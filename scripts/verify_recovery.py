"""Real beat/Redis/Celery recovery from controlled DB fixtures.

Creates only new test analyses. The expired-lease fixture simulates a killed
worker's persisted state; it does not prove an actual OS process crash.
"""

import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import update

from supplement_advisor.config import get_settings
from supplement_advisor.database import make_engine, session_factory
from supplement_advisor.models import Analysis
from supplement_advisor.repository import (
    claim_analysis,
    create_analysis,
    get_analysis,
    reserve_budget,
)
from supplement_advisor.tasks import process_analysis


def verify() -> None:
    engine = make_engine(get_settings().database_url)
    sessions = session_factory(engine)
    try:
        handles = []
        for expired in (False, True):
            token = secrets.token_urlsafe(32)
            with sessions.begin() as session:
                analysis = create_analysis(
                    session,
                    url="https://example.com",
                    product_name=None,
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                )
                if expired:
                    claim = claim_analysis(session, analysis.id)
                    assert reserve_budget(
                        session,
                        analysis.id,
                        claim_token=claim.claim_token,
                        seconds=60,
                        tool_calls=1,
                    )
                    session.execute(
                        update(Analysis)
                        .where(Analysis.id == analysis.id)
                        .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
                    )
                handles.append((analysis.id, token, expired))
        # Intentionally do not publish: the real beat scanner must find both rows.
        with httpx.Client(base_url="http://127.0.0.1:8000", timeout=10, trust_env=False) as client:
            for analysis_id, token, expired in handles:
                deadline = time.monotonic() + 45
                while True:
                    response = client.get(
                        f"/api/analyses/{analysis_id}", headers={"X-Analysis-Token": token}
                    )
                    assert response.status_code == 200
                    status = response.json()["status"]
                    if status not in {"queued", "running"}:
                        assert status in {"needs_input", "completed"}, (
                            "Recovery did not finish collection"
                        )
                        break
                    assert time.monotonic() < deadline, "Beat did not recover persisted work"
                    time.sleep(0.5)
                for _ in range(3):
                    process_analysis.delay(analysis_id)
        # Give the real worker a chance to receive terminal duplicate deliveries.
        time.sleep(2)
        for analysis_id, _, expired in handles:
            with sessions() as session:
                row = get_analysis(session, analysis_id)
                assert row.attempt_count == (2 if expired else 1)
                assert row.active_seconds_reserved == (120 if expired else 60)
                assert row.tool_calls_reserved == (2 if expired else 1)
                assert row.graph_snapshot and row.raw_file
                print(
                    {
                        "recovery": "expired_lease_fixture"
                        if expired
                        else "unpublished_queued_row",
                        "status": row.status,
                        "attempts": row.attempt_count,
                        "reserved_seconds": row.active_seconds_reserved,
                        "duplicate_deliveries": "fenced",
                        "analysis_id": analysis_id,
                    }
                )
    finally:
        engine.dispose()


if __name__ == "__main__":
    verify()
