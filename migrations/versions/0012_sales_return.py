"""Invoice adjustments for returned orders: invoice item names, number counter, returns

Revision ID: 0012_sales_return
Revises: 0011_drive_connection
Create Date: 2026-11-25

Do not run `downgrade` on a machine that has issued returns: dropping sales_return and
document_counter lets numbers already printed be issued again (same warning as 0009). Restore a
backup instead.
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_sales_return"
down_revision = "0011_drive_connection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sap_tax_invoice", sa.Column("net_value_vnd", sa.BigInteger))
    op.add_column("sap_tax_invoice", sa.Column("tax_vnd", sa.BigInteger))

    op.create_table(
        "invoice_item_text",
        sa.Column("material_number", sa.String(20), primary_key=True),
        sa.Column("invoice_name", sa.Text, nullable=False),
        sa.Column("invoice_unit", sa.Text, nullable=False),
        sa.Column("stock_unit", sa.String(10), nullable=False, server_default="PC"),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("updated_by", sa.String(50), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "document_counter",
        sa.Column("doc_type", sa.String(30), primary_key=True),
        sa.Column("year", sa.Integer, primary_key=True),
        sa.Column("next_seq", sa.Integer, nullable=False),
    )

    op.create_table(
        "sales_return",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sales_order_id", sa.Integer, sa.ForeignKey("sales_order.id"), nullable=False),
        sa.Column("reason_kind", sa.String(10), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="ISSUED"),
        sa.Column("doc_year", sa.Integer, nullable=False),
        sa.Column("doc_seq", sa.Integer, nullable=False),
        sa.Column("doc_no", sa.String(60), nullable=False),
        sa.Column("full_return", sa.Boolean, nullable=False),
        sa.Column("delivery", sa.String(20), nullable=False),
        sa.Column("tax_invoice_doc", sa.String(20), nullable=False),
        sa.Column("invoice_symbol", sa.String(20), nullable=False),
        sa.Column("billing_date", sa.Date, nullable=False),
        sa.Column("invoice_net", sa.BigInteger, nullable=False),
        sa.Column("invoice_tax", sa.BigInteger, nullable=False),
        sa.Column("vat_rate", sa.Integer, nullable=False),
        sa.Column("returned_net", sa.BigInteger, nullable=False),
        sa.Column("returned_tax", sa.BigInteger, nullable=False),
        sa.Column("buyer_name", sa.Text, nullable=False),
        sa.Column("buyer_address", sa.Text, nullable=False),
        sa.Column("platform_name", sa.String(100), nullable=False),
        sa.Column("docx_file_id", sa.Integer, sa.ForeignKey("generated_file.id")),
        sa.Column("xlsx_file_id", sa.Integer, sa.ForeignKey("generated_file.id")),
        sa.Column("issued_by", sa.String(50), nullable=False),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("voided_by", sa.String(50)),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("void_reason", sa.Text),
        sa.UniqueConstraint("doc_no"),
        sa.UniqueConstraint("doc_year", "doc_seq"),
        sa.CheckConstraint("reason_kind IN ('CANCEL', 'RETURN')", name="ck_sales_return_reason"),
        sa.CheckConstraint("status IN ('ISSUED', 'VOID')", name="ck_sales_return_status"),
    )
    op.create_index(
        "uq_sales_return_one_issued",
        "sales_return",
        ["sales_order_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ISSUED'"),
    )

    op.create_table(
        "sales_return_line",
        sa.Column(
            "return_id",
            sa.Integer,
            sa.ForeignKey("sales_return.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("line_no", sa.Integer, primary_key=True),
        sa.Column("so_item_no", sa.Integer, nullable=False),
        sa.Column("material_number", sa.String(20), nullable=False),
        sa.Column("sap_name", sa.Text, nullable=False),
        sa.Column("invoice_name", sa.Text, nullable=False),
        sa.Column("invoice_unit", sa.Text, nullable=False),
        sa.Column("stock_unit", sa.String(10), nullable=False),
        sa.Column("invoice_qty", sa.Numeric(15, 3), nullable=False),
        sa.Column("return_qty", sa.Numeric(15, 3), nullable=False),
        sa.Column("unit_price", sa.BigInteger, nullable=False),
        sa.Column("amount_before", sa.BigInteger, nullable=False),
        sa.Column("amount_returned", sa.BigInteger, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sales_return_line")
    op.drop_index("uq_sales_return_one_issued", table_name="sales_return")
    op.drop_table("sales_return")
    op.drop_table("document_counter")
    op.drop_table("invoice_item_text")
    op.drop_column("sap_tax_invoice", "tax_vnd")
    op.drop_column("sap_tax_invoice", "net_value_vnd")
