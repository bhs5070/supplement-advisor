"""Compare saved independent page extractions with live official candidates.

Default: no new collection or model call; reuses recorded vendor extractions.
--live-url explicitly submits one URL to the real stack (one new model run).
Official response values are never injected into page extraction or API input.
Keys, authentication URLs, and guest access tokens are never written to evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from supplement_advisor.agents.collection_graph import _CallBudget, _check_official
from supplement_advisor.config import Settings, configure_logging


class VerificationFailure(Exception):
    """Errors contain only static, non-secret verification codes."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise VerificationFailure(code)


async def verify_cached(input_file: Path) -> dict:
    settings = Settings().model_copy(update={"openai_api_key": None})
    require(bool(settings.food_safety_api_key), "official_key_missing")
    baseline = json.loads(input_file.read_text())
    results = []
    for product in baseline["products"]:
        report = product.get("report")
        entry = {
            "source_product_id": product.get("source_product_id"),
            "source_url": product.get("source_url"),
            "original_collection_status": product.get("collection_status"),
        }
        if product.get("collection_status") != "success" or not report:
            results.append(
                {
                    **entry,
                    "evaluated": False,
                    "original_collection_error": product.get("collection_error"),
                }
            )
            continue
        identity = report.get("product") or {}
        extraction = {
            "product_name": identity.get("name"),
            "manufacturer": identity.get("manufacturer"),
            "report_number": identity.get("report_number"),
            "ingredients": report.get("ingredients", []),
        }
        budget = _CallBudget(settings)
        checked = await _check_official({"extraction": extraction}, None, settings, budget)
        results.append(
            {
                **entry,
                "evaluated": True,
                "input_extraction": extraction,
                "before_check": product.get("official_match_status"),
                "official_result": checked,
                "reserved_official_calls": budget.calls,
                "new_model_calls": 0,
            }
        )
    evaluated = [item for item in results if item.get("evaluated")]
    state_counts = {
        state: sum(
            (item["official_result"].get("official_match") or {}).get("state") == state
            for item in evaluated
        )
        for state in ("matched", "candidate", "unverified", "unknown")
    }
    output = {
        "mode": "saved_independent_vendor_extraction_plus_live_official_api",
        "baseline_file": str(input_file),
        "baseline_sha256": hashlib.sha256(input_file.read_bytes()).hexdigest(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "denominators": {
            "original_sample": len(results),
            "evaluated": len(evaluated),
            "collection_failed_or_report_missing": len(results) - len(evaluated),
            **state_counts,
        },
        "products": results,
        "new_model_calls": 0,
        "new_page_collections": 0,
        "limitation": "Page extraction is saved evidence from the earlier live run, not a fresh URL-to-result run.",
    }
    output["status"] = "passed" if state_counts["matched"] >= 1 else "not_demonstrated"
    return output


def verify_live_url(
    url: str, base_url: str, expected_number: str | None, expect_name_difference: bool = False
) -> dict:
    require(httpx.URL(base_url).host in {"localhost", "127.0.0.1", "::1"}, "local_stack_required")
    with httpx.Client(base_url=base_url, timeout=20, trust_env=False) as client:
        require(client.get("/api/ready").status_code == 200, "stack_not_ready")
        response = client.post("/api/analyses", json={"url": url})
        require(response.status_code == 202, "intake_not_accepted")
        handle = response.json()
        endpoint = f"/api/analyses/{handle['id']}"
        require(client.get(endpoint).status_code == 404, "unauthorized_read_not_denied")
        deadline = time.monotonic() + 90
        while True:
            response = client.get(endpoint, headers={"X-Analysis-Token": handle["access_token"]})
            require(response.status_code == 200, "authorized_read_failed")
            result = response.json()
            if result["status"] not in {"queued", "running"}:
                break
            require(time.monotonic() < deadline, "live_result_timeout")
            time.sleep(0.5)
        report = result.get("report") or {}
        match = report.get("official_match") or {}
        matched_record = match.get("matched_record") or {}
        name_difference = match.get("name_difference") or {}
        checks = {
            "terminal_success": result["status"] in {"completed", "needs_input"},
            "no_supplement": result.get("supplemental_input_used") is False,
            "no_user_input_source": not any(
                s.get("kind") == "user_input" for s in report.get("sources", [])
            ),
            "extraction_completed": (report.get("extraction_status") or {}).get("code")
            in {"extracted", "structured_page"},
            "official_match": match.get("state") == "matched",
            "registered_check": any(
                c.get("name") == "공식 등록 대조" and c.get("status") == "verified"
                for c in report.get("checks", [])
            ),
            "expected_registration": expected_number is None
            or matched_record.get("PRDLST_REPORT_NO") == expected_number,
            "name_difference_disclosed": not expect_name_difference or (
                "registration_identity_with_name_difference" in match.get("reasons", [])
                and name_difference.get("page_name") == (report.get("product") or {}).get("name")
                and name_difference.get("official_name") == matched_record.get("PRDLST_NM")
                and bool(name_difference.get("page_name"))
                and bool(name_difference.get("official_name"))
                and name_difference["page_name"] != name_difference["official_name"]
            ),
            "collection_only": report.get("scope") == "collection_only",
            "no_product_score": report.get("score") is None and report.get("verdict") == "hold",
        }
        return {
            "status": "passed" if all(checks.values()) else "not_demonstrated",
            "mode": "fresh_url_to_live_stack_without_manual_input",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "analysis_id": handle["id"],
            "extraction_status": report.get("extraction_status"),
            "result": result,
            "verification_checks": checks,
            "expected_registration_is_test_assertion_not_input": expected_number,
            "unauthorized_read_status": 404,
        }


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("work/verification/2026-11-09-domestic-matching-live.json"),
    )
    parser.add_argument("--live-url", help="Opt in to one actual URL-to-result run.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--expect-name-difference", action="store_true")
    parser.add_argument(
        "--expected-registration", help="Assertion only; never supplied to the application."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("work/verification/2026-11-09-automatic-matching-cached.json"),
    )
    args = parser.parse_args()
    try:
        result = (
            verify_live_url(
                args.live_url, args.base_url, args.expected_registration, args.expect_name_difference
            )
            if args.live_url
            else asyncio.run(verify_cached(args.input))
        )
    except Exception as exc:
        result = {
            "status": "failed",
            "error": str(exc) if isinstance(exc, VerificationFailure) else type(exc).__name__,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        {
            key: result[key]
            for key in (
                "status",
                "mode",
                "analysis_id",
                "extraction_status",
                "denominators",
                "verification_checks",
                "error",
            )
            if key in result
        }
    )
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
