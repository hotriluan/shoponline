"""History sales: lines of the accountants' file, province aliases, customer province

Revision ID: 0015_history_sales
Revises: 0014_shop
Create Date: 2026-11-25

The alias table is seeded with the 63 pre-merger provinces and the 34 current ones; customers
already stored get the province read from their address.
"""

import sqlalchemy as sa
from alembic import op

from shoponline.domain.provinces import seed_aliases
from shoponline.domain.report_names import province_of

revision = "0015_history_sales"
down_revision = "0014_shop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    alias = op.create_table(
        "province_alias",
        sa.Column("raw_key", sa.String(100), primary_key=True),
        sa.Column("province", sa.String(30), nullable=False),
        sa.Column("updated_by", sa.String(50), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.bulk_insert(
        alias,
        [{"raw_key": k, "province": v, "updated_by": "seed"} for k, v in seed_aliases().items()],
    )

    op.create_table(
        "history_sale_line",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("period", sa.Date, nullable=False),
        sa.Column("ordered_on", sa.Date),
        sa.Column("shop_code", sa.String(30), sa.ForeignKey("shop.code"), nullable=False),
        sa.Column("customer_name", sa.Text),
        sa.Column("customer_phone", sa.String(30)),
        sa.Column("city_raw", sa.Text),
        sa.Column("item_name", sa.Text),
        sa.Column("size", sa.Text),
        sa.Column("variation", sa.Text),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("customer_paid", sa.BigInteger, nullable=False),
        sa.Column("unit_price", sa.BigInteger),
        sa.Column("seller_discount", sa.BigInteger),
        sa.Column("shipping_fee", sa.BigInteger),
        sa.Column("order_key", sa.String(64), nullable=False),
        sa.Column("line_key", sa.String(64), nullable=False, unique=True),
        sa.Column("source_row", sa.Integer, nullable=False),
        sa.Column("import_batch_id", sa.Integer, sa.ForeignKey("import_batch.id"), nullable=False),
    )
    op.create_index("ix_history_sale_line_period", "history_sale_line", ["period"])
    op.create_index("ix_history_sale_line_shop_code", "history_sale_line", ["shop_code"])
    op.create_index("ix_history_sale_line_order_key", "history_sale_line", ["order_key"])
    op.create_index(
        "ix_history_sale_line_import_batch_id", "history_sale_line", ["import_batch_id"]
    )

    op.add_column("customer_info", sa.Column("province", sa.String(30)))
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, address FROM customer_info WHERE address IS NOT NULL")
    ).all()
    for row_id, address in rows:
        province = province_of(address)
        if province:
            bind.execute(
                sa.text("UPDATE customer_info SET province = :p WHERE id = :i"),
                {"p": province, "i": row_id},
            )


def downgrade() -> None:
    op.drop_column("customer_info", "province")
    op.drop_table("history_sale_line")
    op.drop_table("province_alias")
