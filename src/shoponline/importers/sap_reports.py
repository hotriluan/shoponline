"""SAP report exports: zrsd001 (sales orders with PO No) and zrsd004 (deliveries)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import BinaryIO

from shoponline.importers.excel_table import FileRejected, parse_money, read_table

ZRSD001_REQUIRED = (
    "PO No",
    "Doc.Date",
    "SalesDoc",
    "Sold-To",
    "SalesDoc Item",
    "Material No",
    "Order Qty",
    "Net Value (Incl)",
)
ZRSD004_REQUIRED = ("Delivery", "SO Reference", "Sold-to Party", "Actual GI Date")
DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y")


def parse_report_date(text: str, field_name: str) -> date:
    value = text.strip().split(" ")[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"{field_name} sai dạng: {text!r}")


@dataclass
class SoLine:
    item_no: int
    material_number: str
    quantity: Decimal
    net_value_incl: int


@dataclass
class SoReport:
    so_number: str
    po_no: str
    sold_to: str
    doc_date: date
    lines: list[SoLine] = field(default_factory=list)

    @property
    def net_value_incl(self) -> int:
        return sum(line.net_value_incl for line in self.lines)


def read_zrsd001(source: str | Path | BinaryIO) -> list[SoReport]:
    table = read_table(source, required=ZRSD001_REQUIRED)
    errors: list[str] = []
    reports: dict[str, SoReport] = {}
    for row in table.rows:
        so_number = row["SalesDoc"]
        if not so_number:
            continue  # total rows
        try:
            po_no = row["PO No"]
            if not po_no:
                raise ValueError("PO No trống")
            try:
                quantity = Decimal(row["Order Qty"] or "0")
            except InvalidOperation as exc:
                raise ValueError(f"Order Qty không phải số: {row['Order Qty']!r}") from exc
            line = SoLine(
                item_no=int(row["SalesDoc Item"]),
                material_number=row["Material No"],
                quantity=quantity,
                net_value_incl=parse_money(row["Net Value (Incl)"], "Net Value (Incl)"),
            )
            report = reports.setdefault(
                so_number,
                SoReport(
                    so_number=so_number,
                    po_no=po_no,
                    sold_to=row["Sold-To"],
                    doc_date=parse_report_date(row["Doc.Date"], "Doc.Date"),
                ),
            )
            if report.po_no != po_no:
                raise ValueError(f"SO {so_number} có hai PO No: {report.po_no}, {po_no}")
            if any(existing.item_no == line.item_no for existing in report.lines):
                raise ValueError(f"SO {so_number} lặp dòng {line.item_no}")
            report.lines.append(line)
        except ValueError as exc:
            errors.append(f"Dòng {row.number}: {exc}")
    if errors:
        raise FileRejected("File zrsd001 có dòng không đọc được, không nhập gì", errors)
    if not reports:
        raise FileRejected("File zrsd001 không có SO nào")
    return list(reports.values())


@dataclass(frozen=True)
class DeliveryRow:
    delivery: str
    so_number: str
    sold_to: str
    gi_date: date | None


def read_zrsd004(source: str | Path | BinaryIO) -> list[DeliveryRow]:
    table = read_table(source, required=ZRSD004_REQUIRED)
    rows: list[DeliveryRow] = []
    errors: list[str] = []
    for row in table.rows:
        if not row["Delivery"] or not row["SO Reference"]:
            continue  # total rows
        try:
            gi = row["Actual GI Date"]
            rows.append(
                DeliveryRow(
                    delivery=row["Delivery"],
                    so_number=row["SO Reference"],
                    sold_to=row["Sold-to Party"],
                    gi_date=parse_report_date(gi, "Actual GI Date") if gi else None,
                )
            )
        except ValueError as exc:
            errors.append(f"Dòng {row.number}: {exc}")
    if errors:
        raise FileRejected("File zrsd004 có dòng không đọc được", errors)
    if not rows:
        raise FileRejected("File zrsd004 không có DO nào")
    return rows
