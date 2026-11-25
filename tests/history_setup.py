"""A small history workbook shaped like the accountants' file, for tests."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

HEADER = (
    "Division",
    "createTime",
    "month",
    "year",
    "billingName",
    "billingPhone",
    "billingCity",
    "Cust + time",
    "Transaction",
    "Customer paid",
    "unitPrice ",
    "sellerDiscountTotal",
    "shippingFee",
    "Quantity",
    "itemName",
    "Product Classification SKU",
    "variation",
)


def line(
    division="Shopee Bình Dương",
    created="2025-11-14 16:21",
    month=11,
    year=2025,
    name="An",
    city="Kiên Giang",
    paid=811000,
    unit=652126,
    quantity=1,
    item="Propan - EDP-551",
    size="5 kg set",
    variation="White",
):
    return (
        division, created, month, year, name, "******99", city, None, None,
        paid, unit, None, None, quantity, item, size, variation,
    )  # fmt: skip


def write(path: Path, rows: list[tuple]) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADER)
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    return path
