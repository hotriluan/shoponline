"""Money Lazada paid out, typed in by hand: platform_settlement rows with no import batch

Revision ID: 0013_manual_settlement
Revises: 0012_sales_return
Create Date: 2026-11-25

The Lazada balance file carries no order id, so the amounts are typed in. A typed row has no
import_batch_id and an entered_by; a file row keeps its batch.
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_manual_settlement"
down_revision = "0012_sales_return"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("platform_settlement", "import_batch_id", nullable=True)
    op.add_column(
        "platform_settlement",
        sa.Column("source", sa.String(10), nullable=False, server_default="file"),
    )
    op.add_column("platform_settlement", sa.Column("entered_by", sa.String(50)))
    op.create_check_constraint(
        "ck_platform_settlement_source",
        "platform_settlement",
        "(source = 'file' AND import_batch_id IS NOT NULL)"
        " OR (source = 'manual' AND entered_by IS NOT NULL)",
    )


def downgrade() -> None:
    op.execute("DELETE FROM platform_settlement WHERE source = 'manual'")
    op.drop_constraint("ck_platform_settlement_source", "platform_settlement")
    op.drop_column("platform_settlement", "entered_by")
    op.drop_column("platform_settlement", "source")
    op.alter_column("platform_settlement", "import_batch_id", nullable=False)
