"""Read the accountants' `Shop Online 2022-2026` history file into clean sale lines.

The file has no order id, material or invoice number. A line is told from the others by its
fields (see `line_key`), an order by Division + customer name + the createTime as written.

The period is the file's own `month` / `year`. `createTime` is written three ways (and a few
other ways by hand), sometimes with day and month swapped, so it only gives `ordered_on` when a
reading agrees with the period; otherwise `ordered_on` stays empty.

Boundary: periods up to 10/2026 are taken. A line of 11/2026 is taken only when its day is known
and before REPORTING_CUTOVER (the system holds the orders from then on). Any other line is
rejected with its reason, never guessed.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import BinaryIO

from shoponline.domain.provinces import fold_key
from shoponline.importers.excel_table import FileRejected, parse_money, read_table
from shoponline.reports import REPORTING_CUTOVER

COL_DIVISION = "Division"
COL_CREATED = "createTime"
COL_MONTH = "month"
COL_YEAR = "year"
COL_NAME = "billingName"
COL_PHONE = "billingPhone"
COL_CITY = "billingCity"
COL_PAID = "Customer paid"
COL_PRICE = "unitPrice"
COL_DISCOUNT = "sellerDiscountTotal"
COL_SHIPPING = "shippingFee"
COL_QUANTITY = "Quantity"
COL_ITEM = "itemName"
COL_SIZE = "Product Classification SKU"
COL_VARIATION = "variation"
REQUIRED = (
    COL_DIVISION,
    COL_CREATED,
    COL_MONTH,
    COL_YEAR,
    COL_NAME,
    COL_CITY,
    COL_PAID,
    COL_QUANTITY,
    COL_ITEM,
)
# createTime as the file writes it: year-month-day, day-month-year, year-day-month, "07 Mar 2026".
DATE_FORMATS = ("%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", "%Y-%d-%m %H:%M", "%d %b %Y %H:%M")


@dataclass(frozen=True)
class HistoryLine:
    period: date
    ordered_on: date | None
    shop_code: str
    customer_name: str | None
    customer_phone: str | None
    city_raw: str | None
    city_key: str | None
    item_name: str | None
    size: str | None
    variation: str | None
    quantity: int
    customer_paid: int
    unit_price: int | None
    seller_discount: int | None
    shipping_fee: int | None
    order_key: str
    line_key: str
    source_row: int


@dataclass(frozen=True)
class Rejected:
    row: int
    reason: str


@dataclass
class HistoryRead:
    lines: list[HistoryLine] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)


def division_key(text: str) -> str:
    """Division as compared: no case, one space between words ("tiktok Bình Dương")."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def _text(value: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def _money(value: str, field_name: str) -> int | None:
    return parse_money(value, field_name) if value.strip() else None


def ordered_on_of(created: str, period: date) -> date | None:
    """The day of createTime read the first way that lands in the period's month."""
    text = re.sub(r"\s+", " ", created).strip()
    for pattern in DATE_FORMATS:
        try:
            moment = datetime.strptime(text, pattern)
        except ValueError:
            continue
        if (moment.year, moment.month) == (period.year, period.month):
            return moment.date()
    return None


def _hash(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).hexdigest()


def _period(year: str, month: str) -> date:
    y, m = int(year), int(month)
    if not (2000 <= y <= 2100 and 1 <= m <= 12):
        raise ValueError(f"kỳ {month}/{year} không hợp lệ")
    return date(y, m, 1)


def _boundary_problem(period: date, ordered_on: date | None) -> str:
    cutover = REPORTING_CUTOVER.date()
    if (period.year, period.month) < (cutover.year, cutover.month):
        return ""
    if (period.year, period.month) == (cutover.year, cutover.month):
        if ordered_on is None:
            return "kỳ 11/2026 nhưng không đọc được ngày đặt"
        if ordered_on >= cutover:
            return f"đặt từ {cutover.isoformat()}, hệ thống đã có đơn này"
        return ""
    return f"kỳ {period.month}/{period.year} sau ngày chuyển sang dữ liệu hệ thống"


def read_history(source: str | Path | BinaryIO, divisions: Mapping[str, str]) -> HistoryRead:
    """`divisions` maps division_key(Division) to a shop code. Rejects the whole file when a
    required column is missing; a bad line is rejected on its own, with the reason."""
    table = read_table(source, required=REQUIRED)
    if not table.rows:
        raise FileRejected("File lịch sử không có dòng nào")
    result = HistoryRead()
    seen: Counter[str] = Counter()
    for row in table.rows:
        try:
            shop_code = divisions.get(division_key(row[COL_DIVISION]))
            if shop_code is None:
                raise ValueError(f"Division '{row[COL_DIVISION]}' không khớp shop nào")
            period = _period(row[COL_YEAR], row[COL_MONTH])
            if not row[COL_PAID].strip():
                raise ValueError("Customer paid trống")
            if not row[COL_QUANTITY].strip():
                raise ValueError("Quantity trống")
            paid = parse_money(row[COL_PAID], COL_PAID)
            quantity = parse_money(row[COL_QUANTITY], COL_QUANTITY)
            if quantity <= 0:
                raise ValueError(f"Quantity phải lớn hơn 0: {row[COL_QUANTITY]!r}")
            ordered_on = ordered_on_of(row[COL_CREATED], period)
            problem = _boundary_problem(period, ordered_on)
            if problem:
                raise ValueError(problem)
            customer = _text(row[COL_NAME])
            created = _text(row[COL_CREATED]) or ""
            order_key = _hash(shop_code, customer, created)
            fields = (
                shop_code,
                created,
                customer,
                _text(row[COL_ITEM]),
                _text(row[COL_SIZE]) if COL_SIZE in table.columns else None,
                _text(row[COL_VARIATION]) if COL_VARIATION in table.columns else None,
                quantity,
                paid,
            )
            base = _hash(*fields)
            line_key = _hash(base, seen[base])
            seen[base] += 1
            result.lines.append(
                HistoryLine(
                    period=period,
                    ordered_on=ordered_on,
                    shop_code=shop_code,
                    customer_name=customer,
                    customer_phone=_text(row[COL_PHONE]) if COL_PHONE in table.columns else None,
                    city_raw=_text(row[COL_CITY]),
                    city_key=fold_key(row[COL_CITY]) or None,
                    item_name=_text(row[COL_ITEM]),
                    size=fields[4],
                    variation=fields[5],
                    quantity=quantity,
                    customer_paid=paid,
                    unit_price=_money(row[COL_PRICE], COL_PRICE)
                    if COL_PRICE in table.columns
                    else None,
                    seller_discount=(
                        _money(row[COL_DISCOUNT], COL_DISCOUNT)
                        if COL_DISCOUNT in table.columns
                        else None
                    ),
                    shipping_fee=(
                        _money(row[COL_SHIPPING], COL_SHIPPING)
                        if COL_SHIPPING in table.columns
                        else None
                    ),
                    order_key=order_key,
                    line_key=line_key,
                    source_row=row.number,
                )
            )
        except ValueError as exc:
            result.rejected.append(Rejected(row.number, str(exc)))
    return result
