"""Indexes behind the quick order lookup

Revision ID: 0020_order_lookup_indexes
Revises: 0019_report_views_net_of_returns
Create Date: 2026-11-26

The lookup box takes an order id without knowing its platform, a DO, and an invoice number
without its leading zeros; none of these could use an existing index.
"""

from alembic import op

revision = "0020_order_lookup_indexes"
down_revision = "0019_report_views_net_of_returns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_sales_order_platform_order_id_upper "
        "ON sales_order (upper(platform_order_id))"
    )
    op.execute("CREATE INDEX ix_sales_order_do_number ON sales_order (do_number)")
    op.execute(
        "CREATE INDEX ix_sap_tax_invoice_doc_trimmed "
        "ON sap_tax_invoice (ltrim(tax_invoice_doc, '0'))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_sap_tax_invoice_doc_trimmed")
    op.execute("DROP INDEX ix_sales_order_do_number")
    op.execute("DROP INDEX ix_sales_order_platform_order_id_upper")
