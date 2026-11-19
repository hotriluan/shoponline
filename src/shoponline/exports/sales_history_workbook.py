"""Rows to append to the accountants' `Shop Online 2022-2026` history file: sheet1's 17
columns, then the order id, the tax invoice number of the order's DO and the money the platform
paid for the order (20 columns).

Every DELIVERED order not yet confirmed as pasted into that file (sales_history_exported) and
ordered on or before a given day goes in, one row per order line. An order missing a value the
file needs (customer name, a province in its address, the report name of a material, the tax
invoice of its DO read from zrsd003, for Shopee and TikTok the settlement paid by the platform)
is reported as blocked instead of guessed. The invoice is issued after the DO and the platform
settles days after delivery, so an order waiting for either is the normal state in between.
Columns H and I are the file's own relative formulas, so the rows can be pasted below the last
row of sheet1 as they are.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, selectinload

from shoponline.db.models import (
    CustomerInfo,
    PlatformSettlement,
    ReportItemName,
    SalesHistoryExported,
    SalesOrder,
    SapTaxInvoice,
)
from shoponline.domain import states
from shoponline.domain.report_names import province_of

SHEET = "sheet1"
# Row 1 of sheet1, as written there (note the trailing space of "unitPrice ").
COLUMNS = (
    "Division",
    "createTime",
    "month",
    "year",
    "billingName",
    "billingPhone",
    "billingCity",
    "Cust + time",
    "Transaction",
    "Customer paid",
    "unitPrice ",
    "sellerDiscountTotal",
    "shippingFee",
    "Quantity",
    "itemName",
    "Product Classification SKU",
    "variation",
    "Mã đơn",
    "Tax Invoice Doc.",
    "Tiền Vô",
)
DIVISION = {
    "SHOPEE": "Shopee Bình Dương",
    "TIKTOK": "tiktok Bình Dương",
    "LAZADA": "Lazada Mall",
}
HIDDEN_PHONE = "******"
MONEY_FORMAT = "#,##0"
MONEY_COLUMNS = ("J", "K", "T")
TEXT_COLUMNS = ("R", "S")

# Why an order is blocked; the kind tells the page where it is fixed.
CUSTOMER = "customer"
REPORT_NAME = "report_name"
DIVISION_MISSING = "division"
TAX_INVOICE = "tax_invoice"
SETTLEMENT = "settlement"
# Platforms whose settlement files give money per order. Lazada's does not: its column stays empty.
SETTLED_PLATFORMS = ("SHOPEE", "TIKTOK")


@dataclass(frozen=True)
class Reason:
    kind: str
    text: str


@dataclass(frozen=True)
class BlockedOrder:
    platform: str
    platform_order_id: str
    order_batch_id: int
    ordered_at: datetime
    reasons: tuple[Reason, ...]


@dataclass(frozen=True)
class HistoryRow:
    division: str
    ordered_at: datetime
    billing_name: str
    billing_city: str
    customer_paid: int
    unit_price: int
    quantity: int
    item_name: str
    size: str
    variation: str
    platform_order_id: str
    tax_invoice_doc: str
    settlement: int | None = None  # the order's total, on its first line only


@dataclass
class HistoryRows:
    rows: list[HistoryRow] = field(default_factory=list)
    order_ids: list[int] = field(default_factory=list)
    blocked: list[BlockedOrder] = field(default_factory=list)


def history_file_name(day: date) -> str:
    return f"SHOP ONLINE LỊCH SỬ {day:%d%m%y}.xlsx"


def pending_orders(session: Session, until: date) -> list[SalesOrder]:
    """DELIVERED orders ordered on or before `until`, not yet confirmed into the history file.

    ordered_at is the platform's local (Vietnam) time without zone, so it compares as is.
    """
    confirmed = exists().where(SalesHistoryExported.sales_order_id == SalesOrder.id)
    return list(
        session.scalars(
            select(SalesOrder)
            .where(
                SalesOrder.status == states.DELIVERED,
                ~confirmed,
                SalesOrder.ordered_at < datetime.combine(until + timedelta(days=1), time()),
            )
            .options(selectinload(SalesOrder.items))
            .order_by(SalesOrder.ordered_at, SalesOrder.platform_order_id)
        )
    )


def collect_rows(session: Session, until: date) -> HistoryRows:
    orders = pending_orders(session, until)
    result = HistoryRows()
    if not orders:
        return result
    wanted = {(o.platform, o.platform_order_id) for o in orders}
    customers = {
        (c.platform, c.platform_order_id): c
        for c in session.scalars(
            select(CustomerInfo).where(
                CustomerInfo.platform_order_id.in_({oid for _, oid in wanted})
            )
        )
        if (c.platform, c.platform_order_id) in wanted
    }
    materials = {i.material_number for o in orders for i in o.items if i.material_number}
    names = {
        n.material_number: n
        for n in session.scalars(
            select(ReportItemName).where(ReportItemName.material_number.in_(materials))
        )
    }
    deliveries = {o.do_number for o in orders if o.do_number}
    invoices = dict(
        session.execute(
            select(SapTaxInvoice.delivery, SapTaxInvoice.tax_invoice_doc).where(
                SapTaxInvoice.delivery.in_(deliveries)
            )
        ).all()
    )

    settled_ids = {oid for platform, oid in wanted if platform in SETTLED_PLATFORMS}
    settlements = {
        (platform, order_id): total
        for platform, order_id, total in session.execute(
            select(
                PlatformSettlement.platform,
                PlatformSettlement.platform_order_id,
                func.sum(PlatformSettlement.amount),
            )
            .where(
                PlatformSettlement.platform.in_(SETTLED_PLATFORMS),
                PlatformSettlement.platform_order_id.in_(settled_ids),
            )
            .group_by(PlatformSettlement.platform, PlatformSettlement.platform_order_id)
        )
    }

    for order in orders:
        reasons: list[Reason] = []
        division = DIVISION.get(order.platform)
        if division is None:
            reasons.append(Reason(DIVISION_MISSING, f"Sàn {order.platform} chưa có tên Division"))
        info = customers.get((order.platform, order.platform_order_id))
        name = (info.customer_name or "").strip() if info else ""
        if not name:
            reasons.append(Reason(CUSTOMER, "Thiếu tên khách"))
        city = province_of(info.address if info else None)
        if city is None:
            reasons.append(Reason(CUSTOMER, "Địa chỉ không ra tỉnh/thành"))
        for item in order.items:
            if not item.material_number:
                reasons.append(Reason(REPORT_NAME, f"Dòng {item.line_no} chưa có mã vật tư"))
            elif item.material_number not in names:
                reasons.append(
                    Reason(REPORT_NAME, f"Mã {item.material_number} chưa có tên báo cáo")
                )
        invoice = invoices.get(order.do_number or "")
        if invoice is None:
            reasons.append(Reason(TAX_INVOICE, f"DO {order.do_number} chưa có Tax Invoice Doc."))
        total = settlements.get((order.platform, order.platform_order_id))
        if order.platform in SETTLED_PLATFORMS and total is None:
            reasons.append(Reason(SETTLEMENT, "Chưa có tiền vô"))
        if reasons:
            result.blocked.append(
                BlockedOrder(
                    order.platform,
                    order.platform_order_id,
                    order.order_batch_id,
                    order.ordered_at,
                    tuple(dict.fromkeys(reasons)),
                )
            )
            continue
        result.order_ids.append(order.id)
        for index, item in enumerate(order.items):  # ordered by line_no
            report = names[item.material_number]
            result.rows.append(
                HistoryRow(
                    division=division,
                    ordered_at=order.ordered_at,
                    billing_name=name,
                    billing_city=city,
                    customer_paid=(item.unit_price - item.unit_subsidy) * item.quantity,
                    unit_price=item.unit_price,
                    quantity=item.quantity,
                    item_name=report.item_name,
                    size=report.size,
                    variation=report.variation,
                    platform_order_id=order.platform_order_id,
                    tax_invoice_doc=invoice,
                    settlement=int(total) if total is not None and index == 0 else None,
                )
            )
    return result


def build_history_workbook(rows: Sequence[HistoryRow]) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    bold = Font(bold=True)
    for col, title in enumerate(COLUMNS, start=1):
        ws.cell(1, col, title).font = bold
    for r, row in enumerate(rows, start=2):
        values = (
            row.division,
            f"{row.ordered_at:%Y-%m-%d %H:%M}",
            row.ordered_at.month,
            row.ordered_at.year,
            row.billing_name,
            HIDDEN_PHONE,
            row.billing_city,
            f'=E{r}&" "&B{r}',
            f"=IF(H{r}=H{r - 1},0,1)",
            row.customer_paid,
            row.unit_price,
            None,
            None,
            row.quantity,
            row.item_name,
            row.size,
            row.variation,
            row.platform_order_id,
            row.tax_invoice_doc,
            row.settlement,
        )
        for col, value in enumerate(values, start=1):
            ws.cell(r, col, value)
        for letter in MONEY_COLUMNS:
            ws[f"{letter}{r}"].number_format = MONEY_FORMAT
        for letter in TEXT_COLUMNS:  # ids made of digits stay text when pasted
            ws[f"{letter}{r}"].number_format = "@"
    return wb
