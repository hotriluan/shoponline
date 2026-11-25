"""Read a Bkav tax invoice PDF: the header fields and the item table.

A PDF is an untrusted file: the reader checks the signature, size and page count first, and the
web route runs `read_invoice_pdf` in a worker thread with a time limit. Error messages name the
field and the number only; the buyer's name and address are never read, logged or shown.
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from shoponline.importers.excel_table import FileRejected

MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 5
MAX_TEXT = 200

Tables = list[list[list[str | None]]]

_AMOUNT = re.compile(r"^\d{1,3}(\.\d{3})+(,\d+)?$|^\d+(,\d+)?$")
_INDEX_CELL = re.compile(r"^\d+(\s*=.*)?$")
_SYMBOL = re.compile(r"Ký hiệu:\s*(\S+)")
_NUMBER = re.compile(r"(?<![\w])Số:\s*(\d+)")
_DATE = re.compile(r"Ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})")
_DELIVERY = re.compile(r"Số DO:\s*(\S+)")
_PO = re.compile(r"Số PO:\s*(\S+)")
_NET = re.compile(r"Cộng tiền hàng:\s*(\S+)")
_VAT = re.compile(r"Thuế suất GTGT:\s*(\d+)\s*%")
_TAX = re.compile(r"Tiền thuế GTGT:\s*(\S+)")
_TOTAL = re.compile(r"Tổng cộng tiền thanh toán:\s*(\S+)")


@dataclass(frozen=True)
class PdfLine:
    number: int
    name: str
    unit: str
    quantity: Decimal
    amount: int


@dataclass(frozen=True)
class InvoicePdf:
    symbol: str
    number: str
    invoice_date: date
    delivery: str
    po: str
    net: int
    vat_rate: int
    tax: int
    total: int
    lines: tuple[PdfLine, ...]


def parse_amount(text: str) -> Decimal:
    """'111.111' -> 111111; '55.555,5' -> 55555.5 (dot groups thousands, comma is the decimal)."""
    cleaned = text.strip()
    if not _AMOUNT.match(cleaned):
        raise ValueError("sai dạng số")
    return Decimal(cleaned.replace(".", "").replace(",", "."))


def _whole(text: str) -> int:
    value = parse_amount(text)
    if value != value.to_integral_value():
        raise ValueError("có phần lẻ")
    return int(value)


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _valid_text(text: str) -> bool:
    return (
        bool(text)
        and len(text) <= MAX_TEXT
        and not any(unicodedata.category(c) == "Cc" for c in text)
    )


def parse_invoice(tables: Tables) -> InvoicePdf:
    """Pure function over the tables pdfplumber extracted; raises FileRejected naming each gap."""
    errors: list[str] = []
    head = "\n".join(cell for table in tables for row in table for cell in row if cell)

    def find(pattern: re.Pattern, label: str) -> str:
        match = pattern.search(head)
        if not match:
            errors.append(f"Không thấy {label}")
            return ""
        return match.group(1)

    symbol = find(_SYMBOL, "ký hiệu hóa đơn")
    number = find(_NUMBER, "số hóa đơn")
    delivery = find(_DELIVERY, "số DO")
    po = find(_PO, "số PO")
    invoice_date = date(2000, 1, 1)
    match = _DATE.search(head)
    if not match:
        errors.append("Không thấy ngày hóa đơn")
    else:
        try:
            day, month, year = (int(g) for g in match.groups())
            invoice_date = date(year, month, day)
        except ValueError:
            errors.append("Ngày hóa đơn không hợp lệ")
    figures: dict[str, int] = {}
    for key, pattern, label in (
        ("net", _NET, "cộng tiền hàng"),
        ("vat", _VAT, "thuế suất"),
        ("tax", _TAX, "tiền thuế"),
        ("total", _TOTAL, "tổng thanh toán"),
    ):
        raw = find(pattern, label)
        figures[key] = 0
        if not raw:
            continue
        try:
            figures[key] = int(raw) if key == "vat" else _whole(raw)
        except ValueError as exc:
            errors.append(f"{label.capitalize()}: {exc}")

    lines = _parse_lines(tables, errors)
    if errors:
        raise FileRejected("Hóa đơn PDF thiếu hoặc sai trường, không đọc được", errors)
    return InvoicePdf(
        symbol=symbol,
        number=number,
        invoice_date=invoice_date,
        delivery=delivery,
        po=po,
        net=figures["net"],
        vat_rate=figures["vat"],
        tax=figures["tax"],
        total=figures["total"],
        lines=tuple(lines),
    )


def _parse_lines(tables: Tables, errors: list[str]) -> list[PdfLine]:
    lines: list[PdfLine] = []
    in_items = False
    for table in tables:
        skip_index_row = False
        for row in table:
            cells = [_clean(c) for c in row]
            if cells and cells[0] == "STT" and any("Tên hàng" in c for c in cells):
                in_items, skip_index_row = True, True
                continue
            if not in_items or len(cells) < 6:
                continue
            if skip_index_row:
                skip_index_row = False
                if all(_INDEX_CELL.match(c) for c in cells if c):
                    continue
            if not cells[0].isdigit():
                continue
            number = int(cells[0])
            where = f"Dòng hàng {number}"
            name, unit = cells[1], cells[2]
            if not _valid_text(name):
                errors.append(f"{where}: tên hàng trống, dài quá {MAX_TEXT} ký tự hoặc có ký tự lạ")
            if not _valid_text(unit):
                errors.append(
                    f"{where}: đơn vị tính trống, dài quá {MAX_TEXT} ký tự hoặc có ký tự lạ"
                )
            try:
                quantity = parse_amount(cells[3])
                if quantity <= 0:
                    raise ValueError("phải lớn hơn 0")
            except ValueError as exc:
                errors.append(f"{where}: số lượng {exc}")
                continue
            try:
                parse_amount(cells[4])  # unit price: shown only, but must read as a number
                amount = _whole(cells[5])
            except ValueError as exc:
                errors.append(f"{where}: đơn giá hoặc thành tiền {exc}")
                continue
            lines.append(PdfLine(number, name, unit, quantity, amount))
    if not lines and not errors:
        errors.append("Không thấy dòng hàng nào")
    return lines


def read_invoice_pdf(source: bytes | Path) -> InvoicePdf:
    import pdfplumber

    data = source if isinstance(source, bytes) else Path(source).read_bytes()
    if not data.startswith(b"%PDF-"):
        raise FileRejected("Không đọc được hóa đơn: file không phải PDF")
    if len(data) > MAX_BYTES:
        raise FileRejected(f"Không đọc được hóa đơn: file quá {MAX_BYTES // 1024 // 1024} MB")
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > MAX_PAGES:
                raise FileRejected(f"Không đọc được hóa đơn: quá {MAX_PAGES} trang")
            tables: Tables = []
            has_text = False
            for page in pdf.pages:
                tables.extend(page.extract_tables())
                has_text = has_text or bool((page.extract_text() or "").strip())
    except FileRejected:
        raise
    except Exception as exc:  # pdfminer raises many types for damaged input
        raise FileRejected("Không đọc được hóa đơn: PDF hỏng hoặc có mã hóa") from exc
    if not has_text:
        raise FileRejected("Không đọc được hóa đơn: PDF không có chữ (bản scan?)")
    try:
        return parse_invoice(tables)
    except InvalidOperation as exc:  # a number that slipped past the pattern
        raise FileRejected("Không đọc được hóa đơn: số không hợp lệ") from exc
