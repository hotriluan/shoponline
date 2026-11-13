"""zrsd004 + three columns (order id, customer name, address) -> `SHOP ONLINE ddmmyy.xlsx`.

Every other cell, column and row (including the total rows) is kept as exported when one file is
built. Several files merge into one with the total rows recomputed.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from copy import copy
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import BinaryIO

from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from shoponline.db.models import CustomerInfo, SalesOrder, SapSoRef
from shoponline.importers.excel_table import FileRejected, cell_text, normalize_header
from shoponline.importers.sap_reports import parse_report_date
from shoponline.reconcile.so_link import platform_by_customer

SO_COLUMN = "SO Reference"
SOLD_TO_COLUMN = "Sold-to Party"
GI_COLUMN = "Actual GI Date"
INSERTED = ("mã đơn hàng", "tên khách hàng", "địa chỉ")


@dataclass(frozen=True)
class CustomerLine:
    order_id: str | None
    name: str | None
    address: str | None


@dataclass
class AccountingFile:
    workbook: Workbook
    file_name: str
    warnings: list[str] = field(default_factory=list)


Lookup = Callable[[str, str], CustomerLine]


def database_lookup(session: Session) -> Lookup:
    """SO number + sold-to -> order id (linked order first, else PO No) -> customer row."""
    customers = platform_by_customer(session)

    def lookup(so_number: str, sold_to: str) -> CustomerLine:
        order = session.scalar(select(SalesOrder).where(SalesOrder.so_number == so_number))
        if order is not None:
            platform, order_id = order.platform, order.platform_order_id
        else:
            ref = session.get(SapSoRef, so_number)
            if ref is None:
                return CustomerLine(None, None, None)
            platform, order_id = customers.get(ref.sold_to or sold_to), ref.po_no
        info = session.scalar(
            select(CustomerInfo).where(
                CustomerInfo.platform == platform, CustomerInfo.platform_order_id == order_id
            )
        )
        name = info.customer_name if info else None
        return CustomerLine(order_id, name, info.address if info else None)

    return lookup


def preloaded_lookup(session: Session, so_numbers: Collection[str]) -> Lookup:
    """The same answers as database_lookup for the given SO numbers, from three queries."""
    wanted = list(set(so_numbers))
    customers = platform_by_customer(session)
    orders = {
        o.so_number: (o.platform, o.platform_order_id)
        for o in session.scalars(select(SalesOrder).where(SalesOrder.so_number.in_(wanted)))
    }
    refs = {
        r.so_number: r
        for r in session.scalars(select(SapSoRef).where(SapSoRef.so_number.in_(wanted)))
    }
    keys = set(orders.values())
    keys.update((customers.get(r.sold_to), r.po_no) for so, r in refs.items() if so not in orders)
    infos = {
        (i.platform, i.platform_order_id): i
        for i in session.scalars(
            select(CustomerInfo).where(
                tuple_(CustomerInfo.platform, CustomerInfo.platform_order_id).in_(
                    [k for k in keys if k[0] is not None]
                )
            )
        )
    }

    def lookup(so_number: str, sold_to: str) -> CustomerLine:
        if so_number in orders:
            platform, order_id = orders[so_number]
        else:
            ref = refs.get(so_number)
            if ref is None:
                return CustomerLine(None, None, None)
            platform, order_id = customers.get(ref.sold_to or sold_to), ref.po_no
        info = infos.get((platform, order_id))
        return CustomerLine(
            order_id, info.customer_name if info else None, info.address if info else None
        )

    return lookup


def accounting_file_name(gi_date: date) -> str:
    return f"SHOP ONLINE {gi_date:%d%m%y}.xlsx"


def _insert_columns(ws) -> tuple[dict[str, int], int]:
    """Insert the three customer columns after SO Reference (once). Returns headers, first new."""
    headers = {normalize_header(c.value): c.column for c in ws[1] if c.value is not None}
    missing = [c for c in (SO_COLUMN, SOLD_TO_COLUMN, GI_COLUMN) if c not in headers]
    if missing:
        raise FileRejected("File zrsd004 thiếu cột bắt buộc: " + ", ".join(missing))

    so_col = headers[SO_COLUMN]
    first_new = so_col + 1
    already = [normalize_header(ws.cell(1, first_new + i).value) for i in range(3)]
    if already != list(INSERTED):
        widths = {
            c: ws.column_dimensions[get_column_letter(c)].width
            for c in range(first_new, ws.max_column + 1)
        }
        ws.insert_cols(first_new, 3)
        for col, width in widths.items():
            if width:
                ws.column_dimensions[get_column_letter(col + 3)].width = width
        for i, title in enumerate(INSERTED):
            ws.cell(1, first_new + i, title)
        ws.column_dimensions[get_column_letter(first_new)].width = 20
        ws.column_dimensions[get_column_letter(first_new + 1)].width = 24
        ws.column_dimensions[get_column_letter(first_new + 2)].width = 50
        headers = {normalize_header(c.value): c.column for c in ws[1] if c.value is not None}
    return headers, first_new


def _fill_customers(
    ws, headers: dict[str, int], first_new: int, lookup: Lookup
) -> tuple[list[str], list[date]]:
    """Fill the three columns of every row that has an SO number; total rows stay as they are."""
    sold_col, gi_col, so_col = headers[SOLD_TO_COLUMN], headers[GI_COLUMN], headers[SO_COLUMN]
    warnings: list[str] = []
    gi_dates: list[date] = []
    for row in range(2, ws.max_row + 1):
        so_number = cell_text(ws.cell(row, so_col).value)
        if not so_number:
            continue  # total rows stay as they are
        gi_value = ws.cell(row, gi_col).value
        if isinstance(gi_value, datetime):
            gi_dates.append(gi_value.date())
        line = lookup(so_number, cell_text(ws.cell(row, sold_col).value))
        order_cell = ws.cell(row, first_new, line.order_id)
        order_cell.number_format = "@"
        ws.cell(row, first_new + 1, line.name)
        ws.cell(row, first_new + 2, line.address)
        gaps = [
            label
            for label, value in (
                ("mã đơn", line.order_id),
                ("tên khách", line.name),
                ("địa chỉ", line.address),
            )
            if not value
        ]
        if gaps:
            warnings.append(f"Dòng {row} (SO {so_number}): thiếu {', '.join(gaps)}")
    return warnings, gi_dates


def build_accounting_workbook(source: str | Path | BinaryIO, lookup: Lookup) -> AccountingFile:
    """One zrsd004 file as exported, plus the three columns. Every row, totals included, is kept."""
    try:
        wb = load_workbook(source)
    except Exception as exc:
        raise FileRejected(f"Không đọc được file zrsd004: {exc}") from exc
    ws = wb.worksheets[0]
    headers, first_new = _insert_columns(ws)
    warnings, gi_dates = _fill_customers(ws, headers, first_new, lookup)
    file_date = max(gi_dates) if gi_dates else date.today()
    return AccountingFile(workbook=wb, file_name=accounting_file_name(file_date), warnings=warnings)


# ---------------------------------------------------------------- several sources, one file

DELIVERY_COLUMN = "Delivery"
LINE_ITEM_COLUMN = "Line Item"
STATUS_COLUMN = "Total Movement Goods Stat"
GOODS_ISSUED = "C"

# Every quantity column is summed by the unit column beside it, as SAP does in its total rows.
TOTAL_COLUMNS = (
    ("Delivery Qty", "Sales Unit"),
    ("Tonase", "Tonase Unit"),
    ("Actual Delivery Qty", "Sales Unit"),
    ("Net Weight", "Weight Unit"),
    ("Volume", "Volume Unit"),
)
# Order of the total rows when a column has several units. The two real samples show SET above PC;
# the assumption is SAP's internal unit codes ("PC" is stored as "ST"). Any other unit follows in
# alphabetical order. Confirm with a real file that has a third unit.
UNIT_ORDER = ("SET", "PC")

# Why a source row stays out of the merged file.
FOREIGN_CUSTOMER = "khách hàng không thuộc sàn nào"
NO_GI_DATE = "chưa có ngày goods issue thực hoặc ngày ở tương lai"
NOT_COMPLETE = "chưa goods issue xong (trạng thái khác C)"
BEFORE_CUTOFF = "ngày goods issue không sau mốc ngày"
ALREADY_SENT = "DO đã gửi kế toán"
# Rows that may still be sent later, once SAP finishes the goods issue.
NOT_YET_ISSUED = (NO_GI_DATE, NOT_COMPLETE)


@dataclass(frozen=True)
class SkippedRow:
    reason: str
    delivery: str
    so_number: str
    sold_to: str


@dataclass
class MergedAccountingFile(AccountingFile):
    @property
    def deliveries(self) -> set[str]:
        return set(self.delivery_so)

    @property
    def so_numbers(self) -> set[str]:
        return set(self.delivery_so.values())

    delivery_so: dict[str, str] = field(default_factory=dict)  # delivery -> its SO number
    row_count: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    # Only the rows in NOT_YET_ISSUED are listed; the others are counted in `dropped`.
    skipped: list[SkippedRow] = field(default_factory=list)


def _source_name(source: object, index: int) -> str:
    if isinstance(source, str | Path):
        return Path(source).name
    return f"nguồn {index + 1}"


def _gi_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = cell_text(value)
    if not text:
        return None
    try:
        return parse_report_date(text, GI_COLUMN)
    except ValueError:
        return None


def _unit_key(unit: str) -> tuple[int, str]:
    return (UNIT_ORDER.index(unit) if unit in UNIT_ORDER else len(UNIT_ORDER), unit)


def _as_number(total: Decimal) -> int | float:
    return int(total) if total == total.to_integral_value() else float(total)


def _total_rows(columns: dict[str, int], rows: list[list]) -> list[dict[int, object]]:
    """SAP's total rows: each quantity column summed per its own unit.

    There are as many rows as the column with the most units; every column fills its totals from
    the first row down, and leaves the rest empty.
    """
    per_column: dict[int, list[tuple[str, Decimal]]] = {}
    unit_cells: dict[int, list[str]] = {}
    for qty_name, unit_name in TOTAL_COLUMNS:
        if qty_name not in columns or unit_name not in columns:
            continue
        qty_col, unit_col = columns[qty_name], columns[unit_name]
        sums: dict[str, Decimal] = {}
        for row in rows:
            text = cell_text(row[qty_col - 1].value)
            if not text:
                continue
            try:
                value = Decimal(text)
            except InvalidOperation:
                continue
            unit = cell_text(row[unit_col - 1].value)
            sums[unit] = sums.get(unit, Decimal(0)) + value
        ordered = sorted(sums.items(), key=lambda item: _unit_key(item[0]))
        per_column[qty_col] = ordered
        if len(ordered) > len(unit_cells.get(unit_col, [])):
            unit_cells[unit_col] = [unit for unit, _ in ordered]
    height = max((len(v) for v in per_column.values()), default=0)
    totals: list[dict[int, object]] = []
    for i in range(height):
        cells: dict[int, object] = {}
        for unit_col, units in unit_cells.items():
            cells[unit_col] = units[i] if i < len(units) else ""
        for qty_col, ordered in per_column.items():
            cells[qty_col] = _as_number(ordered[i][1]) if i < len(ordered) else None
        totals.append(cells)
    return totals


def _copy_style(source, target) -> None:
    if source.has_style:
        target.number_format = source.number_format
        target.font = copy(source.font)
        target.fill = copy(source.fill)
        target.border = copy(source.border)
        target.alignment = copy(source.alignment)


def _header_of(ws) -> list[str]:
    values = [normalize_header(c.value) for c in ws[1]]
    while values and not values[-1]:
        values.pop()
    return values


def _check_same_header(loaded: list[tuple[str, object]], header: list[str]) -> None:
    for name, ws in loaded[1:]:
        other = _header_of(ws)
        if other == header:
            continue
        lacking = sorted(set(header) - set(other))
        extra = sorted(set(other) - set(header))
        detail = []
        if lacking:
            detail.append("thiếu cột " + ", ".join(lacking))
        if extra:
            detail.append("thừa cột " + ", ".join(extra))
        raise FileRejected(
            f"Các file zrsd004 không cùng cột: {name} " + ("; ".join(detail) or "khác thứ tự cột")
        )


def build_merged_accounting_workbook(
    sources: Sequence[str | Path | BinaryIO],
    lookup: Lookup,
    *,
    exclude_deliveries: Collection[str],
    cutoff: date | None,
    today: date,
    platform_sold_to: Collection[str],
) -> MergedAccountingFile:
    """Several zrsd004 files -> one accounting file.

    Only rows of a configured platform customer that SAP has really issued (Actual GI Date set and
    not after `today`, status C), later than `cutoff` and not in `exclude_deliveries`, are kept.
    Source total rows are dropped; the totals are recomputed over the kept rows.
    """
    if not sources:
        raise FileRejected("Không có DO mới")
    loaded = []
    for index, source in enumerate(sources):
        name = _source_name(source, index)
        try:
            workbook = load_workbook(source)
        except Exception as exc:
            raise FileRejected(f"Không đọc được file zrsd004 ({name}): {exc}") from exc
        loaded.append((name, workbook.worksheets[0]))

    base_name, base_ws = loaded[0]
    header = _header_of(base_ws)
    columns: dict[str, int] = {}
    for position, title in enumerate(header, start=1):
        if title and title not in columns:
            columns[title] = position
    required = (
        DELIVERY_COLUMN,
        SO_COLUMN,
        SOLD_TO_COLUMN,
        GI_COLUMN,
        LINE_ITEM_COLUMN,
        STATUS_COLUMN,
    )
    missing = [c for c in required if c not in columns]
    if missing:
        raise FileRejected(f"File zrsd004 ({base_name}) thiếu cột bắt buộc: " + ", ".join(missing))
    _check_same_header(loaded, header)

    excluded = set(exclude_deliveries)
    customers = set(platform_sold_to)
    dropped: dict[str, int] = {}
    skipped: list[SkippedRow] = []
    kept: dict[tuple[str, str], list] = {}
    gi_dates: list[date] = []
    delivery_col, so_col = columns[DELIVERY_COLUMN], columns[SO_COLUMN]
    sold_col, gi_col = columns[SOLD_TO_COLUMN], columns[GI_COLUMN]
    line_col, status_col = columns[LINE_ITEM_COLUMN], columns[STATUS_COLUMN]
    for _, ws in loaded:
        for cells in ws.iter_rows(min_row=2, max_col=len(header)):
            delivery = cell_text(cells[delivery_col - 1].value)
            so_number = cell_text(cells[so_col - 1].value)
            if not delivery or not so_number:
                continue  # total and blank rows
            sold_to = cell_text(cells[sold_col - 1].value)
            gi = _gi_date(cells[gi_col - 1].value)
            reason = None
            if sold_to not in customers:
                reason = FOREIGN_CUSTOMER
            elif gi is None or gi > today:
                reason = NO_GI_DATE
            elif cell_text(cells[status_col - 1].value) != GOODS_ISSUED:
                reason = NOT_COMPLETE
            elif cutoff is not None and gi <= cutoff:
                reason = BEFORE_CUTOFF
            elif delivery in excluded:
                reason = ALREADY_SENT
            if reason is not None:
                dropped[reason] = dropped.get(reason, 0) + 1
                if reason in NOT_YET_ISSUED:
                    skipped.append(SkippedRow(reason, delivery, so_number, sold_to))
                continue
            key = (delivery, cell_text(cells[line_col - 1].value))
            if key not in kept:  # the source listed first wins
                kept[key] = list(cells)
                gi_dates.append(gi)
    if not kept:
        raise FileRejected("Không có DO mới")

    def line_order(key: tuple[str, str]) -> tuple[str, int, str]:
        delivery, line = key
        return (delivery, int(line) if line.isdigit() else 0, line)

    out = Workbook()
    out_ws = out.active
    out_ws.title = base_ws.title
    for position, title in enumerate(header, start=1):
        cell = out_ws.cell(1, position, title)
        _copy_style(base_ws.cell(1, position), cell)
        letter = get_column_letter(position)
        if base_ws.column_dimensions[letter].width:
            out_ws.column_dimensions[letter].width = base_ws.column_dimensions[letter].width
    rows = [kept[key] for key in sorted(kept, key=line_order)]
    for row_number, cells in enumerate(rows, start=2):
        for position, source_cell in enumerate(cells, start=1):
            target = out_ws.cell(row_number, position, source_cell.value)
            _copy_style(source_cell, target)
    next_row = len(rows) + 2
    for total in _total_rows(columns, rows):
        for position, value in total.items():
            out_ws.cell(next_row, position, value)
        next_row += 1

    out_columns, first_new = _insert_columns(out_ws)
    warnings, _ = _fill_customers(out_ws, out_columns, first_new, lookup)
    return MergedAccountingFile(
        workbook=out,
        file_name=accounting_file_name(max(gi_dates)),
        warnings=warnings,
        delivery_so={d: cell_text(kept[(d, line)][so_col - 1].value) for d, line in kept},
        row_count=len(rows),
        dropped=dropped,
        skipped=skipped,
    )
