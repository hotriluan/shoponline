"""Report views net of returns: issued returns subtract their sale lines; returns at invoice value

Revision ID: 0019_report_views_net_of_returns
Revises: 0018_return_sale_lines
Create Date: 2026-11-26

`report_sale_line` gains a third source, 'return': one negative row per sale line of an ISSUED
return, dated like the original order, so every report sums to the value really sold and matches
the Shop Online file month by month. `report_order_revenue.marketplace_value` subtracts the same
lines, `returned_value` becomes the invoice value returned including VAT (the same basis as
`invoice_value`), and `returned_marketplace_value` is the marketplace value returned. Downgrading
puts back the 0016 definitions.
"""

from alembic import op

revision = "0019_report_views_net_of_returns"
down_revision = "0018_return_sale_lines"
branch_labels = None
depends_on = None

SYSTEM_COLUMNS = """
    date_trunc('month', o.ordered_at)::date,
    o.ordered_at::date,
    s.platform,
    o.shop_code,
    s.division,
    COALESCE(ci.province, a.province),
    COALESCE(NULLIF(rn.item_name, ''), i.product_name),
    NULLIF(rn.size, ''),
    COALESCE(NULLIF(rn.variation, ''), i.variation_name),"""

SYSTEM_JOINS = """
JOIN sales_order o ON o.id = i.sales_order_id
JOIN shop s ON s.code = o.shop_code
LEFT JOIN report_item_name rn ON rn.material_number = i.material_number
LEFT JOIN customer_info ci
    ON ci.platform = o.platform AND ci.platform_order_id = o.platform_order_id
LEFT JOIN province_alias a ON a.raw_key = ci.place_key
WHERE o.ordered_at >= '2026-11-11 00:00' AND o.status <> 'CANCELLED'"""

HISTORY = (
    """
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
    'system'::text,"""
    + SYSTEM_COLUMNS
    + """
    i.quantity,
    (i.unit_price - i.unit_subsidy) * i.quantity,
    o.id::text
FROM sales_order_item i"""
    + SYSTEM_JOINS
)

SALE_LINE = (
    HISTORY
    + """
UNION ALL
SELECT
    'return'::text,"""
    + SYSTEM_COLUMNS
    + """
    -rl.quantity,
    -rl.customer_paid,
    o.id::text
FROM sales_return_sale_line rl
JOIN sales_return r ON r.id = rl.return_id AND r.status = 'ISSUED'
JOIN sales_order_item i ON i.id = rl.sales_order_item_id"""
    + SYSTEM_JOINS
    + "\n"
)

OLD_SALE_LINE = HISTORY + "\n"

REVENUE_HEAD = """
CREATE OR REPLACE VIEW report_order_revenue AS
SELECT
    o.id AS sales_order_id,
    o.platform,
    o.shop_code,
    date_trunc('month', o.ordered_at)::date AS period,
    o.status,"""

REVENUE_SOURCES = """
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
) st ON st.platform = o.platform AND st.platform_order_id = o.platform_order_id"""

WHERE = "\nWHERE o.ordered_at >= '2026-11-11 00:00' AND o.status <> 'CANCELLED'\n"

ORDER_REVENUE = (
    REVENUE_HEAD
    + """
    mk.value - COALESCE(rt.marketplace_value, 0) AS marketplace_value,
    inv.value AS invoice_value,
    st.value AS settled_value,
    COALESCE(rt.value, 0) AS returned_value,
    COALESCE(rt.marketplace_value, 0) AS returned_marketplace_value"""
    + REVENUE_SOURCES
    + """
LEFT JOIN (
    SELECT r.sales_order_id,
           SUM(r.returned_net + r.returned_tax)::bigint AS value,
           SUM(COALESCE(m.value, 0))::bigint AS marketplace_value
    FROM sales_return r
    LEFT JOIN (
        SELECT return_id, SUM(customer_paid)::bigint AS value
        FROM sales_return_sale_line GROUP BY return_id
    ) m ON m.return_id = r.id
    WHERE r.status = 'ISSUED'
    GROUP BY r.sales_order_id
) rt ON rt.sales_order_id = o.id"""
    + WHERE
)

OLD_ORDER_REVENUE = (
    REVENUE_HEAD
    + """
    mk.value AS marketplace_value,
    inv.value AS invoice_value,
    st.value AS settled_value,
    COALESCE(rt.value, 0) AS returned_value"""
    + REVENUE_SOURCES
    + """
LEFT JOIN (
    SELECT r.sales_order_id, SUM(l.amount_returned)::bigint AS value
    FROM sales_return r JOIN sales_return_line l ON l.return_id = r.id
    WHERE r.status = 'ISSUED'
    GROUP BY r.sales_order_id
) rt ON rt.sales_order_id = o.id"""
    + WHERE
)


def upgrade() -> None:
    # Dropped and created, both ways: each direction then states its view exactly, whatever
    # CREATE OR REPLACE would allow between the two column lists.
    op.execute("DROP VIEW report_order_revenue")
    op.execute("DROP VIEW report_sale_line")
    op.execute(SALE_LINE)
    op.execute(ORDER_REVENUE)


def downgrade() -> None:
    op.execute("DROP VIEW report_order_revenue")
    op.execute("DROP VIEW report_sale_line")
    op.execute(OLD_SALE_LINE)
    op.execute(OLD_ORDER_REVENUE)
