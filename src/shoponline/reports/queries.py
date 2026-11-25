"""Aggregates for the management reports, read from the views report_sale_line (every sold item,
history and system) and report_order_revenue (the three revenue figures per system order).

Every function takes the same Filters, so a page and its Excel export show the same numbers.
Figures that history cannot give (invoice, money received) are None, never 0, for months
without system orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from shoponline.domain import states
from shoponline.reports import REPORTING_CUTOVER

UNKNOWN_PROVINCE = "Chưa xác định"
CUTOVER_MONTH = REPORTING_CUTOVER.date().replace(day=1)


@dataclass(frozen=True)
class Filters:
    """Months are the first day of the month; empty tuples mean every platform / shop."""

    from_period: date | None = None
    to_period: date | None = None
    platforms: tuple[str, ...] = ()
    shop_codes: tuple[str, ...] = ()


def _where(f: Filters, params: dict, *, prefix: str = "") -> str:
    clauses = ["TRUE"]
    if f.from_period:
        clauses.append(f"{prefix}period >= :from_period")
        params["from_period"] = f.from_period
    if f.to_period:
        clauses.append(f"{prefix}period <= :to_period")
        params["to_period"] = f.to_period
    if f.platforms:
        clauses.append(f"{prefix}platform = ANY(:platforms)")
        params["platforms"] = list(f.platforms)
    if f.shop_codes:
        clauses.append(f"{prefix}shop_code = ANY(:shop_codes)")
        params["shop_codes"] = list(f.shop_codes)
    return " AND ".join(clauses)


def _run(session: Session, sql: str, params: dict) -> list[dict]:
    return [dict(r) for r in session.execute(text(sql), params).mappings()]


def monthly_overview(session: Session, f: Filters) -> list[dict]:
    """One row per month: marketplace value (history and system), invoice revenue, money
    received, the gap between them, orders, average order, returns.

    `subsidy_gap` (marketplace - invoice) is summed over the orders that have an invoice and
    `platform_fee` (invoice - received) over the orders that have both invoice and money, so a
    missing figure never shows as a fee. `missing_invoice` / `missing_settlement` count the
    delivered orders still waiting for each."""
    params: dict = {"delivered": states.DELIVERED}
    sales = _run(
        session,
        f"""
        SELECT period, SUM(customer_paid)::bigint AS marketplace_value,
               COUNT(DISTINCT order_key) AS orders
        FROM report_sale_line WHERE {_where(f, params)}
        GROUP BY period ORDER BY period
        """,
        params,
    )
    params = {"delivered": states.DELIVERED}
    revenue = {
        row["period"]: row
        for row in _run(
            session,
            f"""
            SELECT period,
                   SUM(invoice_value)::bigint AS invoice_value,
                   SUM(settled_value)::bigint AS settled_value,
                   SUM(marketplace_value - invoice_value)
                       FILTER (WHERE invoice_value IS NOT NULL)::bigint AS subsidy_gap,
                   SUM(invoice_value - settled_value)
                       FILTER (WHERE invoice_value IS NOT NULL
                               AND settled_value IS NOT NULL)::bigint AS platform_fee,
                   SUM(returned_value)::bigint AS returned_value,
                   COUNT(*) FILTER (WHERE status = :delivered
                                    AND invoice_value IS NULL) AS missing_invoice,
                   COUNT(*) FILTER (WHERE status = :delivered
                                    AND settled_value IS NULL) AS missing_settlement
            FROM report_order_revenue WHERE {_where(f, params)}
            GROUP BY period
            """,
            params,
        )
    }
    rows = []
    for sale in sales:
        extra = revenue.get(sale["period"])
        row = {**sale, "average_order": sale["marketplace_value"] // sale["orders"]}
        for key in (
            "invoice_value",
            "settled_value",
            "subsidy_gap",
            "platform_fee",
            "returned_value",
            "missing_invoice",
            "missing_settlement",
        ):
            row[key] = extra[key] if extra else None
        invoice = row["invoice_value"]
        row["return_rate"] = (row["returned_value"] / invoice) if invoice else None
        rows.append(row)
    return rows


def by_channel(session: Session, f: Filters) -> list[dict]:
    params: dict = {}
    return _run(
        session,
        f"""
        SELECT platform, shop_code, division,
               SUM(quantity)::bigint AS quantity,
               SUM(customer_paid)::bigint AS marketplace_value,
               COUNT(DISTINCT order_key) AS orders
        FROM report_sale_line WHERE {_where(f, params)}
        GROUP BY platform, shop_code, division
        ORDER BY marketplace_value DESC
        """,
        params,
    )


def by_product(session: Session, f: Filters, limit: int | None = None) -> list[dict]:
    params: dict = {}
    sql = f"""
        SELECT COALESCE(item_name, '') AS item_name, COALESCE(size, '') AS size,
               COALESCE(variation, '') AS variation,
               SUM(quantity)::bigint AS quantity,
               SUM(customer_paid)::bigint AS marketplace_value
        FROM report_sale_line WHERE {_where(f, params)}
        GROUP BY 1, 2, 3
        ORDER BY marketplace_value DESC, item_name, size, variation
    """
    if limit:
        sql += " LIMIT :limit"
        params["limit"] = limit
    return _run(session, sql, params)


def by_province(session: Session, f: Filters) -> list[dict]:
    params: dict = {"unknown": UNKNOWN_PROVINCE}
    return _run(
        session,
        f"""
        SELECT COALESCE(province, :unknown) AS province,
               SUM(quantity)::bigint AS quantity,
               SUM(customer_paid)::bigint AS marketplace_value,
               COUNT(DISTINCT order_key) AS orders
        FROM report_sale_line WHERE {_where(f, params)}
        GROUP BY 1
        ORDER BY (COALESCE(province, :unknown) = :unknown), marketplace_value DESC
        """,
        params,
    )


def returns(session: Session, f: Filters) -> list[dict]:
    """Issued return documents by month and reason (CANCEL / RETURN), system orders only."""
    params: dict = {}
    return _run(
        session,
        f"""
        SELECT v.period, r.reason_kind,
               COUNT(DISTINCT r.id) AS documents,
               SUM(l.amount_returned)::bigint AS returned_value
        FROM sales_return r
        JOIN sales_return_line l ON l.return_id = r.id
        JOIN report_order_revenue v ON v.sales_order_id = r.sales_order_id
        WHERE r.status = 'ISSUED' AND {_where(f, params, prefix="v.")}
        GROUP BY v.period, r.reason_kind
        ORDER BY v.period, r.reason_kind
        """,
        params,
    )


def data_notes(session: Session, f: Filters) -> list[str]:
    """Warnings about what the figures leave out, for the page and the Excel files."""
    notes: list[str] = []
    params: dict = {}
    counts = _run(
        session,
        f"""
        SELECT COUNT(*) FILTER (WHERE source = 'history') AS history_lines,
               COUNT(*) FILTER (WHERE source = 'history'
                                AND period >= :cutover_month) AS history_cutover_lines,
               COUNT(*) FILTER (WHERE source = 'system'
                                AND period = :cutover_month) AS system_cutover_lines
        FROM report_sale_line WHERE {_where(f, params)}
        """,
        {**params, "cutover_month": CUTOVER_MONTH},
    )[0]
    if counts["history_lines"]:
        notes.append(
            "Số liệu trước 11/11/2026 lấy từ file lịch sử của kế toán: chỉ có giá trị trên sàn, "
            "không có doanh thu hóa đơn và tiền thực nhận."
        )
    covers_cutover_month = (f.from_period is None or f.from_period <= CUTOVER_MONTH) and (
        f.to_period is None or f.to_period >= CUTOVER_MONTH
    )
    if (
        covers_cutover_month
        and counts["system_cutover_lines"]
        and not counts["history_cutover_lines"]
    ):
        notes.append(
            f"Tháng {CUTOVER_MONTH.month}/{CUTOVER_MONTH.year} thiếu đơn từ ngày 01 đến "
            f"{REPORTING_CUTOVER.day - 1}/{CUTOVER_MONTH.month}: chưa nạp phần đó từ file của "
            "kế toán."
        )
    return notes


def monthly_by_channel(session: Session, f: Filters) -> list[dict]:
    """Marketplace value by month and shop, for the stacked chart."""
    params: dict = {}
    return _run(
        session,
        f"""
        SELECT period, shop_code, division, SUM(customer_paid)::bigint AS marketplace_value
        FROM report_sale_line WHERE {_where(f, params)}
        GROUP BY period, shop_code, division ORDER BY period, shop_code
        """,
        params,
    )
