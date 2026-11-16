"""Report names per material and the ledger of orders pasted into the Shop Online history file

Revision ID: 0007_sales_history
Revises: 0006_accounting_runs
Create Date: 2026-11-16
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_sales_history"
down_revision = "0006_accounting_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_item_name",
        sa.Column("material_number", sa.String(20), primary_key=True),
        sa.Column("item_name", sa.Text, nullable=False),
        sa.Column("size", sa.Text, nullable=False),
        sa.Column("variation", sa.Text, nullable=False),
        sa.Column("updated_by", sa.String(50), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "item_name <> '' AND size <> '' AND variation <> ''",
            name="ck_report_item_name_filled",
        ),
    )
    op.create_table(
        "sales_history_file_order",
        sa.Column(
            "generated_file_id",
            sa.Integer,
            sa.ForeignKey("generated_file.id"),
            primary_key=True,
        ),
        sa.Column("sales_order_id", sa.Integer, sa.ForeignKey("sales_order.id"), primary_key=True),
    )
    op.create_table(
        "sales_history_exported",
        sa.Column("sales_order_id", sa.Integer, sa.ForeignKey("sales_order.id"), primary_key=True),
        sa.Column(
            "generated_file_id", sa.Integer, sa.ForeignKey("generated_file.id"), nullable=False
        ),
        sa.Column("confirmed_by", sa.String(50), nullable=False),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_sales_history_exported_generated_file_id",
        "sales_history_exported",
        ["generated_file_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_sales_history_exported_generated_file_id", "sales_history_exported")
    op.drop_table("sales_history_exported")
    op.drop_table("sales_history_file_order")
    op.drop_table("report_item_name")
