"""Add durable M2 evidence review mode."""

import sqlalchemy as sa
from alembic import op

revision = "0003_m2_evidence_mode"
down_revision = "0002_m1_supplement"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("analyses") as batch:
        batch.add_column(
            sa.Column("mode", sa.String(length=30), server_default="collection", nullable=False)
        )
        batch.create_check_constraint("ck_analyses_mode", "mode IN ('collection', 'evidence_review')")


def downgrade():
    with op.batch_alter_table("analyses") as batch:
        batch.drop_constraint("ck_analyses_mode", type_="check")
        batch.drop_column("mode")
