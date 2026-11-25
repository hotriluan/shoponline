"""Report views: one row per sold item (history and system), one per system order

Revision ID: 0016_report_views
Revises: 0015_history_sales
Create Date: 2026-11-25

The views live in schema public so that pg_dump and a restore carry them with the data. The
moment the system's own orders take over from the history file (2026-11-11) is written in the SQL
and pinned to shoponline.reports.REPORTING_CUTOVER by a test.
"""

import sqlalchemy as sa
from alembic import op

from shoponline.domain.provinces import fold_key, place_key

revision = "0016_report_views"
down_revision = "0015_history_sales"
branch_labels = None
depends_on = None

SALE_LINE = """
CREATE OR REPLACE VIEW report_sale_line AS
SELECT
    'history'::text AS source,
    h.period,
    h.ordered_on,
    s.platform,
    h.shop_code,
    s.division,
    a.province,
    h.item_name,
    h.size,
    h.variation,
    h.quantity,
    h.customer_paid,
    h.order_key::text AS order_key
FROM history_sale_line h
JOIN shop s ON s.code = h.shop_code
LEFT JOIN province_alias a ON a.raw_key = h.city_key
UNION ALL
SELECT
    'system'::text,
    date_trunc('month', o.ordered_at)::date,
    o.ordered_at::date,
    s.platform,
    o.shop_code,
    s.division,
    COALESCE(ci.province, a.province),
    COALESCE(NULLIF(rn.item_name, ''), i.product_name),
    NULLIF(rn.size, ''),
    COALESCE(NULLIF(rn.variation, ''), i.variation_name),
    i.quantity,
    (i.unit_price - i.unit_subsidy) * i.quantity,
    o.id::text
FROM sales_order_item i
JOIN sales_order o ON o.id = i.sales_order_id
JOIN shop s ON s.code = o.shop_code
LEFT JOIN report_item_name rn ON rn.material_number = i.material_number
LEFT JOIN customer_info ci
    ON ci.platform = o.platform AND ci.platform_order_id = o.platform_order_id
LEFT JOIN province_alias a ON a.raw_key = ci.place_key
WHERE o.ordered_at >= '2026-11-11 00:00' AND o.status <> 'CANCELLED'
"""

ORDER_REVENUE = """
CREATE OR REPLACE VIEW report_order_revenue AS
SELECT
    o.id AS sales_order_id,
    o.platform,
    o.shop_code,
    date_trunc('month', o.ordered_at)::date AS period,
    o.status,
    mk.value AS marketplace_value,
    inv.value AS invoice_value,
    st.value AS settled_value,
    COALESCE(rt.value, 0) AS returned_value
FROM sales_order o
LEFT JOIN (
    SELECT sales_order_id, SUM((unit_price - unit_subsidy) * quantity)::bigint AS value
    FROM sales_order_item GROUP BY sales_order_id
) mk ON mk.sales_order_id = o.id
LEFT JOIN (
    SELECT delivery,
           CASE WHEN net_value_vnd IS NULL AND tax_vnd IS NULL THEN NULL
                ELSE COALESCE(net_value_vnd, 0) + COALESCE(tax_vnd, 0) END AS value
    FROM sap_tax_invoice
) inv ON inv.delivery = o.do_number
LEFT JOIN (
    SELECT platform, platform_order_id, SUM(amount)::bigint AS value
    FROM platform_settlement GROUP BY platform, platform_order_id
) st ON st.platform = o.platform AND st.platform_order_id = o.platform_order_id
LEFT JOIN (
    SELECT r.sales_order_id, SUM(l.amount_returned)::bigint AS value
    FROM sales_return r JOIN sales_return_line l ON l.return_id = r.id
    WHERE r.status = 'ISSUED'
    GROUP BY r.sales_order_id
) rt ON rt.sales_order_id = o.id
WHERE o.ordered_at >= '2026-11-11 00:00' AND o.status <> 'CANCELLED'
"""


def upgrade() -> None:
    op.add_column("history_sale_line", sa.Column("city_key", sa.String(100)))
    op.add_column("customer_info", sa.Column("place_key", sa.String(100)))
    bind = op.get_bind()
    for table, source, target, fn in (
        ("history_sale_line", "city_raw", "city_key", fold_key),
        ("customer_info", "address", "place_key", place_key),
    ):
        rows = bind.execute(
            sa.text(f"SELECT id, {source} FROM {table} WHERE {source} IS NOT NULL")
        ).all()
        for row_id, value in rows:
            key = fn(value)
            if key:
                bind.execute(
                    sa.text(f"UPDATE {table} SET {target} = :k WHERE id = :i"),
                    {"k": key, "i": row_id},
                )
    op.execute(SALE_LINE)
    op.execute(ORDER_REVENUE)


def downgrade() -> None:
    op.execute("DROP VIEW report_order_revenue")
    op.execute("DROP VIEW report_sale_line")
    op.drop_column("customer_info", "place_key")
    op.drop_column("history_sale_line", "city_key")
