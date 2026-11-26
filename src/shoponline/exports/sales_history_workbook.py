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

A draft (collect_rows(draft=True)) also takes the orders blocked only by those two waits, leaves
the missing cells empty and adds a 21st column saying what each order waits for. It is for
checking only: it is never stored, so it cannot be confirmed as pasted.

collect_all_rows takes every order placed in a range of days, in any status, pasted or not, and
blocks none: the same 21 columns, for reconciling against the accountants' own file.

The file is a ledger that is only appended to. An issued return document adds negative rows (one
per platform line it takes back, at the marketplace price, dated like the original order); a
return cancelled after its negative rows were pasted adds rows that reverse them. A return's rows
go in only once the order's own rows are pasted or sit in the same file, so the file never holds
negative rows for an order it does not have. Column I of those rows is a constant: -1 (+1 when
reversing) on the first row of a whole-order return, 0 otherwise, so SUM(I) still counts orders.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
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
    SalesReturn,
    SalesReturnHistoryExported,
    SapTaxInvoice,
)
from shoponline.domain import states
from shoponline.domain.report_names import province_of
from shoponline.returns import flags as return_flags

SHEET = "sheet1"
DRAFT_SHEET = "NHÁP - KHÔNG DÁN"  # never the name of the file pasted into
FORMULA_STARTS = ("=", "+", "-", "@")
FORMULA_COLUMNS = (8, 9)  # H and I: the file's own formulas, written as formulas on purpose
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
HIDDEN_PHONE = "******"
MONEY_FORMAT = "#,##0"
MONEY_COLUMNS = ("J", "K", "T")
TEXT_COLUMNS = ("R", "S")

# Why an order is blocked; the kind tells the page where it is fixed.
CUSTOMER = "customer"
REPORT_NAME = "report_name"
TAX_INVOICE = "tax_invoice"
SETTLEMENT = "settlement"
# Platforms whose money received is looked up per order. Lazada's file gives none, so an admin
# types it in (accounting/manual_settlement.py); until then the order is still not blocked.
SETTLEMENT_LOOKUP_PLATFORMS = ("SHOPEE", "TIKTOK", "LAZADA")
# Platforms whose order waits for the money (blocked, or a draft) because a file always brings it.
SETTLEMENT_REQUIRED_PLATFORMS = ("SHOPEE", "TIKTOK")
# The only waits a draft accepts, in the order the status column lists them.
DRAFT_LABELS = {TAX_INVOICE: "Chờ hóa đơn", SETTLEMENT: "Chờ tiền vô"}
STATUS_COLUMN = "Trạng thái"
ALL_SHEET = "TẤT CẢ ĐƠN - KHÔNG DÁN"
CONFIRMED_LABEL = "Đã xác nhận dán"
UNCONFIRMED_LABEL = "Chưa xác nhận"


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
    tax_invoice_doc: str | None
    settlement: int | None = None  # the order's total, on its first line only
    status: str = ""  # what a draft order waits for; empty when complete
    transaction: int | None = None  # column I as a constant (return rows); None keeps the formula
    return_doc: str | None = None  # the return document a return row comes from


ISSUE = "ISSUE"  # a return's negative rows
VOID = "VOID"  # the rows that reverse them once the return is cancelled


@dataclass
class HistoryRows:
    rows: list[HistoryRow] = field(default_factory=list)
    order_ids: list[int] = field(default_factory=list)
    blocked: list[BlockedOrder] = field(default_factory=list)
    return_rows: list[HistoryRow] = field(default_factory=list)
    return_ids: list[tuple[int, str]] = field(default_factory=list)  # (return id, ISSUE | VOID)

    @property
    def all_rows(self) -> list[HistoryRow]:
        """Sale rows in their order, then return rows by document number."""
        return self.rows + self.return_rows


def history_file_name(day: date) -> str:
    return f"SHOP ONLINE LỊCH SỬ {day:%d%m%y}.xlsx"


def history_draft_file_name(day: date) -> str:
    return f"NHÁP {history_file_name(day)}"


def history_all_file_name(first: date, last: date) -> str:
    return f"TẤT CẢ ĐƠN SHOP ONLINE {first:%d%m%y}-{last:%d%m%y}.xlsx"


def is_draftable(reasons: Sequence[Reason]) -> bool:
    """True when every reason is a wait a draft accepts."""
    return all(r.kind in DRAFT_LABELS for r in reasons)


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
            .options(selectinload(SalesOrder.items), selectinload(SalesOrder.shop))
            .order_by(SalesOrder.ordered_at, SalesOrder.platform_order_id)
        )
    )


@dataclass(frozen=True)
class Lookups:
    """What the rows of a set of orders are read from, fetched once for all of them."""

    customers: dict
    names: dict
    invoices: dict
    settlements: dict


def _lookups(session: Session, orders: Sequence[SalesOrder]) -> Lookups:
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

    settled_ids = {oid for platform, oid in wanted if platform in SETTLEMENT_LOOKUP_PLATFORMS}
    settlements = {
        (platform, order_id): total
        for platform, order_id, total in session.execute(
            select(
                PlatformSettlement.platform,
                PlatformSettlement.platform_order_id,
                func.sum(PlatformSettlement.amount),
            )
            .where(
                PlatformSettlement.platform.in_(SETTLEMENT_LOOKUP_PLATFORMS),
                PlatformSettlement.platform_order_id.in_(settled_ids),
            )
            .group_by(PlatformSettlement.platform, PlatformSettlement.platform_order_id)
        )
    }
    return Lookups(customers, names, invoices, settlements)


def collect_rows(session: Session, until: date, draft: bool = False) -> HistoryRows:
    orders = pending_orders(session, until)
    result = HistoryRows()
    if orders:
        _collect_order_rows(session, orders, result, draft)
    _collect_return_rows(session, result, draft)
    return result


def _whole_returns(session: Session, order_ids: Sequence[int]) -> set[int]:
    """Orders with an issued return of the whole order."""
    return set(
        session.scalars(
            select(SalesReturn.sales_order_id).where(
                SalesReturn.sales_order_id.in_(order_ids),
                SalesReturn.status == "ISSUED",
                SalesReturn.full_return.is_(True),
            )
        )
    )


def _collect_order_rows(
    session: Session, orders: Sequence[SalesOrder], result: HistoryRows, draft: bool
) -> None:
    lookups = _lookups(session, orders)
    # The platform may never pay for an order cancelled or returned whole: no wait for its money.
    returned_whole = _whole_returns(session, [o.id for o in orders])
    customers, names = lookups.customers, lookups.names
    invoices, settlements = lookups.invoices, lookups.settlements

    for order in orders:
        reasons: list[Reason] = []
        division = order.shop.division
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
        if (
            order.platform in SETTLEMENT_REQUIRED_PLATFORMS
            and total is None
            and order.id not in returned_whole
        ):
            reasons.append(Reason(SETTLEMENT, "Chưa có tiền vô"))
        unique = tuple(dict.fromkeys(reasons))
        status = ""
        if unique and draft and is_draftable(unique):
            kinds = {r.kind for r in unique}
            status = "; ".join(label for kind, label in DRAFT_LABELS.items() if kind in kinds)
        elif unique:
            result.blocked.append(
                BlockedOrder(
                    order.platform,
                    order.platform_order_id,
                    order.order_batch_id,
                    order.ordered_at,
                    unique,
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
                    status=status if index == 0 else "",
                )
            )


def _pasted(session: Session, return_ids: Sequence[int]) -> set[tuple[int, str]]:
    return {
        (return_id, kind)
        for return_id, kind in session.execute(
            select(SalesReturnHistoryExported.return_id, SalesReturnHistoryExported.kind).where(
                SalesReturnHistoryExported.return_id.in_(return_ids)
            )
        )
    }


def return_label(sales_return: SalesReturn, kind: str) -> str:
    what = "Hủy đơn" if sales_return.reason_kind == "CANCEL" else "Trả hàng"
    scope = "cả đơn" if sales_return.full_return else "một phần"
    text = f"{what} ({scope}) – biên bản {sales_return.doc_no}"
    return f"Đảo do hủy phiếu: {text}" if kind == VOID else text


def _rows_of_return(
    sales_return: SalesReturn, kind: str, lookups: Lookups
) -> list[HistoryRow] | Reason:
    """The rows of one return (negative for ISSUE, reversed for VOID), or why they cannot be
    written. The order passed every check when its own rows were written; a value purged since
    is taken from the return's snapshot."""
    order = sales_return.order
    if not sales_return.sale_lines:
        return Reason(
            REPORT_NAME,
            f"Phiếu {sales_return.doc_no} chưa có dòng trừ theo giá sàn: chạy "
            "`shoponline return-sale-lines backfill`",
        )
    info = lookups.customers.get((order.platform, order.platform_order_id))
    name = ((info.customer_name if info else None) or sales_return.buyer_name or "").strip()
    city = province_of(info.address if info else None) or province_of(sales_return.buyer_address)
    if not name or city is None:
        return Reason(CUSTOMER, f"Phiếu {sales_return.doc_no}: thiếu tên khách hoặc tỉnh/thành")
    sign = -1 if kind == ISSUE else 1
    rows = []
    for index, line in enumerate(sales_return.sale_lines):
        item = line.item
        report = lookups.names.get(item.material_number)
        if report is None:
            return Reason(
                REPORT_NAME,
                f"Phiếu {sales_return.doc_no}: mã {item.material_number} chưa có tên báo cáo",
            )
        rows.append(
            HistoryRow(
                division=order.shop.division,
                ordered_at=order.ordered_at,
                billing_name=name,
                billing_city=city,
                customer_paid=sign * line.customer_paid,
                unit_price=item.unit_price,
                quantity=sign * line.quantity,
                item_name=report.item_name,
                size=report.size,
                variation=report.variation,
                platform_order_id=order.platform_order_id,
                tax_invoice_doc=sales_return.tax_invoice_doc,
                transaction=sign if sales_return.full_return and index == 0 else 0,
                return_doc=sales_return.doc_no,
                status=return_label(sales_return, kind) if index == 0 else "",
            )
        )
    return rows


def _returns_with_rows(session: Session, where) -> list[SalesReturn]:
    return list(
        session.scalars(
            select(SalesReturn)
            .where(where)
            .options(
                selectinload(SalesReturn.order).selectinload(SalesOrder.shop),
                selectinload(SalesReturn.order).selectinload(SalesOrder.items),
                selectinload(SalesReturn.sale_lines),
            )
            .order_by(SalesReturn.doc_year, SalesReturn.doc_seq)
        )
    )


def _ledger_entries(
    returns: Sequence[SalesReturn], pasted: set[tuple[int, str]]
) -> list[tuple[SalesReturn, str]]:
    """Every (return, kind) the ledger holds or will hold: the negative rows of an issued return,
    and for a cancelled return whose negative rows were pasted, those rows and their reversal.
    A return cancelled before its negative rows were pasted never reaches the file."""
    entries = []
    for sales_return in returns:
        if sales_return.status == "ISSUED":
            entries.append((sales_return, ISSUE))
        elif (sales_return.id, ISSUE) in pasted:
            entries += [(sales_return, ISSUE), (sales_return, VOID)]
    return entries


def _collect_return_rows(session: Session, result: HistoryRows, draft: bool) -> None:
    exported = exists().where(SalesHistoryExported.sales_order_id == SalesReturn.sales_order_id)
    in_file = SalesReturn.sales_order_id.in_(result.order_ids)
    returns = _returns_with_rows(session, exported | in_file)
    if not returns:
        return
    pasted = _pasted(session, [r.id for r in returns])
    wanted = [e for e in _ledger_entries(returns, pasted) if (e[0].id, e[1]) not in pasted]
    if not wanted:
        return
    lookups = _lookups(session, [r.order for r, _ in wanted])
    for sales_return, kind in wanted:
        rows = _rows_of_return(sales_return, kind, lookups)
        if isinstance(rows, Reason):
            order = sales_return.order
            result.blocked.append(
                BlockedOrder(
                    order.platform,
                    order.platform_order_id,
                    order.order_batch_id,
                    order.ordered_at,
                    (rows,),
                )
            )
            continue
        result.return_ids.append((sales_return.id, kind))
        result.return_rows += [r if draft else replace(r, status="") for r in rows]


def collect_all_rows(session: Session, first: date, last: date) -> list[HistoryRow]:
    """Every order placed from the start of `first` to the end of `last`, in any status, pasted
    or not, one row per order line. Nothing blocks an order: a missing value is left empty or
    taken from the platform's own data. For checking only; nothing is stored."""
    orders = list(
        session.scalars(
            select(SalesOrder)
            .where(
                SalesOrder.ordered_at >= datetime.combine(first, time()),
                SalesOrder.ordered_at < datetime.combine(last + timedelta(days=1), time()),
            )
            .options(selectinload(SalesOrder.items), selectinload(SalesOrder.shop))
            .order_by(SalesOrder.ordered_at, SalesOrder.platform_order_id)
        )
    )
    if not orders:
        return []
    lookups = _lookups(session, orders)
    confirmed = set(
        session.scalars(
            select(SalesHistoryExported.sales_order_id).where(
                SalesHistoryExported.sales_order_id.in_([o.id for o in orders])
            )
        )
    )
    flags = return_flags.of(session, [o.id for o in orders])
    rows: list[HistoryRow] = []
    for order in orders:
        info = lookups.customers.get((order.platform, order.platform_order_id))
        name = (info.customer_name or "").strip() if info else ""
        city = province_of(info.address if info else None) or ""
        invoice = lookups.invoices.get(order.do_number or "")
        total = lookups.settlements.get((order.platform, order.platform_order_id))
        parts = [states.LABELS.get(order.status, order.status)]
        if order.status == states.DELIVERED:
            if invoice is None:
                parts.append(DRAFT_LABELS[TAX_INVOICE])
            if order.platform in SETTLEMENT_REQUIRED_PLATFORMS and total is None:
                parts.append(DRAFT_LABELS[SETTLEMENT])
        flag = flags.get(order.id)
        if flag:
            parts.append(f"{flag.label} – biên bản {flag.doc_no}")
        parts.append(CONFIRMED_LABEL if order.id in confirmed else UNCONFIRMED_LABEL)
        for index, item in enumerate(order.items):  # ordered by line_no
            report = lookups.names.get(item.material_number)
            rows.append(
                HistoryRow(
                    division=order.shop.division,
                    ordered_at=order.ordered_at,
                    billing_name=name,
                    billing_city=city,
                    customer_paid=(item.unit_price - item.unit_subsidy) * item.quantity,
                    unit_price=item.unit_price,
                    quantity=item.quantity,
                    item_name=report.item_name if report else item.sap_name or item.product_name,
                    size=report.size if report else "",
                    variation=report.variation if report else item.variation_name or "",
                    platform_order_id=order.platform_order_id,
                    tax_invoice_doc=invoice,
                    settlement=int(total) if total is not None and index == 0 else None,
                    status="; ".join(parts) if index == 0 else "",
                )
            )
    returns = _returns_with_rows(session, SalesReturn.sales_order_id.in_([o.id for o in orders]))
    pasted = _pasted(session, [r.id for r in returns])
    for sales_return, kind in _ledger_entries(returns, pasted):
        found = _rows_of_return(sales_return, kind, lookups)
        if isinstance(found, Reason):
            continue  # a check file blocks nothing; the Shop Online page shows the reason
        mark = CONFIRMED_LABEL if (sales_return.id, kind) in pasted else UNCONFIRMED_LABEL
        rows += [replace(r, status=f"{r.status}; {mark}") if r.status else r for r in found]
    return rows


def build_history_workbook(
    rows: Sequence[HistoryRow], draft: bool = False, title: str | None = None
) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = title or (DRAFT_SHEET if draft else SHEET)
    bold = Font(bold=True)
    for col, title in enumerate(COLUMNS + (STATUS_COLUMN,) if draft else COLUMNS, start=1):
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
            f"=IF(H{r}=H{r - 1},0,1)" if row.transaction is None else row.transaction,
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
        if draft:
            values += (row.status or None,)
        for col, value in enumerate(values, start=1):
            cell = ws.cell(r, col, value)
            # Text from a platform file (a customer name) must not become a formula in Excel.
            if (
                col not in FORMULA_COLUMNS
                and isinstance(value, str)
                and value.startswith(FORMULA_STARTS)
            ):
                cell.data_type = "s"
        for letter in MONEY_COLUMNS:
            ws[f"{letter}{r}"].number_format = MONEY_FORMAT
        for letter in TEXT_COLUMNS:  # ids made of digits stay text when pasted
            ws[f"{letter}{r}"].number_format = "@"
    return wb
