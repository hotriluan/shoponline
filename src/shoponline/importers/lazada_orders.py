"""Lazada "chờ giao hàng" export (first sheet, one row per unit sold).

Lazada has no quantity column: every unit is its own row (`orderItemId`), and the rows of
one order share `orderNumber`. Discounts are per row, i.e. per unit, and exported as
negative numbers. Unlike Shopee and TikTok, the billing name and address are not masked,
so they fill the customer row directly.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from shoponline.domain.order import ParsedItem, ParsedOrder, default_address
from shoponline.importers.excel_table import FileRejected, parse_money, read_table

PLATFORM = "LAZADA"
COL_ORDER_ID = "orderNumber"
COL_CREATED = "createTime"
COL_PRODUCT = "itemName"
COL_VARIATION = "variation"
COL_PRICE = "unitPrice"
COL_SELLER_DISCOUNT = "sellerDiscountTotal"
COL_PLATFORM_DISCOUNT = "platformDiscountTotal"
COL_NAME = "billingName"
COL_STREET = "billingAddr"
COL_WARD = "billingAddr4"
COL_PROVINCE = "billingAddr3"
REQUIRED = (
    COL_ORDER_ID,
    COL_CREATED,
    COL_PRODUCT,
    COL_VARIATION,
    COL_PRICE,
    COL_SELLER_DISCOUNT,
    COL_PLATFORM_DISCOUNT,
    COL_NAME,
    COL_STREET,
    COL_WARD,
    COL_PROVINCE,
)
# "13 Nov 2026 07:59"; the ISO forms cover cells Excel stored as real dates.
DATE_FORMATS = ("%d %b %Y %H:%M", "%d %b %Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


def _parse_datetime(text: str) -> datetime:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"{COL_CREATED} sai dạng: {text!r}")


def _discount(text: str, field: str) -> int:
    """'-12500.00' -> 12500. Lazada writes discounts as negative amounts."""
    return parse_money(text.strip().removeprefix("-"), field)


def _street(text: str) -> str:
    """Lazada often repeats the street: '146 Đường A, 146 Đường A' -> '146 Đường A'."""
    parts: list[str] = []
    for part in (p.strip() for p in text.split(",")):
        if part and part not in parts:
            parts.append(part)
    return ", ".join(parts)


def read_lazada_orders(source: str | Path | BinaryIO) -> list[ParsedOrder]:
    table = read_table(source, required=REQUIRED)
    errors: list[str] = []
    grouped: dict[str, dict] = {}
    for row in table.rows:
        try:
            order_id = row[COL_ORDER_ID]
            if not order_id:
                raise ValueError(f"{COL_ORDER_ID} trống")
            product = row[COL_PRODUCT]
            if not product:
                raise ValueError(f"{COL_PRODUCT} trống")
            price = parse_money(row[COL_PRICE], COL_PRICE)
            subsidy = _discount(row[COL_SELLER_DISCOUNT], COL_SELLER_DISCOUNT) + _discount(
                row[COL_PLATFORM_DISCOUNT], COL_PLATFORM_DISCOUNT
            )
            if subsidy > price:
                raise ValueError("Trợ giá lớn hơn giá gốc")
            entry = grouped.setdefault(
                order_id,
                {
                    "ordered_at": _parse_datetime(row[COL_CREATED]),
                    "name": row[COL_NAME] or None,
                    "address": default_address(
                        _street(row[COL_STREET]), row[COL_WARD], row[COL_PROVINCE]
                    ),
                    "units": {},
                },
            )
            key = (product, row[COL_VARIATION], price, subsidy)
            entry["units"][key] = entry["units"].get(key, 0) + 1
        except ValueError as exc:
            errors.append(f"Dòng {row.number}: {exc}")
    if errors:
        raise FileRejected("File Lazada có dòng không đọc được, không nhập gì", errors)
    if not grouped:
        raise FileRejected("File Lazada không có đơn nào")
    return [
        ParsedOrder(
            platform=PLATFORM,
            platform_order_id=order_id,
            ordered_at=entry["ordered_at"],
            items=tuple(
                ParsedItem(
                    product_name=product,
                    variation_name=variation,
                    quantity=quantity,
                    unit_price=price,
                    unit_subsidy=subsidy,
                )
                for (product, variation, price, subsidy), quantity in entry["units"].items()
            ),
            default_address=entry["address"],
            customer_name=entry["name"],
        )
        for order_id, entry in grouped.items()
    ]
