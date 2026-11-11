"""Transactions belong to callers, including committing a claim before doing work.

A claim lasts 240 seconds by default, longer than the 180-second runtime budget.
Expired claims may be redelivered by list_dispatchable; a fresh UUID fences every
attempt. A stale or expired worker cannot finish. Budgets are reserved and committed
before bounded work begins; a crash never refunds the reservation. Queue waiting
does not consume active time. The final expired attempt is failed on claim.
"""

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.orm import Session

from .models import Analysis

TERMINAL_STATUSES = frozenset({"completed", "failed", "needs_input"})


def _database_now(session: Session):
    # PostgreSQL's CURRENT_TIMESTAMP is fixed at transaction start. Use the
    # wall clock so long-lived transactions cannot extend an expired lease.
    # Keep PostgreSQL's clock in the UPDATE expression: a worker waiting for a
    # row lock must not finish using a timestamp fetched before that wait.
    return (
        func.clock_timestamp()
        if session.get_bind().dialect.name == "postgresql"
        else datetime.now(timezone.utc)
    )


def _lock_claim(session: Session, analysis_id: str, claim_token: str) -> bool:
    # Evaluate the lease in a subsequent statement, after acquiring the lock.
    # A bare UPDATE can evaluate WHERE before waiting on an unchanged locked row.
    return session.scalar(
        select(Analysis.id)
        .where(
            Analysis.id == analysis_id,
            Analysis.status == "running",
            Analysis.claim_token == claim_token,
        )
        .with_for_update()
    ) is not None


def create_analysis(
    session: Session, *, url: str, product_name: str | None, token_hash: str,
    mode: str = "collection",
) -> Analysis:
    if re.fullmatch(r"[0-9a-f]{64}", token_hash) is None:
        raise ValueError("token_hash must be a SHA-256 hex digest")
    if mode not in {"collection", "evidence_review"}:
        raise ValueError("unknown analysis mode")
    analysis = Analysis(url=url, product_name=product_name, token_hash=token_hash, mode=mode)
    session.add(analysis)
    session.flush()
    return analysis


def get_analysis(session: Session, analysis_id: str) -> Analysis | None:
    return session.get(Analysis, analysis_id)


def accept_supplement(
    session: Session, analysis_id: str, token_hash: str, payload: dict[str, Any]
) -> bool:
    """Atomically accept the sole supplement for an authorized needs_input row."""
    now = _database_now(session)
    result = session.execute(
        update(Analysis)
        .where(
            Analysis.id == analysis_id,
            Analysis.token_hash == token_hash,
            Analysis.status == "needs_input",
            Analysis.supplemental_input.is_(None),
        )
        .values(
            supplemental_input=payload,
            supplemental_received_at=now,
            status="queued",
            error_code=None,
            message=None,
            completed_at=None,
            claim_token=None,
            lease_expires_at=None,
            graph_snapshot=case(
                (Analysis.mode == "collection", None), else_=Analysis.graph_snapshot
            ),
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def list_dispatchable(session: Session, *, limit: int = 50) -> list[str]:
    if limit < 1:
        raise ValueError("limit must be positive")
    now = _database_now(session)
    return list(
        session.scalars(
            select(Analysis.id)
            .where(
                or_(
                    Analysis.status == "queued",
                    and_(Analysis.status == "running", Analysis.lease_expires_at <= now),
                )
            )
            .order_by(Analysis.created_at, Analysis.id)
            .limit(limit)
        )
    )


def claim_analysis(
    session: Session,
    analysis_id: str,
    *,
    max_attempts: int = 3,
    lease_seconds: int = 240,
) -> Analysis | None:
    if max_attempts < 1 or lease_seconds < 1:
        raise ValueError("max_attempts and lease_seconds must be positive")
    now = _database_now(session)
    dispatchable = or_(
        Analysis.status == "queued",
        and_(Analysis.status == "running", Analysis.lease_expires_at <= now),
    )
    claimed = session.scalars(
        update(Analysis)
        .where(Analysis.id == analysis_id, dispatchable, Analysis.attempt_count < max_attempts)
        .values(
            status="running",
            claim_token=str(uuid4()),
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            attempt_count=Analysis.attempt_count + 1,
            started_at=func.coalesce(Analysis.started_at, now),
            updated_at=now,
        )
        .returning(Analysis)
        .execution_options(populate_existing=True, synchronize_session=False)
    ).one_or_none()
    if claimed is not None:
        return claimed
    # A crash on the last permitted attempt must not leave a running row forever.
    session.execute(
        update(Analysis)
        .where(Analysis.id == analysis_id, dispatchable, Analysis.attempt_count >= max_attempts)
        .values(
            status="failed",
            error_code="attempt_limit_exceeded",
            message="The analysis could not finish after repeated processing attempts.",
            claim_token=None,
            lease_expires_at=None,
            completed_at=now,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    return None


def finish_analysis(
    session: Session,
    analysis_id: str,
    *,
    claim_token: str,
    status: str,
    report: dict[str, Any] | None = None,
    error_code: str | None = None,
    message: str | None = None,
    raw_file: str | None = None,
) -> bool:
    if status not in TERMINAL_STATUSES:
        raise ValueError("finish status must be completed, failed, or needs_input")
    if not _lock_claim(session, analysis_id, claim_token):
        return False
    now = _database_now(session)
    result = session.execute(
        update(Analysis)
        .where(
            Analysis.id == analysis_id,
            Analysis.status == "running",
            Analysis.claim_token == claim_token,
            Analysis.lease_expires_at > now,
        )
        .values(
            status=status,
            report=report,
            error_code=error_code,
            message=message,
            raw_file=raw_file,
            claim_token=None,
            lease_expires_at=None,
            completed_at=now,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def reserve_budget(
    session: Session,
    analysis_id: str,
    *,
    claim_token: str,
    seconds: float,
    tool_calls: int,
    max_seconds: float = 180,
    max_tool_calls: int = 20,
) -> bool:
    """Reserve worst-case bounded work; callers commit before performing it.

    Reservations survive claim expiry and are intentionally never refunded.
    This conservative accounting bounds retries even when a worker is killed
    before recording how much of its reservation it actually used.
    """
    if (
        not math.isfinite(seconds)
        or not math.isfinite(max_seconds)
        or seconds < 0
        or max_seconds <= 0
        or not isinstance(tool_calls, int)
        or not isinstance(max_tool_calls, int)
        or tool_calls < 0
        or max_tool_calls < 1
    ):
        raise ValueError("budget reservations and limits must be finite and nonnegative")
    if not _lock_claim(session, analysis_id, claim_token):
        return False
    now = _database_now(session)
    result = session.execute(
        update(Analysis)
        .where(
            Analysis.id == analysis_id,
            Analysis.status == "running",
            Analysis.claim_token == claim_token,
            Analysis.lease_expires_at > now,
            Analysis.active_seconds_reserved + seconds <= max_seconds,
            Analysis.tool_calls_reserved + tool_calls <= max_tool_calls,
        )
        .values(
            active_seconds_reserved=Analysis.active_seconds_reserved + seconds,
            tool_calls_reserved=Analysis.tool_calls_reserved + tool_calls,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def save_snapshot(
    session: Session,
    analysis_id: str,
    *,
    claim_token: str,
    snapshot: dict[str, Any],
) -> bool:
    """Persist a graph snapshot only while this worker still owns the lease."""
    if not _lock_claim(session, analysis_id, claim_token):
        return False
    now = _database_now(session)
    result = session.execute(
        update(Analysis)
        .where(
            Analysis.id == analysis_id,
            Analysis.status == "running",
            Analysis.claim_token == claim_token,
            Analysis.lease_expires_at > now,
        )
        .values(graph_snapshot=snapshot, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def save_worker_state(
    session: Session,
    analysis_id: str,
    *,
    claim_token: str,
    snapshot: dict[str, Any],
    report: dict[str, Any] | None = None,
    raw_file: str | None = None,
) -> bool:
    """Fenced checkpoint for M2's M1 report and raw file handoff."""
    if not _lock_claim(session, analysis_id, claim_token):
        return False
    now = _database_now(session)
    values: dict[str, Any] = {"graph_snapshot": snapshot, "updated_at": now}
    if report is not None:
        values["report"] = report
    if raw_file is not None:
        values["raw_file"] = raw_file
    result = session.execute(
        update(Analysis)
        .where(
            Analysis.id == analysis_id,
            Analysis.status == "running",
            Analysis.claim_token == claim_token,
            Analysis.lease_expires_at > now,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def yield_analysis(
    session: Session,
    analysis_id: str,
    *,
    claim_token: str,
    snapshot: dict[str, Any],
    report: dict[str, Any],
) -> bool:
    """Queue a still-fenced M2 worker while preserving all durable reservations."""
    if not _lock_claim(session, analysis_id, claim_token):
        return False
    now = _database_now(session)
    result = session.execute(
        update(Analysis)
        .where(
            Analysis.id == analysis_id,
            Analysis.status == "running",
            Analysis.claim_token == claim_token,
            Analysis.lease_expires_at > now,
        )
        .values(
            status="queued",
            report=report,
            graph_snapshot=snapshot,
            error_code=None,
            message=None,
            claim_token=None,
            lease_expires_at=None,
            completed_at=None,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1
