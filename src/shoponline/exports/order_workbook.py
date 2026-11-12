"""Batch -> `ĐƠN HÀNG ONLINE <SÀN> ddmmyy.xlsx`, the sheet sales admins key SOs from.

Layout follows the hand-made files: title in E3, customer block D5:E7, table header on row 9,
data from row 10. Values only, no formulas. Orders without discount come first because the
shared ZDI1 condition record forces discounted SOs to be created last.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Font

from shoponline.db.models import OrderBatch, PlatformSetting, SalesOrder
from shoponline.domain import states

HEADER_ROW = 9
FIRST_DATA_ROW = 10
COLUMNS = (
    "Ngày",
    "Đơn Hàng",
    "Mã Số Đơn Hàng",
    "Tên Sản Phẩm",
    "Mã SP",
    "Số Lượng",
    "Đơn Giá",
    "Thành Tiền",
    "Sale",
)
# Per-unit subsidy goes here (assumption pending owner confirmation; change in one place).
SUBSIDY_COLUMN = "Sale"
MONEY_FORMAT = "#,##0"
DATE_FORMAT = "dd/mm/yyyy"
COLUMN_WIDTHS = {"A": 12, "B": 10, "C": 24, "D": 40, "E": 14, "F": 10, "G": 14, "H": 16, "I": 12}


@dataclass
class OrderFile:
    workbook: Workbook
    file_name: str
    included: int
    excluded: int


def order_file_name(platform: str, processing_date: date) -> str:
    return f"ĐƠN HÀNG ONLINE {platform.upper()} {processing_date:%d%m%y}.xlsx"


def _sorted_orders(orders: Iterable[SalesOrder]) -> list[SalesOrder]:
    def has_discount(order: SalesOrder) -> bool:
        return any(item.unit_subsidy > 0 for item in order.items)

    return sorted(orders, key=lambda o: (has_discount(o), o.ordered_at, o.platform_order_id))


def build_order_workbook(
    setting: PlatformSetting, batch: OrderBatch, orders: Iterable[SalesOrder]
) -> OrderFile:
    orders = list(orders)
    ready = _sorted_orders(o for o in orders if o.status == states.READY)
    skipped = sum(1 for o in orders if o.status in (states.MAPPING_ERROR, states.NEED_REVIEW))

    wb = Workbook()
    ws = wb.active
    ws.title = setting.platform.upper()
    bold = Font(bold=True)
    ws["E3"] = f"ĐƠN HÀNG THÁNG {batch.processing_date:%m/%Y}"
    ws["D5"] = "Customer Name/Tên Khách hàng:"
    ws["E5"] = setting.display_name
    ws["D6"] = "Mã số khách hàng/SAP Code:"
    ws["E6"] = int(setting.sap_customer)
    ws["D7"] = "Địa chỉ khách hàng: "
    for ref in ("E3", "D5", "E5", "D6", "D7"):
        ws[ref].font = bold
    for col, title in enumerate(COLUMNS, start=1):
        ws.cell(HEADER_ROW, col, title).font = bold
    for letter, width in COLUMN_WIDTHS.items():
        ws.column_dimensions[letter].width = width

    col = {name: index for index, name in enumerate(COLUMNS, start=1)}
    row = FIRST_DATA_ROW
    for seq, order in enumerate(ready, start=1):
        for item in order.items:
            values = {
                "Ngày": batch.processing_date,
                "Đơn Hàng": str(seq),
                "Mã Số Đơn Hàng": order.platform_order_id,
                "Tên Sản Phẩm": item.sap_name,
                "Mã SP": int(item.material_number),
                "Số Lượng": item.quantity,
                "Đơn Giá": item.unit_price,
                "Thành Tiền": item.quantity * item.unit_price,
                SUBSIDY_COLUMN: item.unit_subsidy or None,
            }
            for name, value in values.items():
                ws.cell(row, col[name], value)
            ws.cell(row, col["Ngày"]).number_format = DATE_FORMAT
            ws.cell(row, col["Đơn Hàng"]).number_format = "@"
            order_cell = ws.cell(row, col["Mã Số Đơn Hàng"])
            order_cell.number_format = "@"  # keep 18-digit TikTok ids intact
            order_cell.data_type = "s"
            for name in ("Đơn Giá", "Thành Tiền", SUBSIDY_COLUMN):
                ws.cell(row, col[name]).number_format = MONEY_FORMAT
            row += 1

    return OrderFile(
        workbook=wb,
        file_name=order_file_name(setting.platform, batch.processing_date),
        included=len(ready),
        excluded=skipped,
    )
