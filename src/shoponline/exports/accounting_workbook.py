"""zrsd004 + three columns (order id, customer name, address) -> `SHOP ONLINE ddmmyy.xlsx`.

Every other cell, column and row (including the two total rows) is kept as exported.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import BinaryIO

from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.db.models import CustomerInfo, SalesOrder, SapSoRef
from shoponline.importers.excel_table import FileRejected, cell_text, normalize_header
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


def accounting_file_name(gi_date: date) -> str:
    return f"SHOP ONLINE {gi_date:%d%m%y}.xlsx"


def build_accounting_workbook(source: str | Path | BinaryIO, lookup: Lookup) -> AccountingFile:
    try:
        wb = load_workbook(source)
    except Exception as exc:
        raise FileRejected(f"Không đọc được file zrsd004: {exc}") from exc
    ws = wb.worksheets[0]
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

    sold_col, gi_col = headers[SOLD_TO_COLUMN], headers[GI_COLUMN]
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

    file_date = max(gi_dates) if gi_dates else date.today()
    return AccountingFile(workbook=wb, file_name=accounting_file_name(file_date), warnings=warnings)
