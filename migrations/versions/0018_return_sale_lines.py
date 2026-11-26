"""Return sale lines: what a return takes off each platform order line, and its history-file rows

Revision ID: 0018_return_sale_lines
Revises: 0017_customer_address_source
Create Date: 2026-11-26

`sales_return_sale_line` holds, per platform order line, the quantity a return takes back and its
value at the marketplace price, so the Shop Online file and the reports read one source.
`sales_history_file_return` records which downloaded file carries a return's rows (ISSUE: the
negative rows, VOID: the rows that reverse them after the return is cancelled), and
`sales_return_history_exported` records the rows confirmed as pasted, mirroring the two order
tables of 0007. Downgrading drops only these three tables; `sales_return` is untouched.
"""

import sqlalchemy as sa
from alembic import op

revision = "0018_return_sale_lines"
down_revision = "0017_customer_address_source"
branch_labels = None
depends_on = None

KINDS = "kind IN ('ISSUE', 'VOID')"


def upgrade() -> None:
    op.create_table(
        "sales_return_sale_line",
        sa.Column(
            "return_id",
            sa.Integer,
            sa.ForeignKey("sales_return.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "sales_order_item_id",
            sa.Integer,
            sa.ForeignKey("sales_order_item.id"),
            primary_key=True,
        ),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("customer_paid", sa.BigInteger, nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_sales_return_sale_line_quantity"),
        sa.CheckConstraint("customer_paid >= 0", name="ck_sales_return_sale_line_paid"),
    )
    op.create_table(
        "sales_history_file_return",
        sa.Column(
            "generated_file_id",
            sa.Integer,
            sa.ForeignKey("generated_file.id"),
            primary_key=True,
        ),
        sa.Column("return_id", sa.Integer, sa.ForeignKey("sales_return.id"), primary_key=True),
        sa.Column("kind", sa.String(10), primary_key=True),
        sa.CheckConstraint(KINDS, name="ck_sales_history_file_return_kind"),
    )
    op.create_table(
        "sales_return_history_exported",
        sa.Column("return_id", sa.Integer, sa.ForeignKey("sales_return.id"), primary_key=True),
        sa.Column("kind", sa.String(10), primary_key=True),
        sa.Column(
            "generated_file_id",
            sa.Integer,
            sa.ForeignKey("generated_file.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("confirmed_by", sa.String(50), nullable=False),
        sa.Column(
            "confirmed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(KINDS, name="ck_sales_return_history_exported_kind"),
    )


def downgrade() -> None:
    op.drop_table("sales_return_history_exported")
    op.drop_table("sales_history_file_return")
    op.drop_table("sales_return_sale_line")
