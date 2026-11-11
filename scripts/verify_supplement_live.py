"""Check real supplemental-input processing from an explicitly controlled DB seed.

Requires the migrated local Compose stack and a configured I0030 key. The initial
report is synthetic, and the manually supplied identity comes from a previously
authenticated official response. This verifies API/DB/queue/official lookup and
permissions; it is not independent automatic matching of a vendor page. No model
call or collection is needed. Tokens and API keys are never written to artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from supplement_advisor.config import Settings, configure_logging
from supplement_advisor.database import make_engine, session_factory
from supplement_advisor.repository import (
    claim_analysis,
    create_analysis,
    finish_analysis,
    get_analysis,
    reserve_budget,
)


class VerificationFailure(Exception):
    """Static error codes only; never arbitrary HTTP or DB exception text."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise VerificationFailure(code)


def seed_report() -> dict:
    return {
        "scope": "collection_only",
        "summary": "추가 입력 경로 검증용 DB 시드입니다. 실제 수집 결과가 아닙니다.",
        "product": {"name": None, "manufacturer": None, "report_number": None},
        "claims": [],
        "ingredients": [],
        "sources": [
            {
                "id": "product-page",
                "url": "",
                "title": "통제 검증용 초기 자료",
                "kind": "test_fixture",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "excerpt": "판매 페이지를 독립적으로 수집한 자료가 아닙니다.",
            }
        ],
        "checks": [
            {
                "name": name,
                "status": "unavailable",
                "detail": "초기 단계는 통제 DB 시드입니다.",
                "source_ids": [],
            }
            for name in ("페이지 수집", "표시 정보 추출", "공식 등록 대조")
        ],
        "limitations": ["초기 수집·모델 추출은 검증 범위에 포함되지 않습니다."],
        "score": None,
        "verdict": "hold",
        "missing_fields": ["product_name", "manufacturer", "report_number", "ingredient_label"],
    }


def counters(sessions, analysis_id: str) -> dict:
    with sessions() as session:
        row = get_analysis(session, analysis_id)
        require(row is not None, "analysis_missing")
        return {
            "attempts": row.attempt_count,
            "reserved_seconds": row.active_seconds_reserved,
            "tool_calls": row.tool_calls_reserved,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "supplement_received": row.supplemental_received_at is not None,
        }


def verify(record_file: Path, base_url: str) -> dict:
    configure_logging()
    settings = Settings()
    require(bool(settings.food_safety_api_key), "foodsafety_not_configured")
    require(httpx.URL(base_url).host in {"localhost", "127.0.0.1", "::1"}, "local_stack_required")
    record = json.loads(record_file.read_text())["sample_records"][0]
    payload = {
        "product_name": record["PRDLST_NM"],
        "manufacturer": record["BSSH_NM"],
        "report_number": record["PRDLST_REPORT_NO"],
        "ingredients": [
            {"name": "검증용 수동 입력 성분", "amount": None, "unit": None, "basis": None}
        ],
    }
    token = secrets.token_urlsafe(32)
    engine = make_engine(settings.database_url)
    sessions = session_factory(engine)
    try:
        with httpx.Client(base_url=base_url, timeout=20, trust_env=False) as client:
            require(client.get("/api/ready").status_code == 200, "stack_not_ready")
            with sessions.begin() as session:
                row = create_analysis(
                    session,
                    url="https://example.com/m1-controlled-seed",
                    product_name=None,
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                )
                analysis_id = row.id
                claim = claim_analysis(session, analysis_id)
                require(claim is not None, "seed_claim_failed")
                require(
                    reserve_budget(
                        session,
                        analysis_id,
                        claim_token=claim.claim_token,
                        seconds=60,
                        tool_calls=1,
                    ),
                    "seed_budget_failed",
                )
                require(
                    finish_analysis(
                        session,
                        analysis_id,
                        claim_token=claim.claim_token,
                        status="needs_input",
                        report=seed_report(),
                        error_code="insufficient_information",
                        message="통제 DB 시드: 필요한 정보를 한 번 보완합니다.",
                    ),
                    "seed_finish_failed",
                )
            before = counters(sessions, analysis_id)
            endpoint = f"/api/analyses/{analysis_id}"
            headers = {"X-Analysis-Token": token}
            require(client.get(endpoint).status_code == 404, "missing_token_not_denied")
            require(
                client.post(
                    endpoint + "/supplement",
                    json=payload,
                    headers={
                        "X-Analysis-Token": "wrong-token",
                    },
                ).status_code
                == 404,
                "wrong_token_not_denied",
            )
            require(
                client.get(endpoint, headers=headers).json().get("can_supplement") is True,
                "initial_form_not_available",
            )
            accepted = client.post(endpoint + "/supplement", json=payload, headers=headers)
            require(accepted.status_code == 202, "supplement_not_accepted")
            require("access_token" not in accepted.json(), "token_reissued")
            deadline = time.monotonic() + 90
            while True:
                response = client.get(endpoint, headers=headers)
                require(response.status_code == 200, "result_not_accessible")
                result = response.json()
                if result["status"] not in {"queued", "running"}:
                    break
                require(time.monotonic() < deadline, "worker_result_timeout")
                time.sleep(0.5)
            require(result["status"] == "completed", "supplement_not_completed")
            require(result.get("supplemental_input_used") is True, "input_use_not_recorded")
            require(result.get("can_supplement") is False, "second_form_available")
            report = result.get("report") or {}
            require(report.get("scope") == "collection_only", "scope_changed")
            require(
                report.get("score") is None and report.get("verdict") == "hold",
                "unsupported_verdict",
            )
            require(
                any(item.get("kind") == "user_input" for item in report.get("sources", [])),
                "user_source_missing",
            )
            field_sources = report.get("product", {}).get("field_sources", {})
            require(
                all(
                    field_sources.get(field) == "user-input"
                    for field in ("name", "manufacturer", "report_number")
                ),
                "manual_identity_provenance_missing",
            )
            require(
                all(
                    item.get("source_id") == "user-input"
                    and all(item.get(field) is None for field in ("amount", "unit", "basis"))
                    for item in report.get("ingredients", [])
                )
                and bool(report.get("ingredients")),
                "manual_ingredient_provenance_or_unknown_values_changed",
            )
            require(
                any(
                    item.get("name") == "공식 등록 대조" and item.get("status") == "verified"
                    for item in report.get("checks", [])
                ),
                "official_match_not_verified",
            )
            require(
                client.post(endpoint + "/supplement", json=payload, headers=headers).status_code
                == 409,
                "second_submission_not_denied",
            )
            after = counters(sessions, analysis_id)
            require(
                after["attempts"] == before["attempts"] + 1, "attempt_count_reset_or_duplicated"
            )
            require(
                after["reserved_seconds"] == before["reserved_seconds"] + 60, "time_budget_reset"
            )
            require(after["tool_calls"] == before["tool_calls"] + 1, "unexpected_tool_calls")
            require(after["started_at"] == before["started_at"], "first_start_changed")
            return {
                "status": "passed",
                "input_type": "controlled_db_seed_and_official_record_derived_manual_input",
                "independent_vendor_match": False,
                "analysis_id": analysis_id,
                "before": before,
                "after": after,
                "result": result,
                "wrong_token_status": 404,
                "duplicate_submission_status": 409,
                "additional_model_or_collection_calls": 0,
            }
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--record-file",
        type=Path,
        default=Path("work/verification/2026-11-09-food-safety-auth.json"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("work/verification/2026-11-09-supplement-live.json")
    )
    args = parser.parse_args()
    try:
        result = verify(args.record_file, args.base_url)
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
            for key in ("status", "analysis_id", "before", "after", "error")
            if key in result
        }
    )
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
