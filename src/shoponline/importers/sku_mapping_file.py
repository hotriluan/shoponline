"""Mapping table upload: one sheet with columns Tên sản phẩm, Tên phân loại, Mã SAP, Tên SAP."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

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


def import_mapping_file(
    session: Session, source: str | Path | BinaryIO, platform: str, actor: str
) -> MappingImportResult:
    table = read_table(source, required=REQUIRED)
    rows, errors = [], []
    for row in table.rows:
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
        raise FileRejected("Bảng ánh xạ không có dòng nào")
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
    return MappingImportResult(saved=saved, unchanged=unchanged, fixed_orders=fixed)
