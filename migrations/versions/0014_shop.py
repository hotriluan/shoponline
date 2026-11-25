"""Shops: every order records the shop that sold it

Revision ID: 0014_shop
Revises: 0013_manual_settlement
Create Date: 2026-11-25

Existing orders are given the platform's active shop: before this change each platform had one
shop, so that is where they came from.
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_shop"
down_revision = "0013_manual_settlement"
branch_labels = None
depends_on = None

# code, platform, division (written as is into the Shop Online history file), active, sort order
SHOPS = (
    ("SHOPEE_BD", "SHOPEE", "Shopee Bình Dương", True, 1),
    ("SHOPEE_PGT", "SHOPEE", "Shopee PGT", False, 2),
    ("SHOPEE_DN", "SHOPEE", "Shopee Da Nang", False, 3),
    ("TIKTOK_BD", "TIKTOK", "tiktok Bình Dương", True, 1),
    ("LAZADA_MALL", "LAZADA", "Lazada Mall", True, 1),
    ("LAZADA", "LAZADA", "Lazada", False, 2),
)


def upgrade() -> None:
    shop = op.create_table(
        "shop",
        sa.Column("code", sa.String(30), primary_key=True),
        sa.Column(
            "platform", sa.String(20), sa.ForeignKey("platform_setting.platform"), nullable=False
        ),
        sa.Column("division", sa.String(50), nullable=False, unique=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    )
    op.bulk_insert(
        shop,
        [
            {"code": c, "platform": p, "division": d, "active": a, "sort_order": n}
            for c, p, d, a, n in SHOPS
        ],
    )

    op.add_column("sales_order", sa.Column("shop_code", sa.String(30)))
    op.execute(
        """
        UPDATE sales_order o SET shop_code = (
            SELECT s.code FROM shop s
            WHERE s.platform = o.platform AND s.active
            ORDER BY s.sort_order LIMIT 1
        )
        """
    )
    op.alter_column("sales_order", "shop_code", nullable=False)
    op.create_foreign_key("fk_sales_order_shop", "sales_order", "shop", ["shop_code"], ["code"])
    op.create_index("ix_sales_order_shop_code", "sales_order", ["shop_code"])

    op.add_column("import_batch", sa.Column("shop_code", sa.String(30)))
    op.create_foreign_key("fk_import_batch_shop", "import_batch", "shop", ["shop_code"], ["code"])


def downgrade() -> None:
    op.drop_constraint("fk_import_batch_shop", "import_batch")
    op.drop_column("import_batch", "shop_code")
    op.drop_index("ix_sales_order_shop_code", table_name="sales_order")
    op.drop_constraint("fk_sales_order_shop", "sales_order")
    op.drop_column("sales_order", "shop_code")
    op.drop_table("shop")
