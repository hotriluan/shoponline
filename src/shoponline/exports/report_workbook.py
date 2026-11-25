"""One workbook layout for every management report: a title, the filter and the data notes
above, then a table with money formatted as #,##0. Built in memory; nothing is stored."""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font

MONEY_FORMAT = "#,##0"
PERCENT_FORMAT = "0.0%"
FORMULA_STARTS = ("=", "+", "-", "@")


def _safe(value):
    """Text that Excel would run as a formula is written as text."""
    if isinstance(value, str) and value.startswith(FORMULA_STARTS):
        return "'" + value
    return value


def build(
    sheet_title: str,
    filter_line: str,
    notes: Sequence[str],
    headers: Sequence[str],
    rows: Sequence[Sequence],
    *,
    money: Sequence[str] = (),
    percent: Sequence[str] = (),
) -> Workbook:
    """`money` / `percent` name the columns (by header) to format as such."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_title[:31]
    sheet.append([sheet_title])
    sheet["A1"].font = Font(bold=True, size=13)
    sheet.append([filter_line])
    for note in notes:
        sheet.append([note])
    sheet.append([])
    header_row = sheet.max_row + 1
    sheet.append(list(headers))
    for cell in sheet[header_row]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append([_safe(v) for v in row])
    for name, number_format in (
        *((h, MONEY_FORMAT) for h in money),
        *((h, PERCENT_FORMAT) for h in percent),
    ):
        column = headers.index(name) + 1
        for cells in sheet.iter_rows(min_row=header_row + 1, min_col=column, max_col=column):
            cells[0].number_format = number_format
    for index, header in enumerate(headers, start=1):
        width = max(
            [
                len(str(header)),
                *(len(str(r[index - 1])) for r in rows[:200] if r[index - 1] is not None),
            ]
        )
        sheet.column_dimensions[sheet.cell(row=header_row, column=index).column_letter].width = min(
            max(width + 2, 12), 60
        )
    sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)
    return workbook


def to_bytes(workbook: Workbook) -> bytes:
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
