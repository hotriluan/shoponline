"""SAP sales orders seen in zrsd001: SO number, PO No, value, items

Revision ID: 0003_sap_so_ref
Revises: 0002_core_schema
Create Date: 2026-11-11
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_sap_so_ref"
down_revision = "0002_core_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sap_so_ref",
        sa.Column("so_number", sa.String(20), primary_key=True),
        sa.Column("po_no", sa.String(40), nullable=False),
        sa.Column("sold_to", sa.String(20), nullable=False),
        sa.Column("doc_date", sa.Date, nullable=False),
        sa.Column("net_value_incl", sa.BigInteger, nullable=False),
        sa.Column("import_batch_id", sa.Integer, sa.ForeignKey("import_batch.id")),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_sap_so_ref_po_no", "sap_so_ref", ["po_no"])
    op.create_index("ix_sap_so_ref_sold_to_date", "sap_so_ref", ["sold_to", "doc_date"])
    op.create_table(
        "sap_so_ref_item",
        sa.Column(
            "so_number",
            sa.String(20),
            sa.ForeignKey("sap_so_ref.so_number", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("item_no", sa.Integer, primary_key=True),
        sa.Column("material_number", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Numeric(15, 3), nullable=False),
        sa.Column("net_value_incl", sa.BigInteger, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sap_so_ref_item")
    op.drop_table("sap_so_ref")
