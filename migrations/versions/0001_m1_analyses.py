"""Durable guest analyses, fenced leases, and cumulative execution budgets."""

import sqlalchemy as sa
from alembic import op

revision = "0001_m1_analyses"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("product_name", sa.String(300)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("report", sa.JSON()),
        sa.Column("error_code", sa.String(100)),
        sa.Column("message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("raw_file", sa.Text()),
        sa.Column("claim_token", sa.String(36)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("active_seconds_reserved", sa.Float(), nullable=False, server_default="0"),
        sa.Column("tool_calls_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("graph_snapshot", sa.JSON()),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'needs_input', 'completed', 'failed')",
            name="ck_analyses_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_analyses_attempt_count"),
        sa.CheckConstraint("length(token_hash) = 64", name="ck_analyses_token_hash"),
        sa.CheckConstraint("active_seconds_reserved >= 0", name="ck_analyses_active_budget"),
        sa.CheckConstraint("tool_calls_reserved >= 0", name="ck_analyses_tool_budget"),
        sa.CheckConstraint(
            "(status = 'running' AND claim_token IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR (status <> 'running' AND claim_token IS NULL AND lease_expires_at IS NULL)",
            name="ck_analyses_lease",
        ),
    )
    op.create_index(
        "ix_analyses_dispatch", "analyses", ["status", "lease_expires_at", "created_at"]
    )


def downgrade():
    op.drop_index("ix_analyses_dispatch", table_name="analyses")
    op.drop_table("analyses")
