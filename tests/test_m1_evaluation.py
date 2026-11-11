"""Mock-only tests for the frozen M1 evaluation harness."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts import evaluate_m1 as evaluation


def _manifest():
    sites = [
        {"id": f"site{i}", "domain": f"vendor{i}.example"}
        for i in range(3)
    ]
    samples = []
    for index in range(20):
        site = sites[index % len(sites)]
        samples.append(
            {
                "id": f"sample-{index}",
                "site_id": site["id"],
                "url": f"https://www.{site['domain']}/product/{index}?tracking=secret",
                "expected_display_name": "metadata must not enter model input",
                "cohort": "regression_seed" if index == 0 else "holdout_discovery",
                "labels": {
                    "identity": {
                        "product_name": {"status": "unknown", "values": []},
                        "manufacturer": {"status": "unknown", "values": []},
                        "report_number": {"status": "unknown", "values": []},
                    },
                    "official_registration": {"status": "unknown", "report_numbers": []},
                },
            }
        )
    return {"version": "test-v1", "frozen_at": "2026-11-10T00:00:00Z", "sites": sites, "samples": samples}


def _report():
    return {
        "product": {"name": "Actual Product", "manufacturer": None, "report_number": None},
        "claims": [],
        "ingredients": [],
        "extraction_status": {"code": "extracted"},
        "official_match": {"state": "unknown", "reasons": ["not_configured"]},
    }


def test_frozen_manifest_schema_and_real_corpus():
    corpus = json.loads(evaluation.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    assert len(evaluation.validate_manifest(corpus)["samples"]) == 20
    assert evaluation.validate_manifest(_manifest())["samples"][0]["expected_display_name"]


def test_manifest_rejects_duplicates_wrong_host_and_known_empty_label():
    corpus = _manifest()
    corpus["samples"][1]["id"] = corpus["samples"][0]["id"]
    with pytest.raises(evaluation.ManifestError, match="sample_id_invalid_or_duplicate"):
        evaluation.validate_manifest(corpus)

    corpus = _manifest()
    corpus["samples"][0]["url"] = "https://attacker.example/product"
    with pytest.raises(evaluation.ManifestError, match="sample_host_does_not_match_site"):
        evaluation.validate_manifest(corpus)

    corpus = _manifest()
    corpus["samples"][0]["labels"]["identity"]["product_name"] = {
        "status": "known",
        "values": [],
    }
    with pytest.raises(evaluation.ManifestError, match="identity_label_invalid"):
        evaluation.validate_manifest(corpus)


@pytest.mark.asyncio
async def test_collect_only_preserves_denominators_and_never_passes_expected_name(
    monkeypatch, tmp_path
):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    monkeypatch.setattr(evaluation, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(
        evaluation,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key="secret",
            food_safety_api_key="secret",
            model_copy=lambda update: SimpleNamespace(**update),
        ),
    )
    collected = []
    graph_args = []

    async def collect(url):
        collected.append(url)
        return SimpleNamespace(
            url=url,
            title="Public title",
            text="Actual Product label",
            html="<html><title>Public title</title>Actual Product label</html>",
            image_urls=[],
        )

    async def graph(page, product_name, settings):
        graph_args.append(product_name)
        assert settings.openai_api_key is None
        assert settings.food_safety_api_key is None
        return _report()

    monkeypatch.setattr(evaluation, "collect_page", collect)
    monkeypatch.setattr(evaluation, "run_collection_graph", graph)
    output = tmp_path / "evaluation.json"
    result = await evaluation.evaluate(manifest_path, output, use_configured_keys=False)

    assert len(collected) == 20
    assert graph_args == [None] * 20
    assert result["manifest_sha256"] == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert result["denominators"]["manifest_n"] == 20
    assert result["denominators"]["processed_n"] == 20
    assert result["mode"] == "collect_only"
    assert result["code_sha256"] == result["code_hashes"]["harness"]
    assert "structured_extraction" in result["code_hashes"]
    assert all(item["model_request_count"] == 0 for item in result["samples"])
    assert all(item["collection_request_count"] == 1 for item in result["samples"])
    assert "tracking=secret" not in output.read_text(encoding="utf-8")
    assert all(item["identity"]["name"]["status"] == "unjudged" for item in result["samples"])


@pytest.mark.asyncio
async def test_completed_and_failed_samples_are_not_replayed(monkeypatch, tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    monkeypatch.setattr(evaluation, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(
        evaluation,
        "get_settings",
        lambda: SimpleNamespace(model_copy=lambda update: SimpleNamespace(**update)),
    )
    calls = []

    async def collect(url):
        calls.append(url)
        raise RuntimeError("private URL and secret must not be serialized")

    monkeypatch.setattr(evaluation, "collect_page", collect)
    output = tmp_path / "evaluation.json"
    first = await evaluation.evaluate(manifest_path, output, use_configured_keys=False)
    assert all(item["status"] == "failed" for item in first["samples"])
    assert "private URL and secret" not in output.read_text(encoding="utf-8")
    await evaluation.evaluate(manifest_path, output, use_configured_keys=False)
    assert len(calls) == 20


@pytest.mark.asyncio
async def test_collect_only_raw_cache_reuses_verified_source_in_live_stage(monkeypatch, tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    monkeypatch.setattr(evaluation, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(
        evaluation,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key="configured",
            food_safety_api_key="configured",
            openai_model="gpt-5.6-luna",
            model_copy=lambda update: SimpleNamespace(**update),
        ),
    )
    collected = []

    async def collect(url):
        collected.append(url)
        return SimpleNamespace(url=url, title="Title", text="Actual Product", html="Actual Product", image_urls=[])

    async def graph(page, product_name, settings):
        assert product_name is None
        return _report()

    monkeypatch.setattr(evaluation, "collect_page", collect)
    monkeypatch.setattr(evaluation, "run_collection_graph", graph)
    baseline = tmp_path / "collect-only.json"
    live = tmp_path / "opt-in.json"
    await evaluation.evaluate(manifest_path, baseline, use_configured_keys=False)
    result = await evaluation.evaluate(manifest_path, live, use_configured_keys=True)

    assert len(collected) == 20
    assert all(item["collection_source"] == "raw_html_cache" for item in result["samples"])
    assert all(item["collection_request_count"] == 0 for item in result["samples"])


@pytest.mark.asyncio
async def test_resume_signature_rejects_corrupt_or_different_mode_checkpoint(monkeypatch, tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    output = tmp_path / "run.json"
    monkeypatch.setattr(evaluation, "get_settings", lambda: SimpleNamespace(model_copy=lambda update: SimpleNamespace(**update)))
    monkeypatch.setattr(evaluation, "collect_page", lambda url: None)
    output.write_text("{truncated", encoding="utf-8")
    with pytest.raises(evaluation.ManifestError, match="checkpoint_corrupt_preserved"):
        await evaluation.evaluate(manifest_path, output, use_configured_keys=False)

    output.unlink()
    await evaluation.evaluate(manifest_path, output, use_configured_keys=False)
    with pytest.raises(evaluation.ManifestError, match="checkpoint_signature_mismatch"):
        await evaluation.evaluate(manifest_path, output, use_configured_keys=True)


def test_known_official_match_uses_only_the_matched_record_number():
    sample = {
        "labels": {
            "identity": {},
            "official_registration": {"status": "known", "report_numbers": ["123"]},
        }
    }
    report = {
        "product": {},
        "official_match": {
            "state": "matched",
            "matched_record": {"PRDLST_REPORT_NO": "999"},
            "evidence": [{"field": "report_number", "official_value": "123"}],
        },
    }
    assert evaluation._assess_labels(sample, report)["official_match"]["status"] == "false_match"


def test_grounding_is_unassessed_for_empty_extraction_and_flags_invented_values():
    assert evaluation._extracted_values({"product": {}, "claims": [], "ingredients": []}) == []
    report = {"product": {"name": "Invented"}, "claims": [], "ingredients": []}
    assert evaluation._grounded_values(report, "the original page") == []


def test_identity_metrics_keep_label_denominators_separate_from_outcomes():
    samples = [
        {"identity": {"name": {"label_status": "known", "status": "correct"}}},
        {"identity": {"name": {"label_status": "unknown", "status": "unjudged"}}},
        {"identity": {"name": {"label_status": "not_in_page", "status": "unjudged"}}},
    ]
    name = evaluation._summary(samples)["identity"]["name"]
    assert name["label_status"] == {"known": 1, "unknown": 1, "not_in_page": 1}
    assert name["outcome"] == {"correct": 1, "unjudged": 2}


def test_runtime_signature_hashes_extraction_code_and_only_safe_config_fields():
    hashes = evaluation._code_hashes()
    assert hashes["structured_extraction"] == hashlib.sha256(
        evaluation.Path("src/supplement_advisor/agents/structured_extraction.py").read_bytes()
    ).hexdigest()
    settings = SimpleNamespace(
        openai_model="gpt-5.6-luna",
        external_timeout_seconds=15,
        model_timeout_seconds=30,
        analysis_timeout_seconds=180,
        attempt_timeout_seconds=60,
        max_tool_calls=20,
        openai_api_key="secret-key-must-not-appear",
        database_url="postgres://secret",
    )
    config = evaluation._safe_execution_config(settings)
    assert config == {
        "openai_model": "gpt-5.6-luna",
        "external_timeout_seconds": 15,
        "model_timeout_seconds": 30,
        "analysis_timeout_seconds": 180,
        "attempt_timeout_seconds": 60,
        "max_tool_calls": 20,
    }
    assert "secret" not in json.dumps(config)


def test_not_in_page_labels_measure_completed_extraction_and_skip_incomplete_runs():
    sample = {
        "labels": {
            "identity": {
                "product_name": {"status": "not_in_page", "values": []},
                "manufacturer": {"status": "unknown", "values": []},
                "report_number": {"status": "not_in_page", "values": []},
            },
            "official_registration": {"status": "unknown", "report_numbers": []},
        }
    }
    empty_report = {
        "product": {"name": None, "manufacturer": None, "report_number": None},
        "extraction_status": {"code": "structured_page"},
        "official_match": {"state": "unknown"},
    }
    assessment = evaluation._assess_labels(sample, empty_report)
    assert assessment["name"] == {
        "status": "expected_missing",
        "label_status": "not_in_page",
        "actual_present": False,
    }

    visible_report = {
        **empty_report,
        "product": {"name": "Unexpected product name", "manufacturer": None, "report_number": None},
    }
    assert evaluation._assess_labels(sample, visible_report)["name"]["status"] == "unexpected_present"

    incomplete_report = {**empty_report, "extraction_status": {"code": "not_configured"}}
    assert evaluation._assess_labels(sample, incomplete_report)["name"] == {
        "status": "unjudged",
        "label_status": "not_in_page",
        "reason": "extraction_not_completed",
    }
