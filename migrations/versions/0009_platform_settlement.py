"""Money the platform paid for each order, read from Shopee/TikTok settlement files

Revision ID: 0009_platform_settlement
Revises: 0008_sap_tax_invoice
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_platform_settlement"
down_revision = "0008_sap_tax_invoice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_settlement",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("platform_order_id", sa.String(40), nullable=False),
        sa.Column("line_key", sa.String(200), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("settled_at", sa.DateTime, nullable=False),
        sa.Column(
            "import_batch_id", sa.Integer, sa.ForeignKey("import_batch.id"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("platform", "line_key"),
    )
    op.create_index(
        "ix_platform_settlement_order", "platform_settlement", ["platform", "platform_order_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_platform_settlement_order", table_name="platform_settlement")
    op.drop_table("platform_settlement")
