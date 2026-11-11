"""core schema: platforms, users, imports, orders, mapping, customers, events

Revision ID: 0002_core_schema
Revises: 0001_initial
Create Date: 2026-11-11
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_core_schema"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    platform = op.create_table(
        "platform_setting",
        sa.Column("platform", sa.String(20), primary_key=True),
        sa.Column("display_name", sa.String(50), nullable=False),
        sa.Column("sap_customer", sa.String(20), nullable=False, unique=True),
        sa.Column("mode", sa.String(10), nullable=False, server_default="manual"),
        sa.CheckConstraint("mode IN ('manual', 'shadow', 'live')", name="ck_platform_mode"),
    )
    op.bulk_insert(
        platform,
        [
            {
                "platform": "SHOPEE",
                "display_name": "SHOPEE",
                "sap_customer": "1200001145",
                "mode": "manual",
            },
            {
                "platform": "LAZADA",
                "display_name": "LAZADA",
                "sap_customer": "1200001118",
                "mode": "manual",
            },
            {
                "platform": "TIKTOK",
                "display_name": "TIKTOK",
                "sap_customer": "1200001146",
                "mode": "manual",
            },
        ],
    )

    op.create_table(
        "app_user",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(300), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('admin', 'viewer')", name="ck_app_user_role"),
    )

    op.create_table(
        "import_batch",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("platform", sa.String(20)),
        sa.Column("file_name", sa.String(300), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("stored_path", sa.String(500), nullable=False),
        sa.Column("imported_by", sa.String(50), nullable=False),
        sa.Column("imported_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("new_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("unchanged_count", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_table(
        "generated_file",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("file_name", sa.String(300), nullable=False),
        sa.Column("stored_path", sa.String(500), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(50), nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "order_batch",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "platform", sa.String(20), sa.ForeignKey("platform_setting.platform"), nullable=False
        ),
        sa.Column("processing_date", sa.Date, nullable=False),
        sa.Column("gi_date", sa.Date, nullable=False),
        sa.Column("confirmed_by", sa.String(50)),
        sa.Column("confirmed_at", TS),
        sa.UniqueConstraint("platform", "processing_date"),
    )

    op.create_table(
        "sales_order",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "platform", sa.String(20), sa.ForeignKey("platform_setting.platform"), nullable=False
        ),
        sa.Column("platform_order_id", sa.String(40), nullable=False),
        sa.Column("order_batch_id", sa.Integer, sa.ForeignKey("order_batch.id"), nullable=False),
        sa.Column("ordered_at", sa.DateTime, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("status_reason", sa.Text),
        sa.Column("review_note", sa.Text),
        sa.Column("so_number", sa.String(20)),
        sa.Column("do_number", sa.String(20)),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("platform", "platform_order_id"),
        sa.CheckConstraint(
            "status IN ('NEW', 'READY', 'SO_LINKED', 'DELIVERED', "
            "'MAPPING_ERROR', 'NEED_REVIEW', 'CANCELLED')",
            name="ck_sales_order_status",
        ),
    )
    op.create_index("ix_sales_order_so_number", "sales_order", ["so_number"])
    op.create_index("ix_sales_order_batch", "sales_order", ["order_batch_id"])

    op.create_table(
        "sales_order_item",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "sales_order_id",
            sa.Integer,
            sa.ForeignKey("sales_order.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column("product_name", sa.Text, nullable=False),
        sa.Column("variation_name", sa.Text, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_price", sa.BigInteger, nullable=False),
        sa.Column("unit_subsidy", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("material_number", sa.String(20)),
        sa.Column("sap_name", sa.Text),
        sa.CheckConstraint("quantity > 0", name="ck_item_quantity"),
        sa.CheckConstraint("unit_price >= 0 AND unit_subsidy >= 0", name="ck_item_money"),
    )
    op.create_index("ix_sales_order_item_order", "sales_order_item", ["sales_order_id"])

    op.create_table(
        "sku_mapping",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "platform", sa.String(20), sa.ForeignKey("platform_setting.platform"), nullable=False
        ),
        sa.Column("product_key", sa.Text, nullable=False),
        sa.Column("variation_key", sa.Text, nullable=False),
        sa.Column("product_name", sa.Text, nullable=False),
        sa.Column("variation_name", sa.Text, nullable=False),
        sa.Column("material_number", sa.String(20), nullable=False),
        sa.Column("sap_name", sa.Text, nullable=False),
        sa.Column("updated_by", sa.String(50), nullable=False),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("platform", "product_key", "variation_key"),
    )

    op.create_table(
        "customer_info",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "platform", sa.String(20), sa.ForeignKey("platform_setting.platform"), nullable=False
        ),
        sa.Column("platform_order_id", sa.String(40), nullable=False),
        sa.Column("customer_name", sa.Text),
        sa.Column("address", sa.Text),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("platform", "platform_order_id"),
    )

    op.create_table(
        "event_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("actor", sa.String(50), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("platform", sa.String(20)),
        sa.Column("platform_order_id", sa.String(40)),
        sa.Column("detail", sa.Text),
    )
    op.create_index("ix_event_log_platform_order_id", "event_log", ["platform_order_id"])


def downgrade() -> None:
    for table in (
        "event_log",
        "customer_info",
        "sku_mapping",
        "sales_order_item",
        "sales_order",
        "order_batch",
        "generated_file",
        "import_batch",
        "app_user",
        "platform_setting",
    ):
        op.drop_table(table)
