"""REQUEST to RETURN GOODS (.xlsx), filled from the stored snapshot of a sales return.

The template (exports/templates/return_request.xlsx) is the sample's `RRG ENGLISH` sheet with its
dynamic cells emptied. Each returned line takes a row from 14: C number, D the SAP item name,
N quantity, P stock unit, AL the reason. The sample has one item row; a second line repeats it.

The sheet XML is edited directly instead of through openpyxl: loading and saving a workbook with
openpyxl rewrites styles (it resets the font and alignment of merged cells' hidden cells), the
sheet properties and the header and footer, and the forms must stay identical to the sample.
Everything outside the cells, rows, merged ranges and print area named here is copied unchanged.
"""

from __future__ import annotations

import copy
import re
import zipfile
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from lxml import etree

from shoponline.exports.text_clean import clean_text

TEMPLATE = Path(__file__).parent / "templates" / "return_request.xlsx"
SHEET_PART = "xl/worksheets/sheet1.xml"
WORKBOOK_PART = "xl/workbook.xml"
FIRST_ITEM_ROW = 14
REASON_LABEL = {"CANCEL": "KHÁCH HỦY ĐƠN", "RETURN": "KHÁCH TRẢ HÀNG"}
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS = {"s": MAIN}
_REF = re.compile(r"(\$?[A-Z]{1,3}\$?)(\d+)")


def _q(name: str) -> str:
    return f"{{{MAIN}}}{name}"


def _shift_refs(text: str, after_row: int, extra: int) -> str:
    """Move every cell reference below `after_row` down by `extra` rows."""

    def move(match: re.Match) -> str:
        row = int(match.group(2))
        return f"{match.group(1)}{row + extra if row > after_row else row}"

    return _REF.sub(move, text)


def _set_cell(sheet: etree._Element, ref: str, value: str | int | float) -> None:
    """Put a value in an existing styled cell; text is stored as a string, never as a formula."""
    cell = sheet.find(f".//s:c[@r='{ref}']", NS)
    if cell is None:
        raise ValueError(f"The template has no cell {ref}")
    for child in list(cell):
        cell.remove(child)
    cell.attrib.pop("t", None)
    if isinstance(value, str):
        cell.set("t", "inlineStr")
        text = etree.SubElement(etree.SubElement(cell, _q("is")), _q("t"))
        text.text = clean_text(value)
    else:
        etree.SubElement(cell, _q("v")).text = (
            repr(value) if isinstance(value, float) else str(value)
        )


def _quantity(value: Decimal | float | int) -> int | float:
    number = Decimal(value)
    return int(number) if number == number.to_integral_value() else float(number)


def _make_room(sheet: etree._Element, extra: int) -> None:
    """Repeat the item row `extra` times below itself; the rows beneath move down."""
    if extra <= 0:
        return
    row = FIRST_ITEM_ROW
    data = sheet.find("s:sheetData", NS)
    rows = list(data)
    item = next(r for r in rows if int(r.get("r")) == row)
    for below in reversed([r for r in rows if int(r.get("r")) > row]):
        below.set("r", str(int(below.get("r")) + extra))
        for cell in below:
            cell.set("r", _shift_refs(cell.get("r"), row, extra))
    anchor = item
    for offset in range(1, extra + 1):
        copy_row = copy.deepcopy(item)
        copy_row.set("r", str(row + offset))
        for cell in copy_row:
            cell.set("r", re.sub(r"\d+", str(row + offset), cell.get("r")))
        anchor.addnext(copy_row)
        anchor = copy_row

    merges = sheet.find("s:mergeCells", NS)
    if merges is not None:
        item_merges = []
        for merge in list(merges):
            ref = merge.get("ref")
            first_row = int(_REF.findall(ref)[0][1])
            last_row = int(_REF.findall(ref)[-1][1])
            if first_row == last_row == row:
                item_merges.append(ref)
            merge.set("ref", _shift_refs(ref, row, extra))
        for ref in item_merges:
            for offset in range(1, extra + 1):
                added = etree.SubElement(merges, _q("mergeCell"))
                added.set("ref", re.sub(r"\d+", str(row + offset), ref))
        merges.set("count", str(len(merges)))
    dimension = sheet.find("s:dimension", NS)
    if dimension is not None:
        dimension.set("ref", _shift_refs(dimension.get("ref"), row, extra))


def render(sales_return) -> bytes:
    lines = [line for line in sales_return.lines if line.return_qty > 0]
    extra = len(lines) - 1
    with zipfile.ZipFile(TEMPLATE) as source:
        sheet = etree.fromstring(source.read(SHEET_PART))
        workbook = source.read(WORKBOOK_PART).decode("utf-8")
        _make_room(sheet, extra)
        _set_cell(sheet, "H6", sales_return.platform_name)
        for index, line in enumerate(lines):
            row = FIRST_ITEM_ROW + index
            _set_cell(sheet, f"C{row}", index + 1)
            _set_cell(sheet, f"D{row}", line.sap_name)
            _set_cell(sheet, f"N{row}", _quantity(line.return_qty))
            _set_cell(sheet, f"P{row}", line.stock_unit)
            _set_cell(sheet, f"AL{row}", REASON_LABEL[sales_return.reason_kind])
        sheet_xml = etree.tostring(sheet, xml_declaration=True, encoding="UTF-8", standalone=True)
        workbook = re.sub(
            r"(<definedName[^>]*>)([^<]*)(</definedName>)",
            lambda m: m.group(1) + _shift_refs(m.group(2), FIRST_ITEM_ROW, extra) + m.group(3),
            workbook,
        )
        out = BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename == SHEET_PART:
                    data = sheet_xml
                elif info.filename == WORKBOOK_PART:
                    data = workbook.encode("utf-8")
                target.writestr(info.filename, data)
    return out.getvalue()
