"""Read a Shopee or TikTok settlement file: the money the platform paid for each order.

The platform is recognised from the file itself. Lazada's Balance Transactions carry no order
id, so that file is refused instead of guessed at. Any unreadable row refuses the whole file, as
with the SAP reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from shoponline.importers.excel_table import (
    FileRejected,
    normalize_header,
    open_workbook,
    parse_signed_money,
    read_sheet,
)

SHOPEE_SHEET = "Transaction Report"
SHOPEE_MARKER = "Ngày"
SHOPEE_REQUIRED = ("Ngày", "Loại giao dịch", "Mã đơn hàng", "Số tiền", "Trạng thái")
SHOPEE_OK_STATUS = "Giao dịch thành công"
LAZADA_SHEET = "Balance Transactions"
TIKTOK_REQUIRED = (
    "ID đơn hàng/điều chỉnh",
    "Loại giao dịch",
    "Thời gian quyết toán đơn hàng",
    "Tổng số tiền quyết toán",
    "ID đơn hàng liên quan",
)
TIKTOK_ORDER_TYPE = "Đơn hàng"
MAX_ORDER_ID = 40
MAX_LINE_KEY = 200


@dataclass(frozen=True)
class SettlementRow:
    platform_order_id: str
    line_key: str
    amount: int
    settled_at: datetime


@dataclass
class SettlementFile:
    platform: str
    rows: list[SettlementRow] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _parse_time(text: str, formats: tuple[str, ...], field_name: str) -> datetime:
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"{field_name} không đúng định dạng ngày: {text!r}")


def _finish(result: SettlementFile, errors: list[str], label: str) -> SettlementFile:
    if errors:
        raise FileRejected(f"File {label} có dòng không đọc được, không nhập gì", errors)
    if not result.rows:
        raise FileRejected(f"File {label} không có giao dịch nào theo đơn")
    return result


def _shopee(worksheet) -> SettlementFile:
    table = read_sheet(worksheet, required=SHOPEE_REQUIRED, header_marker=SHOPEE_MARKER)
    result = SettlementFile("SHOPEE")
    errors: list[str] = []
    seen: dict[str, int] = {}
    for row in table.rows:
        order_id = row["Mã đơn hàng"]
        if not order_id:
            continue
        kind = row["Loại giao dịch"]
        if order_id == "-":
            result.skipped.append(f"Dòng {row.number}: {kind} {row['Số tiền']} (không theo đơn)")
            continue
        if row["Trạng thái"] != SHOPEE_OK_STATUS:
            result.skipped.append(f"Dòng {row.number}: đơn {order_id}, {row['Trạng thái']}")
            continue
        try:
            if len(order_id) > MAX_ORDER_ID:
                raise ValueError(f"Mã đơn dài quá {MAX_ORDER_ID} ký tự")
            amount = parse_signed_money(row["Số tiền"], "Số tiền")
            when = _parse_time(row["Ngày"], ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"), "Ngày")
            base = f"{order_id}|{row['Ngày']}|{kind}|{amount}"
            seen[base] = seen.get(base, 0) + 1
            key = f"{base}|#{seen[base]}"
            if len(key) > MAX_LINE_KEY:
                raise ValueError("Khóa dòng quá dài")
            result.rows.append(SettlementRow(order_id, key, amount, when))
        except ValueError as exc:
            errors.append(f"Dòng {row.number}: {exc}")
    return _finish(result, errors, "Shopee")


def _tiktok(worksheet) -> SettlementFile:
    table = read_sheet(worksheet, required=TIKTOK_REQUIRED)
    result = SettlementFile("TIKTOK")
    errors: list[str] = []
    keys: set[str] = set()
    for row in table.rows:
        transaction = row["ID đơn hàng/điều chỉnh"]
        related = row["ID đơn hàng liên quan"]
        if not transaction:
            continue
        if row["Loại giao dịch"] != TIKTOK_ORDER_TYPE:
            result.skipped.append(
                f"{row['Loại giao dịch'] or 'không rõ loại'}: ID {transaction}, đơn liên quan "
                f"{related or '-'}"
            )
            continue
        try:
            order_id = related or transaction
            if len(order_id) > MAX_ORDER_ID:
                raise ValueError(f"Mã đơn dài quá {MAX_ORDER_ID} ký tự")
            if len(transaction) > MAX_LINE_KEY:
                raise ValueError("Khóa dòng quá dài")
            if transaction in keys:
                raise ValueError(f"ID giao dịch {transaction} lặp trong file")
            keys.add(transaction)
            amount = parse_signed_money(row["Tổng số tiền quyết toán"], "Tổng số tiền quyết toán")
            when = _parse_time(
                row["Thời gian quyết toán đơn hàng"],
                ("%Y/%m/%d", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"),
                "Thời gian quyết toán đơn hàng",
            )
            result.rows.append(SettlementRow(order_id, transaction, amount, when))
        except ValueError as exc:
            errors.append(f"Dòng {row.number}: {exc}")
    return _finish(result, errors, "TikTok")


def read_settlement_file(source: str | Path | BinaryIO) -> SettlementFile:
    workbook = open_workbook(source)
    try:
        names = {normalize_header(n): n for n in workbook.sheetnames}
        if SHOPEE_SHEET in names:
            return _shopee(workbook[names[SHOPEE_SHEET]])
        if LAZADA_SHEET in names:
            raise FileRejected(
                "File Lazada Balance Transactions không có mã đơn, không lấy được tiền vô theo đơn"
            )
        first = workbook.worksheets[0]
        header = next(first.iter_rows(max_row=1, values_only=True), ())
        if header and normalize_header(header[0]) == TIKTOK_REQUIRED[0]:
            return _tiktok(first)
        raise FileRejected(
            f"Không nhận ra file quyết toán. Chỉ nhận file Shopee (sheet '{SHOPEE_SHEET}') và "
            "TikTok (sheet 'Chi tiết đơn hàng'); file có các sheet: "
            + ", ".join(workbook.sheetnames)
        )
    finally:
        workbook.close()
