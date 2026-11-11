"""Opt-in, one-submission evidence review check against a local API."""

from __future__ import annotations

import argparse
import ipaddress
import json
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import httpx


def _local_base(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("invalid_base_url")
    try:
        loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = parsed.hostname.lower() == "localhost"
    if not loopback or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("invalid_base_url")
    return value.rstrip("/")


def _artifact_value(value):
    """Remove private source bodies and credentials from saved API observations."""
    blocked = {"text", "access_token", "token_hash", "api_key", "raw_file"}
    if isinstance(value, dict):
        return {key: _artifact_value(item) for key, item in value.items() if key not in blocked}
    if isinstance(value, list):
        return [_artifact_value(item) for item in value]
    return value


def verify(
    base_url: str, live_url: str, *, client_factory=httpx.Client, timeout_seconds: int = 300
) -> dict:
    """Submit one explicitly supplied product URL. Return credential-free observations."""
    base = _local_base(base_url)
    if not 1 <= timeout_seconds <= 300:
        raise ValueError("timeout_out_of_range")
    with client_factory(
        base_url=base, timeout=20, trust_env=False, follow_redirects=False
    ) as client:
        ready = client.get("/api/ready")
        if ready.status_code != 200 or not all(ready.json().values()):
            return {"live": "failed", "code": "stack_not_ready"}
        submitted = client.post("/api/analyses", json={"url": live_url, "mode": "evidence_review"})
        if submitted.status_code != 202:
            return {
                "live": "failed",
                "code": "submission_rejected",
                "http_status": submitted.status_code,
            }
        accepted = submitted.json()
        identity, token = accepted.get("id"), accepted.get("access_token")
        if not isinstance(identity, str) or not isinstance(token, str) or not token:
            return {"live": "failed", "code": "invalid_acceptance"}
        try:
            identity = str(UUID(identity))
        except ValueError:
            return {"live": "failed", "code": "invalid_acceptance"}
        path = f"/api/analyses/{identity}"
        if client.get(path).status_code != 404:
            return {"live": "failed", "code": "unauthorized_read_not_hidden"}

        deadline, result = time.monotonic() + timeout_seconds, None
        while time.monotonic() < deadline:
            response = client.get(path, headers={"X-Analysis-Token": token})
            if response.status_code != 200:
                return {
                    "live": "failed",
                    "code": "authorized_read_failed",
                    "http_status": response.status_code,
                }
            result = response.json()
            if result.get("status") not in {"queued", "running"}:
                break
            time.sleep(1)
        if not result or result.get("status") in {"queued", "running"}:
            return {"live": "failed", "code": "poll_timeout"}

        report = result.get("report") or {}
        research = report.get("research") or {}
        roles = research.get("roles") or []
        research_sources = research.get("sources") or []
        collection_sources = (report.get("collection_report") or {}).get("sources") or []
        public_sources = (report.get("sources") or []) + collection_sources + research_sources
        role_names = {row.get("role") for row in roles if isinstance(row, dict)}
        public_text_exposed = any("text" in row for row in public_sources if isinstance(row, dict))
        dispatched = any(
            isinstance(row, dict) and row.get("action") == "dispatch"
            for row in (research.get("decisions") or [])
        )
        read_sources = [
            row
            for row in research_sources
            if isinstance(row, dict)
            and row.get("kind") in {"official", "research"}
            and row.get("access_scope") in {"abstract", "document"}
        ]
        demonstrated = dispatched and bool(read_sources)
        usage = research.get("usage") if isinstance(research.get("usage"), dict) else {}
        by_role = usage.get("by_role") if isinstance(usage.get("by_role"), dict) else {}
        redirect_by_role = (
            usage.get("redirect_by_role") if isinstance(usage.get("redirect_by_role"), dict) else {}
        )
        personal_fit = next(
            (
                row.get("status")
                for row in roles
                if isinstance(row, dict) and row.get("role") == "personal_fit"
            ),
            None,
        )
        checks = {
            "evidence_mode_and_scope": result.get("mode") == "evidence_review"
            and report.get("scope") == "evidence_review",
            "score_null_and_hold": report.get("score") is None and report.get("verdict") == "hold",
            "collection_report_preserved": (report.get("collection_report") or {}).get("scope")
            == "collection_only",
            "five_expected_roles": len(roles) == 5
            and len(role_names) == 5
            and role_names
            == {"composition", "claims", "personal_fit", "safety", "official_quality"},
            "personal_fit_not_applicable": personal_fit == "not_applicable",
            "public_sources_hide_text": not public_text_exposed,
            "research_dispatch_and_read_observed": demonstrated,
            "usage_within_limits": isinstance(usage.get("total"), int)
            and usage["total"] <= 20
            and all(
                isinstance(count, int) and count <= 6
                for role, count in by_role.items()
                if role != "supervisor"
            )
            and usage.get("redirect_total", 0) <= 2
            and all(count <= 1 for count in redirect_by_role.values()),
        }
        return {
            "analysis_id": identity,
            "live": "passed" if all(checks.values()) else "failed",
            "checks": checks,
            "api_result": {
                key: _artifact_value(result.get(key))
                for key in (
                    "id",
                    "status",
                    "mode",
                    "product_name",
                    "report",
                    "error_code",
                    "message",
                    "missing_fields",
                    "supplemental_input_used",
                    "can_supplement",
                    "created_at",
                    "updated_at",
                )
                if key in result
            },
            "analysis": {
                "status": result.get("status"),
                "mode": result.get("mode"),
                "scope": report.get("scope"),
                "score": report.get("score"),
                "verdict": report.get("verdict"),
                "research_status": research.get("status"),
                "roles": sorted(role_names),
                "personal_fit_status": personal_fit,
                "dispatch_observed": dispatched,
                "source_count": len(research_sources),
                "research_observation": "demonstrated" if demonstrated else "not_demonstrated",
                "read_source_metadata": [
                    {
                        key: row.get(key)
                        for key in (
                            "id",
                            "kind",
                            "access_scope",
                            "title",
                            "provider",
                            "document_id",
                        )
                    }
                    for row in read_sources
                ],
                "public_source_text_exposed": public_text_exposed,
                "reported_reserved_usage": usage,
                "provider_call_count": "not independently observable",
            },
            "request_count": "one POST; GET polling",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-url", help="One product page URL; omitted means zero requests")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Loopback API base URL")
    parser.add_argument("--output", type=Path, help="Optional credential-free JSON artifact")
    args = parser.parse_args()
    if not args.live_url:
        result = {"live": "not_run", "requests": 0}
    else:
        try:
            result = verify(args.base_url, args.live_url)
        except httpx.TimeoutException:
            result = {"live": "failed", "code": "timeout"}
        except httpx.ConnectError:
            result = {"live": "failed", "code": "connect_error"}
        except Exception:
            # Never include exception text: HTTP errors can contain secrets or response bodies.
            result = {"live": "failed", "code": "verification_failed"}
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 1 if result.get("live") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
