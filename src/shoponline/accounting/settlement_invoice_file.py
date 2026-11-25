"""Lazada payout file from accounting: tax invoice number, date received, amount.

Accounting has the SAP tax invoice number, not Lazada's order id. Each invoice number is looked up
to exactly one Lazada order (invoice -> delivery -> sales order); a line whose invoice matches no
order or several orders is refused, never guessed or split. The checks and the save are the same as
for amounts typed by hand (manual_settlement). Nothing here stores the file.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from io import BytesIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shoponline.accounting import manual_settlement as manual
from shoponline.clock import today_vn
from shoponline.db.models import SalesOrder, SapTaxInvoice
from shoponline.importers.excel_table import parse_money, read_table

INVOICE_COLUMN = "Số hóa đơn"
DATE_COLUMN = "Ngày nhận tiền"
AMOUNT_COLUMN = "Số tiền"
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
THOUSANDS = re.compile(r"^\d{1,3}([.,\s]\d{3})+$")
CARRY_PARTS = 4


@dataclass(frozen=True)
class FileLine:
    line_no: int
    invoice: str  # normalized: no spaces, no leading zeros
    amount: int | None
    settled_on: date | None
    error: str = ""


@dataclass(frozen=True)
class ResolvedLine:
    line: FileLine
    order_id: str
    error: str


def normalize_invoice(text: str) -> str:
    """Spreadsheets drop the leading zeros of an invoice number; compare without them."""
    return text.strip().lstrip("0")


def _date(text: str) -> date:
    if ISO_DATE.match(text):
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass
    elif text:
        return manual.parse_date(text)
    raise manual.SettlementError(f"Ngày '{text}' không đúng dạng")


def _amount(text: str) -> int:
    if not text:
        raise manual.SettlementError("Số tiền trống")
    try:
        return parse_money(text, "Số tiền")
    except ValueError as exc:
        if THOUSANDS.match(text):  # a text cell such as "1.234.567"
            return manual.parse_amount(text)
        raise manual.SettlementError(str(exc)) from None


def read_file(data: bytes) -> list[FileLine]:
    """The lines of the first sheet; FileRejected when it is not an Excel file or a column is
    missing. A line that cannot be read comes back with its error."""
    table = read_table(BytesIO(data), required=(INVOICE_COLUMN, DATE_COLUMN, AMOUNT_COLUMN))
    lines = []
    for row in table.rows:
        invoice = normalize_invoice(row[INVOICE_COLUMN])
        try:
            if not invoice:
                raise manual.SettlementError("Số hóa đơn trống")
            lines.append(
                FileLine(
                    row.number,
                    invoice,
                    _amount(row[AMOUNT_COLUMN]),
                    _date(row[DATE_COLUMN]),
                )
            )
        except manual.SettlementError as exc:
            lines.append(FileLine(row.number, invoice, None, None, str(exc)))
    return lines


def _numbers(lines: list[FileLine]) -> str:
    return ", ".join(str(n) for n in lines)


def _orders_by_invoice(session: Session, invoices: set[str]) -> dict[str, set[str]]:
    """Per normalized invoice: its Lazada order ids; an empty set when SAP has the invoice but no
    Lazada order owns its DO; absent when SAP does not have it. One query for all invoices."""
    key = func.ltrim(SapTaxInvoice.tax_invoice_doc, "0")
    rows = session.execute(
        select(key, SalesOrder.platform_order_id)
        .select_from(SapTaxInvoice)
        .outerjoin(
            SalesOrder,
            (SalesOrder.do_number == SapTaxInvoice.delivery)
            & (SalesOrder.platform == manual.PLATFORM),
        )
        .where(key.in_(invoices))
    )
    found: dict[str, set[str]] = {}
    for invoice, order_id in rows:
        found.setdefault(invoice, set())
        if order_id is not None:
            found[invoice].add(order_id)
    return found


def resolve(
    session: Session, lines: list[FileLine], today: date | None = None
) -> list[ResolvedLine]:
    """Every line with its Lazada order and the reason it cannot be saved ('' when it can)."""
    today = today or today_vn()
    by_invoice: dict[str, list[int]] = defaultdict(list)
    for line in lines:
        if line.invoice:
            by_invoice[line.invoice].append(line.line_no)
    found = _orders_by_invoice(session, set(by_invoice))

    order_ids: dict[int, str] = {}
    errors: dict[int, str] = {}
    for line in lines:
        if line.error:
            errors[line.line_no] = line.error
            continue
        shown = line.invoice.zfill(8)
        numbers = by_invoice[line.invoice]
        orders = found.get(line.invoice)
        if len(numbers) > 1:
            errors[line.line_no] = f"Hóa đơn {shown} trùng ở các dòng {_numbers(numbers)}"
        elif orders is None:
            errors[line.line_no] = f"Hóa đơn {shown} chưa có trong dữ liệu SAP"
        elif not orders:
            errors[line.line_no] = f"Hóa đơn {shown} không thuộc đơn Lazada nào"
        elif len(orders) > 1:
            errors[line.line_no] = (
                f"Hóa đơn {shown} ứng với {len(orders)} đơn ({', '.join(sorted(orders))}), "
                "không tự chia tiền"
            )
        else:
            order_ids[line.line_no] = next(iter(orders))

    resolved = []
    for line in lines:
        order_id = order_ids.get(line.line_no, "")
        error = errors.get(line.line_no, "")
        if not error:
            try:
                manual.check(session, order_id, line.amount, line.settled_on, today)
            except manual.SettlementError as exc:
                error = str(exc)
        resolved.append(ResolvedLine(line, order_id, error))
    return resolved


def to_carry(lines: list[FileLine]) -> str:
    """The readable lines as text the preview form carries to the save step."""
    return "\n".join(
        f"{line.line_no}\t{line.invoice}\t{line.amount}\t{line.settled_on.isoformat()}"
        for line in lines
        if not line.error
    )


def from_carry(text: str) -> list[FileLine]:
    """Inverse of to_carry; ValueError when the text is not exactly what to_carry wrote."""
    lines = []
    for raw in text.splitlines():
        parts = raw.split("\t")
        if len(parts) != CARRY_PARTS or not parts[1] or not parts[0].isdigit():
            raise ValueError("Dữ liệu xem trước không đọc được")
        number, invoice, amount, day = parts
        if not amount.isdigit() or normalize_invoice(invoice) != invoice:
            raise ValueError("Dữ liệu xem trước không đọc được")
        lines.append(FileLine(int(number), invoice, int(amount), date.fromisoformat(day)))
    return lines
