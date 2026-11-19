"""Read one worksheet as a table addressed by column names. Every cell becomes a string."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import BinaryIO

from openpyxl import load_workbook

MAX_ERRORS_SHOWN = 20


class FileRejected(ValueError):
    """The whole file is refused; nothing from it is stored."""

    def __init__(self, message: str, details: Iterable[str] = ()):
        self.details = list(details)
        shown = self.details[:MAX_ERRORS_SHOWN]
        more = len(self.details) - len(shown)
        full = message
        if shown:
            full += "\n" + "\n".join(f"- {d}" for d in shown)
        if more > 0:
            full += f"\n- … và {more} lỗi khác"
        super().__init__(full)
        self.message = message


def normalize_header(text: object) -> str:
    """NFC + trim. Case is significant: Shopee has two columns differing only in case."""
    return unicodedata.normalize("NFC", str(text or "")).strip()


def cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.time() == datetime.min.time():
            return value.date().isoformat()
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    return str(value).strip()


@dataclass
class Row:
    number: int
    values: list[str]
    columns: dict[str, int]

    def __getitem__(self, name: str) -> str:
        index = self.columns[name]
        return self.values[index] if index < len(self.values) else ""


@dataclass
class Table:
    sheet_name: str
    columns: dict[str, int]
    rows: list[Row]


def open_workbook(source: str | Path | BinaryIO):
    try:
        # Not read_only: platform exports carry wrong sheet dimensions, which makes the
        # read-only reader return truncated rows.
        return load_workbook(source, data_only=True)
    except Exception as exc:  # openpyxl raises many types for non-xlsx input
        raise FileRejected(f"Không đọc được file Excel: {exc}") from exc


def read_sheet(
    worksheet,
    *,
    required: Iterable[str],
    header_row: int = 1,
    header_marker: str | None = None,
) -> Table:
    """Read one worksheet as a table; reject when any required column is missing.

    With `header_marker`, the header is the first row whose first cell equals the marker (a
    report with a summary above its table); `header_row` is then ignored. Duplicate column names
    keep the first occurrence.
    """
    rows_iter = worksheet.iter_rows(values_only=True)
    header: tuple = ()
    if header_marker is None:
        for _ in range(header_row):
            header = next(rows_iter, ())
    else:
        wanted = normalize_header(header_marker)
        header_row = 0
        for raw in rows_iter:
            header_row += 1
            if raw and normalize_header(raw[0]) == wanted:
                header = raw
                break
        else:
            raise FileRejected(f"Không tìm thấy dòng tiêu đề bắt đầu bằng '{header_marker}'")
    columns: dict[str, int] = {}
    for index, raw in enumerate(header):
        name = normalize_header(raw)
        if name and name not in columns:
            columns[name] = index
    missing = [normalize_header(c) for c in required if normalize_header(c) not in columns]
    if missing:
        raise FileRejected("File thiếu cột bắt buộc: " + ", ".join(missing))

    rows: list[Row] = []
    for offset, raw_row in enumerate(rows_iter, start=header_row + 1):
        values = [cell_text(v) for v in raw_row]
        if any(values):
            rows.append(Row(number=offset, values=values, columns=columns))
    return Table(sheet_name=worksheet.title, columns=columns, rows=rows)


def read_table(
    source: str | Path | BinaryIO,
    *,
    required: Iterable[str],
    sheet: str | None = None,
    header_row: int = 1,
) -> Table:
    """Load a sheet; reject when the sheet or any required column is missing."""
    workbook = open_workbook(source)
    try:
        if sheet is None:
            worksheet = workbook.worksheets[0]
        else:
            names = {normalize_header(n): n for n in workbook.sheetnames}
            if normalize_header(sheet) not in names:
                raise FileRejected(
                    f"Không có sheet '{sheet}'. File có: {', '.join(workbook.sheetnames)}"
                )
            worksheet = workbook[names[normalize_header(sheet)]]
        return read_sheet(worksheet, required=required, header_row=header_row)
    finally:
        workbook.close()


MAX_MONEY = 10**15


def _parse_amount(text: str, field: str) -> Decimal:
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field} không phải số: {text!r}") from exc
    if not amount.is_finite():
        raise ValueError(f"{field} không phải số hữu hạn: {text!r}")
    if amount != amount.to_integral_value():
        raise ValueError(f"{field} có phần lẻ: {text!r}")
    return amount


def parse_money(text: str, field: str) -> int:
    """'120000.00' -> 120000. Blank -> 0. A non-zero fractional part is an error."""
    cleaned = text.strip()
    if not cleaned:
        return 0
    amount = _parse_amount(cleaned, field)
    if amount < 0:
        raise ValueError(f"{field} âm: {text!r}")
    return int(amount)


def parse_signed_money(text: str, field: str) -> int:
    """Like parse_money but a negative amount is allowed and a blank cell is an error."""
    cleaned = text.strip()
    if not cleaned:
        raise ValueError(f"{field} trống")
    amount = _parse_amount(cleaned, field)
    if abs(amount) >= MAX_MONEY:
        raise ValueError(f"{field} quá lớn: {text!r}")
    return int(amount)


def parse_quantity(text: str, field: str) -> int:
    value = parse_money(text, field)
    if value <= 0:
        raise ValueError(f"{field} phải lớn hơn 0: {text!r}")
    return value
