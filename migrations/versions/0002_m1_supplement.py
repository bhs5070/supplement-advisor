"""Store one authorized guest supplement."""

import sqlalchemy as sa
from alembic import op

revision = "0002_m1_supplement"
down_revision = "0001_m1_analyses"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("analyses", sa.Column("supplemental_input", sa.JSON()))
    op.add_column(
        "analyses", sa.Column("supplemental_received_at", sa.DateTime(timezone=True))
    )


def downgrade():
    op.drop_column("analyses", "supplemental_received_at")
    op.drop_column("analyses", "supplemental_input")
