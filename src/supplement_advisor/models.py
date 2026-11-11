"""Durable guest requests, reports, and fenced worker leases."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'needs_input', 'completed', 'failed')",
            name="ck_analyses_status",
        ),
        CheckConstraint("mode IN ('collection', 'evidence_review')", name="ck_analyses_mode"),
        CheckConstraint("attempt_count >= 0", name="ck_analyses_attempt_count"),
        CheckConstraint("active_seconds_reserved >= 0", name="ck_analyses_active_budget"),
        CheckConstraint("tool_calls_reserved >= 0", name="ck_analyses_tool_budget"),
        CheckConstraint("length(token_hash) = 64", name="ck_analyses_token_hash"),
        CheckConstraint(
            "(status = 'running' AND claim_token IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR (status <> 'running' AND claim_token IS NULL AND lease_expires_at IS NULL)",
            name="ck_analyses_lease",
        ),
        Index("ix_analyses_dispatch", "status", "lease_expires_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(30), nullable=False, default="collection", server_default="collection")
    product_name: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    report: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(100))
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_file: Mapped[str | None] = mapped_column(Text)
    claim_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_seconds_reserved: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    tool_calls_reserved: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    graph_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    supplemental_input: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    supplemental_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<Analysis id={self.id!r} status={self.status!r}>"
