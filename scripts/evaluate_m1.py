"""Run the frozen, bounded M1 product-page evaluation corpus.

This harness reports observed evidence and denominators; it does not certify
general product quality. Configured model and official API credentials are
ignored unless --use-configured-keys is supplied.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from supplement_advisor.agents import collection_graph, run_collection_graph
from supplement_advisor.collection import CollectedPage, collect_page
from supplement_advisor.config import get_settings

DEFAULT_MANIFEST = Path("docs/evaluation/m1-corpus.json")
DEFAULT_OUTPUT = Path("work/verification/m1-evaluation.json")
CACHE_DIR = Path("work/verification/m1-evaluation-cache")
HARNESS_VERSION = "m1-harness-v2"
IDENTITY_FIELDS = ("name", "manufacturer", "report_number")


class ManifestError(ValueError):
    """A frozen corpus is malformed and must not trigger external requests."""


def _safe_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if not parsed.hostname or parsed.username or parsed.password:
            return "<invalid-url>"
        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        netloc = f"{host}:{parsed.port}" if parsed.port is not None else host
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    except ValueError:
        return "<invalid-url>"


def _hostname(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        if parsed.username or parsed.password:
            raise ValueError
        return parsed.hostname.rstrip(".").lower()
    except ValueError:
        raise ManifestError("sample_url_invalid") from None


def _valid_label(label: Any, *, field: str) -> bool:
    if not isinstance(label, dict):
        return False
    status = label.get("status")
    allowed = {"known", "unknown", "not_in_page"} if field in IDENTITY_FIELDS else {"known", "unknown"}
    if status not in allowed:
        return False
    key = "values" if field in IDENTITY_FIELDS else "report_numbers"
    values = label.get(key)
    return (
        isinstance(values, list)
        and (status != "known" or bool(values))
        and all(isinstance(value, str) and value.strip() for value in values)
    )


def validate_manifest(manifest: Any) -> dict[str, Any]:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("version"), (str, int)):
        raise ManifestError("manifest_header_invalid")
    if not isinstance(manifest.get("frozen_at"), str) or not manifest["frozen_at"].strip():
        raise ManifestError("manifest_not_frozen")
    sites = manifest.get("sites")
    samples = manifest.get("samples")
    if not isinstance(sites, list) or not 3 <= len(sites) <= 5:
        raise ManifestError("site_count_must_be_3_to_5")
    if not isinstance(samples, list) or len(samples) != 20:
        raise ManifestError("sample_count_must_be_20")
    site_ids: set[str] = set()
    domains: dict[str, str] = {}
    for site in sites:
        if not isinstance(site, dict) or not isinstance(site.get("id"), str):
            raise ManifestError("site_entry_invalid")
        site_id = site["id"]
        domain = site.get("domain")
        if not site_id or site_id in site_ids or not isinstance(domain, str):
            raise ManifestError("site_identity_invalid")
        domain = domain.lower().rstrip(".")
        if not domain or "/" in domain or domain in domains:
            raise ManifestError("site_domain_invalid")
        site_ids.add(site_id)
        domains[domain] = site_id
    ids: set[str] = set()
    urls: set[str] = set()
    for sample in samples:
        if not isinstance(sample, dict):
            raise ManifestError("sample_entry_invalid")
        sample_id, site_id, url = sample.get("id"), sample.get("site_id"), sample.get("url")
        if not isinstance(sample_id, str) or not sample_id or sample_id in ids:
            raise ManifestError("sample_id_invalid_or_duplicate")
        if site_id not in site_ids or not isinstance(url, str):
            raise ManifestError("sample_site_or_url_invalid")
        host = _hostname(url)
        if not any(host == domain or host.endswith("." + domain) for domain in domains if domains[domain] == site_id):
            raise ManifestError("sample_host_does_not_match_site")
        if url in urls:
            raise ManifestError("sample_url_duplicate")
        ids.add(sample_id)
        urls.add(url)
        labels = sample.get("labels", {})
        if not isinstance(labels, dict):
            raise ManifestError("sample_labels_invalid")
        identity = labels.get("identity", {})
        if not isinstance(identity, dict):
            raise ManifestError("identity_labels_invalid")
        for field in IDENTITY_FIELDS:
            label_key = "product_name" if field == "name" else field
            if label_key in identity and not _valid_label(identity[label_key], field=field):
                raise ManifestError("identity_label_invalid")
        if "official_registration" in labels and not _valid_label(
            labels["official_registration"], field="official_registration"
        ):
            raise ManifestError("official_label_invalid")
    if len(site_ids) != len({sample["site_id"] for sample in samples}):
        raise ManifestError("each_declared_site_must_have_samples")
    return manifest


def _normalize(value: Any) -> str:
    return "".join(str(value or "").casefold().split())


def _value_present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _extracted_values(report: dict[str, Any]) -> list[str]:
    product = report.get("product") or {}
    values = [product.get("name"), product.get("manufacturer"), product.get("report_number")]
    values.extend(report.get("claims", []))
    for ingredient in report.get("ingredients", []):
        if isinstance(ingredient, dict):
            values.extend(ingredient.get(key) for key in ("name", "amount", "unit", "basis"))
    return [value.strip() for value in values if _value_present(value)]


def _grounded_values(report: dict[str, Any], page_text: str) -> list[str]:
    document = _normalize(page_text)
    return [value for value in _extracted_values(report) if _normalize(value) in document]


def _identity_value(report: dict[str, Any], field: str) -> Any:
    product = report.get("product") or {}
    return product.get({"name": "name", "manufacturer": "manufacturer", "report_number": "report_number"}[field])


def _assess_labels(sample: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    labels = sample.get("labels", {})
    identity_labels = labels.get("identity", {})
    assessment: dict[str, Any] = {}
    for field in IDENTITY_FIELDS:
        label = identity_labels.get("product_name" if field == "name" else field)
        if not label:
            assessment[field] = {"status": "unjudged", "label_status": "unknown", "reason": "label_absent"}
            continue
        status = label["status"]
        if status != "known":
            if status == "not_in_page":
                extraction_code = (report.get("extraction_status") or {}).get("code", "unknown")
                if extraction_code not in {"extracted", "structured_page"}:
                    assessment[field] = {
                        "status": "unjudged",
                        "label_status": status,
                        "reason": "extraction_not_completed",
                    }
                    continue
                actual = _identity_value(report, field)
                outcome = "unexpected_present" if _value_present(actual) else "expected_missing"
                assessment[field] = {
                    "status": outcome,
                    "label_status": status,
                    "actual_present": _value_present(actual),
                }
                continue
            assessment[field] = {"status": "unjudged", "label_status": status}
            continue
        extraction_code = (report.get("extraction_status") or {}).get("code", "unknown")
        if extraction_code in {"not_configured", "budget_exhausted", "unknown"}:
            assessment[field] = {"status": "unjudged", "label_status": status, "reason": "extraction_not_run"}
            continue
        actual = _identity_value(report, field)
        expected = label["values"]
        if not _value_present(actual):
            assessment[field] = {"status": "missing", "label_status": status, "actual_present": False}
        else:
            match = any(_normalize(actual) == _normalize(value) for value in expected)
            assessment[field] = {"status": "correct" if match else "incorrect", "label_status": status, "actual_present": True}
    official = labels.get("official_registration")
    match = report.get("official_match") or {}
    if not official or official.get("status") != "known":
        official_label_status = official.get("status", "unknown") if isinstance(official, dict) else "unknown"
        assessment["official_match"] = {"status": "unjudged", "label_status": official_label_status}
    else:
        expected = {_normalize(value) for value in official["report_numbers"]}
        matched = match.get("state") == "matched"
        record = match.get("matched_record") or {}
        actual_number = _normalize(record.get("PRDLST_REPORT_NO"))
        if match.get("state") == "unknown" and "not_configured" in (match.get("reasons") or []):
            status = "unjudged"
            reason = "official_lookup_not_run"
        elif matched and actual_number and actual_number in expected:
            status = "true_match"
            reason = None
        elif matched:
            status = "false_match"
            reason = None
        elif match.get("state") in {"candidate", "unverified", "unknown"}:
            status = "not_confirmed"
            reason = match.get("state")
        else:
            status = "unjudged"
            reason = None
        assessment["official_match"] = {
            "status": status,
            "label_status": official["status"],
            "prediction": match.get("state") or "unknown",
            "reason": reason,
        }
    return assessment


def _cache_path(sample_id: str, url: str) -> Path:
    digest = hashlib.sha256(url.encode()).hexdigest()[:16]
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", sample_id)
    return CACHE_DIR / f"{safe_id}-{digest}.json"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _code_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    files = {
        "harness": Path(__file__),
        "collection": root / "src/supplement_advisor/collection.py",
        "collection_graph": root / "src/supplement_advisor/agents/collection_graph.py",
        "structured_extraction": root / "src/supplement_advisor/agents/structured_extraction.py",
        "config": root / "src/supplement_advisor/config.py",
    }
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}


def _settings(use_configured_keys: bool):
    settings = get_settings()
    if use_configured_keys:
        return settings
    return settings.model_copy(update={"openai_api_key": None, "food_safety_api_key": None})


def _safe_execution_config(settings: Any) -> dict[str, Any]:
    """Expose only non-secret model selection and bounded runtime settings."""
    result: dict[str, Any] = {}
    for name in (
        "openai_model",
        "external_timeout_seconds",
        "model_timeout_seconds",
        "analysis_timeout_seconds",
        "attempt_timeout_seconds",
        "max_tool_calls",
    ):
        value = getattr(settings, name, None)
        if name == "openai_model":
            result[name] = value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,100}", value) else None
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            result[name] = value
    return result


async def evaluate(manifest_path: Path, output_path: Path, *, use_configured_keys: bool) -> dict[str, Any]:
    manifest_bytes = manifest_path.read_bytes()
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = validate_manifest(json.loads(manifest_bytes))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    code_hashes = _code_hashes()
    settings = _settings(use_configured_keys)
    execution_config = _safe_execution_config(settings)
    mode = "configured_keys_opt_in" if use_configured_keys else "collect_only"
    resume_signature = hashlib.sha256(json.dumps({"manifest_sha256": manifest_hash, "mode": mode, "code_sha256": code_hashes, "harness_version": HARNESS_VERSION, "execution_config": execution_config}, sort_keys=True).encode()).hexdigest()
    previous: dict[str, dict[str, Any]] = {}
    run_id = uuid.uuid4().hex[:16]
    if output_path.exists():
        try:
            old = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise ManifestError("checkpoint_corrupt_preserved") from exc
        if old.get("resume_signature") != resume_signature:
            raise ManifestError("checkpoint_signature_mismatch_use_new_output")
        previous = {item["id"]: item for item in old.get("samples", []) if item.get("id")}
        run_id = old.get("run_id", run_id)
    samples_out: list[dict[str, Any]] = []
    for sample in manifest["samples"]:
        sample_id = sample["id"]
        if sample_id in previous:
            old_item = previous[sample_id]
            if old_item.get("status") == "started":
                old_item = {**old_item, "status": "unknown_interrupted", "failure_code": "interrupted_after_checkpoint"}
            samples_out.append(old_item)
            continue
        item: dict[str, Any] = {"id": sample_id, "site_id": sample["site_id"], "url": _safe_url(sample["url"]), "status": "started"}
        item["cohort"] = sample.get("cohort")
        item["expected_display_name"] = sample.get("expected_display_name")
        item["discovery_url"] = _safe_url(sample["discovery_url"]) if sample.get("discovery_url") else None
        item["labels"] = sample.get("labels", {})
        # Durable before collection or any provider request: a crash can never
        # make this frozen sample eligible for a second model call.
        samples_out.append(item)
        _atomic_write(output_path, json.dumps(_result(manifest, manifest_hash, samples_out, use_configured_keys, run_id=run_id, code_hashes=code_hashes, resume_signature=resume_signature, execution_config=execution_config), ensure_ascii=False, indent=2) + "\n")
        samples_out.pop()
        model_requests = official_requests = collection_requests = 0
        timings: dict[str, float] = {}
        graph_module = None
        original_extract = original_check = None
        original_records = original_client = None
        try:
            started = time.perf_counter()
            cache_path = _cache_path(sample_id, sample["url"])
            if cache_path.exists():
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                html = cached.get("html")
                expected_hash = cached.get("source_sha256")
                if (
                    cached.get("url_sha256") != hashlib.sha256(sample["url"].encode()).hexdigest()
                    or not isinstance(html, str)
                    or not isinstance(expected_hash, str)
                    or hashlib.sha256(html.encode("utf-8")).hexdigest() != expected_hash
                    or not isinstance(cached.get("collected_at"), str)
                ):
                    raise ValueError("cache_invalid")
                # Parse via the collector's parser without issuing an HTTP request.
                from supplement_advisor.collection import _PageParser

                parser = _PageParser(sample["url"])
                parser.feed(html)
                parser.close()
                page = CollectedPage(sample["url"], " ".join(parser.title_parts)[:1000], "\n".join(parser.parts), html, parser.images)
                item["collection_source"] = "raw_html_cache"
                item["source_sha256"] = expected_hash
                item["collected_at"] = cached["collected_at"]
            else:
                collection_requests += 1
                page = await collect_page(sample["url"])
                html_hash = hashlib.sha256(page.html.encode("utf-8")).hexdigest()
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                collected_at = datetime.now(timezone.utc).isoformat()
                _atomic_write(cache_path, json.dumps({"url_sha256": hashlib.sha256(sample["url"].encode()).hexdigest(), "html": page.html, "source_sha256": html_hash, "collected_at": collected_at}, ensure_ascii=False))
                item.update({"collection_source": "live_http", "source_sha256": html_hash, "collected_at": collected_at})
            timings["collection_seconds"] = time.perf_counter() - started
            item["collection_request_count"] = collection_requests
            item["page_title"] = page.title
            item["model_request_count"] = 0
            item["official_provider_request_count"] = 0
            import supplement_advisor.agents.collection_graph as graph_module

            original_extract = graph_module._extract
            original_check = graph_module._check_official

            async def timed_extract(*args, **kwargs):
                stage_started = time.perf_counter()
                try:
                    return await original_extract(*args, **kwargs)
                finally:
                    timings["extraction_seconds"] = timings.get("extraction_seconds", 0.0) + time.perf_counter() - stage_started

            async def timed_check(*args, **kwargs):
                stage_started = time.perf_counter()
                try:
                    return await original_check(*args, **kwargs)
                finally:
                    timings["official_match_seconds"] = timings.get("official_match_seconds", 0.0) + time.perf_counter() - stage_started

            graph_module._extract = timed_extract
            graph_module._check_official = timed_check
            if use_configured_keys:
                original_records = collection_graph._official_records

                async def counted_records(*args, **kwargs):
                    nonlocal official_requests
                    if official_requests >= 3:
                        raise RuntimeError("per-sample official request limit exceeded")
                    official_requests += 1
                    return await original_records(*args, **kwargs)

                collection_graph._official_records = counted_records
                # The model SDK call count is instrumented at the actual parse boundary.
                original_client = graph_module.AsyncOpenAI

                class CountedResponses:
                    def __init__(self, responses):
                        self._responses = responses
                    def __getattr__(self, name):
                        return getattr(self._responses, name)
                    async def parse(self, *args, **kwargs):
                        nonlocal model_requests
                        if model_requests >= 1:
                            raise RuntimeError("per-sample model request limit exceeded")
                        model_requests += 1
                        return await self._responses.parse(*args, **kwargs)

                class CountedClient:
                    def __init__(self, *args, **kwargs):
                        self._client = original_client(*args, **kwargs)
                    async def __aenter__(self):
                        await self._client.__aenter__()
                        return self
                    async def __aexit__(self, *args):
                        return await self._client.__aexit__(*args)
                    @property
                    def responses(self):
                        return CountedResponses(self._client.responses)

                graph_module.AsyncOpenAI = CountedClient
                try:
                    stage = time.perf_counter()
                    report = await run_collection_graph(page, None, settings)
                    timings["analysis_seconds"] = time.perf_counter() - stage
                finally:
                    graph_module.AsyncOpenAI = original_client
                    collection_graph._official_records = original_records
            else:
                stage = time.perf_counter()
                try:
                    report = await run_collection_graph(page, None, settings)
                finally:
                    timings["analysis_seconds"] = time.perf_counter() - stage
            graph_module._extract = original_extract
            graph_module._check_official = original_check
            extraction_code = (report.get("extraction_status") or {}).get("code", "unknown")
            extracted_values = _extracted_values(report)
            grounded_values = _grounded_values(report, page.text)
            extraction_ran = extraction_code not in {"not_configured", "budget_exhausted", "unknown"}
            for source in report.get("sources", []):
                if isinstance(source, dict) and isinstance(source.get("url"), str):
                    source["url"] = _safe_url(source["url"])
            item.update({
                "status": "completed",
                "extraction_code": extraction_code,
                "grounding": {
                    "status": "unassessed" if not extraction_ran or not extracted_values else "pass" if len(grounded_values) == len(extracted_values) else "fail",
                    "observed_value_count": len(extracted_values),
                    "grounded_value_count": len(grounded_values),
                    "ungrounded_value_count": len(extracted_values) - len(grounded_values),
                },
                "identity": _assess_labels(sample, report),
                "official_match": report.get("official_match") or {"state": "unknown"},
                "report": report,
                "cohort": sample.get("cohort"),
                "expected_display_name": sample.get("expected_display_name"),
                "discovery_url": _safe_url(sample["discovery_url"]) if sample.get("discovery_url") else None,
                "labels": sample.get("labels", {}),
                "official_provider_request_count": official_requests,
                "model_request_count": model_requests,
                "latency_seconds": timings,
                "tool_request_count": collection_requests + model_requests + official_requests,
                "reason_codes": {
                    "collection": None,
                    "extraction": (report.get("extraction_status") or {}).get("code", "unknown"),
                    "official": ((report.get("official_match") or {}).get("reasons") or []),
                },
            })
        except Exception as exc:
            # Never persist arbitrary exception text; it can contain private URLs or credentials.
            code = getattr(exc, "code", type(exc).__name__)
            item.update({"status": "failed", "failure_code": code if isinstance(code, str) else "error"})
            item["collection_request_count"] = collection_requests
            item["model_request_count"] = model_requests
            item["official_provider_request_count"] = official_requests
            item["latency_seconds"] = timings
            item["tool_request_count"] = collection_requests + model_requests + official_requests
            if "collection_seconds" not in timings:
                timings["collection_seconds"] = time.perf_counter() - started
            item["reason_codes"] = {"collection": code if not item.get("collection_source") else None}
        finally:
            if graph_module is not None and original_extract is not None:
                graph_module._extract = original_extract
                graph_module._check_official = original_check
            if graph_module is not None and original_client is not None:
                graph_module.AsyncOpenAI = original_client
            if original_records is not None:
                collection_graph._official_records = original_records
        samples_out.append(item)
        result = _result(manifest, manifest_hash, samples_out, use_configured_keys, run_id=run_id, code_hashes=code_hashes, resume_signature=resume_signature, execution_config=execution_config)
        _atomic_write(output_path, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    result = _result(manifest, manifest_hash, samples_out, use_configured_keys, run_id=run_id, code_hashes=code_hashes, resume_signature=resume_signature, execution_config=execution_config)
    _atomic_write(output_path, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def _summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    identity_counts = {field: {} for field in IDENTITY_FIELDS}
    official_counts: dict[str, int] = {}
    grounding: dict[str, int] = {}
    extraction_codes: dict[str, int] = {}
    official_states: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    totals = {key: 0 for key in ("collection_http_requests", "model_requests", "official_provider_requests", "tool_requests")}
    latency = {key: 0.0 for key in ("collection_seconds", "extraction_seconds", "official_match_seconds", "analysis_seconds")}
    for sample in samples:
        totals["collection_http_requests"] += sample.get("collection_request_count", 0)
        totals["model_requests"] += sample.get("model_request_count", 0)
        totals["official_provider_requests"] += sample.get("official_provider_request_count", 0)
        totals["tool_requests"] += sample.get("tool_request_count", 0)
        for key in latency:
            latency[key] += sample.get("latency_seconds", {}).get(key, 0.0)
        code = sample.get("extraction_code", sample.get("failure_code", "not_run"))
        extraction_codes[code] = extraction_codes.get(code, 0) + 1
        grounding_status = sample.get("grounding", {}).get("status", "unassessed")
        grounding[grounding_status] = grounding.get(grounding_status, 0) + 1
        for field in IDENTITY_FIELDS:
            assessment = sample.get("identity", {}).get(field, {})
            bucket = identity_counts[field]
            label_status = assessment.get("label_status", "unknown")
            outcome = assessment.get("status", "unjudged")
            labels = bucket.setdefault("label_status", {})
            labels[label_status] = labels.get(label_status, 0) + 1
            outcomes = bucket.setdefault("outcome", {})
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
        official_assessment = sample.get("identity", {}).get("official_match", {})
        official_status = official_assessment.get("status", "unjudged")
        official_label_status = official_assessment.get("label_status", "unknown")
        official_labels = official_counts.setdefault("label_status", {})
        official_labels[official_label_status] = official_labels.get(official_label_status, 0) + 1
        official_outcomes = official_counts.setdefault("outcome", {})
        official_outcomes[official_status] = official_outcomes.get(official_status, 0) + 1
        state = (sample.get("official_match") or {}).get("state", "unknown")
        official_states[state] = official_states.get(state, 0) + 1
        for category in ("collection", "extraction", "official"):
            reason = sample.get("reason_codes", {}).get(category)
            values = reason if isinstance(reason, list) else [reason]
            for value in values:
                if value:
                    key = f"{category}:{value}"
                    reason_counts[key] = reason_counts.get(key, 0) + 1
    return {
        "n": len(samples),
        "collection_http_attempt_n": sum(sample.get("collection_request_count", 0) for sample in samples),
        "collection_http_success_n": sum(1 for sample in samples if sample.get("collection_source") == "live_http"),
        "cached_source_reuse_n": sum(1 for sample in samples if sample.get("collection_source") == "raw_html_cache"),
        "collection_input_available_n": sum(1 for sample in samples if sample.get("collection_source")),
        "model_request_n": totals["model_requests"],
        "model_completed_n": sum(1 for sample in samples if sample.get("extraction_code") == "extracted"),
        "structured_extraction_n": sum(1 for sample in samples if sample.get("extraction_code") == "structured_page"),
        "official_provider_request_n": totals["official_provider_requests"],
        "grounding": grounding,
        "identity": identity_counts,
        "official_prediction_state": official_states,
        "official_judgement": official_counts,
        "actual_requests": totals,
        "latency_seconds_sum": latency,
        "reason_counts": reason_counts,
        "extraction_codes": extraction_codes,
    }


def _result(manifest: dict[str, Any], manifest_hash: str, samples: list[dict[str, Any]], use_configured_keys: bool, *, run_id: str, code_hashes: dict[str, str], resume_signature: str, execution_config: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for sample in samples:
        counts[sample.get("status", "unknown")] = counts.get(sample.get("status", "unknown"), 0) + 1
    site_samples = {site["id"]: [item for item in samples if item.get("site_id") == site["id"]] for site in manifest["sites"]}
    cohort_samples = {cohort: [item for item in samples if item.get("cohort") == cohort] for cohort in sorted({item.get("cohort", "unknown") for item in manifest["samples"]})}
    return {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": manifest_hash,
        "mode": "configured_keys_opt_in" if use_configured_keys else "collect_only",
        "code_sha256": code_hashes["harness"],
        "code_hashes": code_hashes,
        "execution_config": execution_config,
        "resume_signature": resume_signature,
        "manifest_version": manifest.get("version"),
        "parent_manifest_sha256": manifest.get("parent_manifest_sha256"),
        "fixed_denominators": {
            "site": {site["id"]: sum(1 for item in manifest["samples"] if item["site_id"] == site["id"]) for site in manifest["sites"]},
            "cohort": {cohort: sum(1 for item in manifest["samples"] if item.get("cohort") == cohort) for cohort in sorted({item.get("cohort", "unknown") for item in manifest["samples"]})},
        },
        "denominators": {"manifest_n": len(manifest["samples"]), "processed_n": len(samples), "statuses": counts},
        "metrics": {"overall": _summary(samples), "by_site": {key: _summary(value) for key, value in site_samples.items()}, "by_cohort": {key: _summary(value) for key, value in cohort_samples.items()}},
        "samples": samples,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--use-configured-keys", action="store_true", help="Allow actual model and official API requests using configured credentials.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = asyncio.run(evaluate(args.manifest, args.output, use_configured_keys=args.use_configured_keys))
    except (ManifestError, OSError, json.JSONDecodeError) as exc:
        message = str(exc) if isinstance(exc, ManifestError) else "manifest_read_failed"
        sys.stderr.write(f"Evaluation not started: {message}\n")
        return 2
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output == Path("-"):
        sys.stdout.write(rendered + "\n")
    return 0 if len(result["samples"]) == 20 else 1


if __name__ == "__main__":
    raise SystemExit(main())
