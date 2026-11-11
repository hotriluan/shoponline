"""Shopee "chờ giao hàng" export (sheet `orders`, one row per order line)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from shoponline.domain.order import ParsedItem, ParsedOrder, default_address
from shoponline.importers.excel_table import FileRejected, parse_money, parse_quantity, read_table

PLATFORM = "SHOPEE"
SHEET = "orders"
COL_ORDER_ID = "Mã đơn hàng"
COL_ORDERED_AT = "Ngày đặt hàng"
COL_PRODUCT = "Tên sản phẩm"
COL_VARIATION = "Tên phân loại hàng"
COL_QUANTITY = "Số lượng"
COL_PRICE = "Giá gốc"
COL_SELLER_SUBSIDY = "Người bán trợ giá"
COL_SHOPEE_SUBSIDY = "Được Shopee trợ giá"
COL_DISTRICT = "TP / Quận / Huyện"
COL_PROVINCE = "Tỉnh/Thành phố"
REQUIRED = (
    COL_ORDER_ID,
    COL_ORDERED_AT,
    COL_PRODUCT,
    COL_VARIATION,
    COL_QUANTITY,
    COL_PRICE,
    COL_SELLER_SUBSIDY,
    COL_SHOPEE_SUBSIDY,
    COL_DISTRICT,
    COL_PROVINCE,
)
DATE_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S")


def _parse_datetime(text: str) -> datetime:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"{COL_ORDERED_AT} sai dạng: {text!r}")


def read_shopee_orders(source: str | Path | BinaryIO) -> list[ParsedOrder]:
    table = read_table(source, required=REQUIRED, sheet=SHEET)
    errors: list[str] = []
    grouped: dict[str, dict] = {}
    for row in table.rows:
        try:
            order_id = row[COL_ORDER_ID]
            if not order_id:
                raise ValueError(f"{COL_ORDER_ID} trống")
            seller = parse_money(row[COL_SELLER_SUBSIDY], COL_SELLER_SUBSIDY)
            shopee = parse_money(row[COL_SHOPEE_SUBSIDY], COL_SHOPEE_SUBSIDY)
            item = ParsedItem(
                product_name=row[COL_PRODUCT],
                variation_name=row[COL_VARIATION],
                quantity=parse_quantity(row[COL_QUANTITY], COL_QUANTITY),
                unit_price=parse_money(row[COL_PRICE], COL_PRICE),
                unit_subsidy=seller + shopee,
            )
            if not item.product_name:
                raise ValueError(f"{COL_PRODUCT} trống")
            if item.unit_subsidy > item.unit_price:
                raise ValueError("Trợ giá lớn hơn giá gốc")
            entry = grouped.setdefault(
                order_id,
                {
                    "ordered_at": _parse_datetime(row[COL_ORDERED_AT]),
                    "address": default_address(row[COL_DISTRICT], row[COL_PROVINCE]),
                    "items": [],
                },
            )
            entry["items"].append(item)
        except ValueError as exc:
            errors.append(f"Dòng {row.number}: {exc}")
    if errors:
        raise FileRejected("File Shopee có dòng không đọc được, không nhập gì", errors)
    if not grouped:
        raise FileRejected("File Shopee không có đơn nào")
    return [
        ParsedOrder(
            platform=PLATFORM,
            platform_order_id=order_id,
            ordered_at=entry["ordered_at"],
            items=tuple(entry["items"]),
            default_address=entry["address"],
        )
        for order_id, entry in grouped.items()
    ]
