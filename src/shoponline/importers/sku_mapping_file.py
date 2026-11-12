"""Mapping table upload: one sheet with columns Tên sản phẩm, Tên phân loại, Mã SAP, Tên SAP.

Rows whose Mã SAP and Tên SAP are both blank are skipped, so the downloaded list of unmapped
products can be uploaded back with only some rows filled in.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy.orm import Session

from shoponline.domain.sku_mapping import upsert_mapping, validate_material_number
from shoponline.importers.excel_table import FileRejected, read_table
from shoponline.importers.order_import import reevaluate_mapping_errors

COL_PRODUCT = "Tên sản phẩm"
COL_VARIATION = "Tên phân loại"
COL_MATERIAL = "Mã SAP"
COL_SAP_NAME = "Tên SAP"
REQUIRED = (COL_PRODUCT, COL_VARIATION, COL_MATERIAL, COL_SAP_NAME)


@dataclass
class MappingImportResult:
    saved: int
    unchanged: int
    fixed_orders: int
    skipped: int = 0


def build_mapping_template(pairs: list[tuple[str, str]]) -> Workbook:
    """Workbook in the upload layout, product and variation filled, SAP columns left blank."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Ánh xạ"
    sheet.append(list(REQUIRED))
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for product, variation in pairs:
        sheet.append([product, variation or "", "", ""])
    for column, width in zip("ABCD", (60, 30, 14, 40), strict=True):
        sheet.column_dimensions[column].width = width
    # Text format keeps leading zeros and stops Excel turning long codes into numbers.
    for row in sheet.iter_rows(min_row=2, min_col=3, max_col=3):
        row[0].number_format = "@"
    return workbook


def import_mapping_file(
    session: Session, source: str | Path | BinaryIO, platform: str, actor: str
) -> MappingImportResult:
    table = read_table(source, required=REQUIRED)
    rows, errors = [], []
    skipped = 0
    for row in table.rows:
        if not row[COL_MATERIAL] and not row[COL_SAP_NAME]:
            skipped += 1
            continue
        try:
            if not row[COL_PRODUCT]:
                raise ValueError(f"{COL_PRODUCT} trống")
            if not row[COL_SAP_NAME]:
                raise ValueError(f"{COL_SAP_NAME} trống")
            validate_material_number(row[COL_MATERIAL])
            rows.append(row)
        except ValueError as exc:
            errors.append(f"Dòng {row.number}: {exc}")
    if errors:
        raise FileRejected("Bảng ánh xạ có dòng sai, không nhập gì", errors)
    if not rows:
        raise FileRejected("Bảng ánh xạ không có dòng nào điền Mã SAP và Tên SAP")
    saved = unchanged = 0
    for row in rows:
        _, changed = upsert_mapping(
            session,
            platform,
            row[COL_PRODUCT],
            row[COL_VARIATION],
            row[COL_MATERIAL],
            row[COL_SAP_NAME],
            actor,
        )
        saved += changed
        unchanged += not changed
    fixed = reevaluate_mapping_errors(session, platform, actor)
    return MappingImportResult(
        saved=saved, unchanged=unchanged, fixed_orders=fixed, skipped=skipped
    )
