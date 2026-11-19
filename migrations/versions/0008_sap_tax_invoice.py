"""Tax invoice number of each platform delivery, read from zrsd003

Revision ID: 0008_sap_tax_invoice
Revises: 0007_sales_history
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_sap_tax_invoice"
down_revision = "0007_sales_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sap_tax_invoice",
        sa.Column("delivery", sa.String(20), primary_key=True),
        sa.Column("tax_invoice_doc", sa.String(20), nullable=False),
        sa.Column("billing_doc", sa.String(20), nullable=False),
        sa.Column("billing_date", sa.Date, nullable=False),
        sa.Column("bill_to", sa.String(20), nullable=False),
        sa.Column("import_batch_id", sa.Integer, sa.ForeignKey("import_batch.id")),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("sap_tax_invoice")
