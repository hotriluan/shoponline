"""TikTok Shop "chờ vận chuyển" export (sheet `OrderSKUList`).

Row 1 is the header and row 2 describes each column; only rows whose Order ID is all digits
are orders. Discounts are per line (not per unit), unlike Shopee.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from shoponline.domain.order import ParsedItem, ParsedOrder, default_address
from shoponline.importers.excel_table import FileRejected, parse_money, parse_quantity, read_table

PLATFORM = "TIKTOK"
SHEET = "OrderSKUList"
COL_ORDER_ID = "Order ID"
COL_CREATED = "Created Time"
COL_PRODUCT = "Product Name"
COL_VARIATION = "Variation"
COL_QUANTITY = "Quantity"
COL_PRICE = "SKU Unit Original Price"
COL_SELLER_DISCOUNT = "SKU Seller Discount"
COL_PLATFORM_DISCOUNT = "SKU Platform Discount"
COL_DISTRICT = "District"
COL_PROVINCE = "Province"
REQUIRED = (
    COL_ORDER_ID,
    COL_CREATED,
    COL_PRODUCT,
    COL_VARIATION,
    COL_QUANTITY,
    COL_PRICE,
    COL_SELLER_DISCOUNT,
    COL_PLATFORM_DISCOUNT,
    COL_DISTRICT,
    COL_PROVINCE,
)
# Day first: 11/11/2026 11:36:57
DATE_FORMATS = ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M")


def _parse_datetime(text: str) -> datetime:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"{COL_CREATED} sai dạng: {text!r}")


def read_tiktok_orders(source: str | Path | BinaryIO) -> list[ParsedOrder]:
    table = read_table(source, required=REQUIRED, sheet=SHEET)
    errors: list[str] = []
    grouped: dict[str, dict] = {}
    for row in table.rows:
        order_id = row[COL_ORDER_ID]
        if not order_id.isdigit():
            continue  # the column-description row and blank rows
        try:
            quantity = parse_quantity(row[COL_QUANTITY], COL_QUANTITY)
            line_discount = parse_money(
                row[COL_SELLER_DISCOUNT], COL_SELLER_DISCOUNT
            ) + parse_money(row[COL_PLATFORM_DISCOUNT], COL_PLATFORM_DISCOUNT)
            item = ParsedItem(
                product_name=row[COL_PRODUCT],
                variation_name=row[COL_VARIATION],
                quantity=quantity,
                unit_price=parse_money(row[COL_PRICE], COL_PRICE),
                unit_subsidy=line_discount // quantity,
            )
            if not item.product_name:
                raise ValueError(f"{COL_PRODUCT} trống")
            if item.unit_subsidy > item.unit_price:
                raise ValueError("Trợ giá lớn hơn giá gốc")
            entry = grouped.setdefault(
                order_id,
                {
                    "ordered_at": _parse_datetime(row[COL_CREATED]),
                    "address": default_address(row[COL_DISTRICT], row[COL_PROVINCE]),
                    "items": [],
                    "reasons": [],
                },
            )
            entry["items"].append(item)
            if line_discount % quantity:
                entry["reasons"].append(
                    f"Trợ giá dòng {row.number} ({line_discount}) không chia hết cho "
                    f"số lượng {quantity}"
                )
        except ValueError as exc:
            errors.append(f"Dòng {row.number}: {exc}")
    if errors:
        raise FileRejected("File TikTok có dòng không đọc được, không nhập gì", errors)
    if not grouped:
        raise FileRejected("File TikTok không có đơn nào")
    return [
        ParsedOrder(
            platform=PLATFORM,
            platform_order_id=order_id,
            ordered_at=entry["ordered_at"],
            items=tuple(entry["items"]),
            default_address=entry["address"],
            review_reasons=tuple(entry["reasons"]),
        )
        for order_id, entry in grouped.items()
    ]
