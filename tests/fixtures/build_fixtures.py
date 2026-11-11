"""Build test workbooks with the exact sheet names and headers of the real exports.

All data is invented. Never copy rows from real files into the repo.
Run `python tests/fixtures/build_fixtures.py <folder>` to write a sample set for manual testing.
"""

from __future__ import annotations

import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook


def _nfd(text: str) -> str:
    return unicodedata.normalize("NFD", text)


# Shopee "Order.toship" export: 61 columns. Some real headers are not NFC; keep that here.
SHOPEE_HEADERS = [
    "Mã đơn hàng",
    "Mã Kiện Hàng",
    "Ngày đặt hàng",
    "Trạng Thái Đơn Hàng",
    "Sản Phẩm Bán Chạy",
    "Nhận xét từ Người mua",
    "Mã vận đơn",
    "Đơn Vị Vận Chuyển",
    "Phương thức giao hàng",
    "Loại đơn hàng",
    "Ngày giao hàng dự kiến",
    _nfd("Ngày gửi hàng"),
    "Thời gian giao hàng",
    "Trạng thái Trả hàng/Hoàn tiền",
    "SKU sản phẩm",
    "Tên sản phẩm",
    _nfd("Cân nặng sản phẩm"),
    _nfd("Tổng cân nặng"),
    "SKU phân loại hàng",
    "Tên phân loại hàng",
    "Giá gốc",
    "Người bán trợ giá",
    _nfd("Được Shopee trợ giá"),
    "Tổng số tiền được người bán trợ giá",
    _nfd("Giá ưu đãi"),
    "Số lượng",
    "Số lượng sản phẩm được hoàn trả",
    "Tổng số tiền Người mua thanh toán",
    "Tổng giá trị đơn hàng (VND)",
    "Mã giảm giá của Shop",
    "Hoàn Xu",
    "Mã giảm giá của Shopee",
    "Chỉ tiêu Combo Khuyến Mãi",
    "Giảm giá từ combo Shopee",
    "Giảm giá từ Combo của Shop",
    _nfd("Shopee Xu được hoàn"),
    _nfd("Số tiền được giảm khi thanh toán bằng thẻ Ghi nợ"),
    "Trade-in Discount",
    "Trade-in Bonus",
    _nfd("Phí vận chuyển (dự kiến)"),
    "Trade-in Bonus by Seller",
    _nfd("Phí vận chuyển mà người mua trả"),
    "Phí vận chuyển tài trợ bởi Shopee (dự kiến)",
    "Phí vận chuyển trả hàng (đơn Trả hàng/hoàn tiền)",
    "Tổng số tiền người mua thanh toán",
    "Thời gian hoàn thành đơn hàng",
    "Thời gian đơn hàng được thanh toán",
    "Phương thức thanh toán",
    "Phí cố định",
    "Phí Dịch Vụ",
    "Phí xử lý giao dịch",
    "Tiền ký quỹ",
    "Người Mua",
    "Tên Người nhận",
    "Số điện thoại",
    "Tỉnh/Thành phố",
    "TP / Quận / Huyện",
    "Quận",
    "Địa chỉ nhận hàng",
    "Quốc gia",
    "Ghi chú",
]

TIKTOK_HEADERS = [
    "Order ID",
    "Order Status",
    "Order Substatus",
    "Cancelation/Return Type",
    "Normal or Pre-order",
    "SKU ID",
    "Seller SKU",
    "Product Name",
    "Variation",
    "Quantity",
    "Sku Quantity of return",
    "SKU Unit Original Price",
    "SKU Subtotal Before Discount",
    "SKU Platform Discount",
    "SKU Seller Discount",
    "SKU Subtotal After Discount",
    "Shipping Fee After Discount",
    "Original Shipping Fee",
    "Shipping Fee Seller Discount",
    "Shipping Fee Platform Discount",
    "Payment platform discount",
    "Taxes",
    "Order Amount",
    "Order Refund Amount",
    "Created Time",
    "Paid Time",
    "RTS Time",
    "Shipped Time",
    "Delivered Time",
    "Cancelled Time",
    "Cancel By",
    "Cancel Reason",
    "Fulfillment Type",
    "Warehouse Name",
    "Tracking ID",
    "Delivery Option",
    "Shipping Provider Name",
    "Buyer Message",
    "Buyer Username",
    "Recipient",
    "Phone #",
    "Country",
    "Province",
    "District",
    "Commune",
    "Detail Address",
    "Additional address information",
    "Payment Method",
    "Weight(kg)",
    "Product Category",
    "Package ID",
    "Seller Note",
    "Checked Status",
    "Checked Marked by",
    "Order Channel",
    "Creator Handle",
]
TIKTOK_DESCRIPTIONS = {
    "Order ID": "Platform unique order ID.",
    "Product Name": "Platform product name.",
    "Quantity": "SKU sold quantity in the order.",
    "SKU Unit Original Price": "1 SKU original price.",
    "SKU Seller Discount": "Total seller discount in this SKU ID.",
    "Created Time": "Order created time.",
}

# zrsd001 as exported by SAP (no extra column added by hand)
ZRSD001_HEADERS = [
    "SOffc",
    "DChl",
    "City",
    "Salesman",
    "PO No",
    "CL.Stts",
    "Cust.Grp",
    "Doc.Date",
    "SalesDoc",
    "Sold-To",
    "Customer",
    "SalesDoc Item",
    "Material No",
    "Desc",
    "IP_Desc",
    "SLoc SO",
    "ReqTyp",
    "Sales Unit",
    "Order Qty",
    "Confirm Qty",
    "Deliv Qty",
    "GI Qty",
    "Open Qty",
    "Reject Qty",
    "SLoc Stk",
    "Demand",
    "FreeStk(E) NoSO",
    "FreeStk(UU)",
    "SOH(E)",
    "SOH(E)NoSO",
    "SOH(UU)",
    "PlnGI",
    "Curr",
    "Net Price",
    "Net Value",
    "Tax",
    "Net Value (Incl)",
    "Net Weight",
    "WUn",
    "Volume",
    "VUn",
    "Tonase",
    "TUn",
    "HeadTxt",
    "Price",
    "Discount",
]

# zrsd004 as exported by SAP, before the three columns are inserted
ZRSD004_HEADERS = [
    "Delivery Date",
    "Actual GI Date",
    "Delivery",
    "SO Reference",
    "Req. Type",
    "Delivery Type",
    "Shipping Point",
    "Sloc",
    "Sales Office",
    "Dist. Channel",
    "Cust. Group",
    "Sold-to Party",
    "Ship-to Party",
    "Name of Ship-to",
    "City of Ship-to",
    "Regional Stru. Grp.",
    "Transportation Zone",
    "Salesman ID",
    "Salesman Name",
    "Material",
    "Description",
    "Delivery Qty",
    "Tonase",
    "Tonase Unit",
    "Actual Delivery Qty",
    "Sales Unit",
    "Net Weight",
    "Weight Unit",
    "Volume",
    "Volume Unit",
    "Created By",
    "Product Hierarchy",
    "Line Item",
    "Total Movement Goods Stat",
]


def _write(path: Path, sheet: str, headers: list[str], rows: list[list]) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(headers)
    for row in rows:
        ws.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _by_header(headers: list[str], values: dict[str, object], default: object = "") -> list:
    nfc = {unicodedata.normalize("NFC", h): h for h in headers}
    unknown = set(values) - set(nfc)
    if unknown:
        raise KeyError(f"Unknown columns: {unknown}")
    return [values.get(unicodedata.normalize("NFC", h), default) for h in headers]


def shopee_row(
    order_id: str,
    product: str = "Sơn thử A",
    variation: str = "Màu 01,1 lít",
    quantity: int = 1,
    price: int = 100000,
    seller_subsidy: int = 0,
    shopee_subsidy: int = 0,
    ordered_at: str = "2026-11-11 08:00",
    district: str = "Phường Một",
    province: str = "Tỉnh Thử",
    **extra: object,
) -> dict[str, object]:
    return {
        "Mã đơn hàng": order_id,
        "Ngày đặt hàng": ordered_at,
        "Trạng Thái Đơn Hàng": "Chờ giao hàng",
        "Tên sản phẩm": product,
        "SKU phân loại hàng": "10",
        "Tên phân loại hàng": variation,
        "Giá gốc": f"{price}.00",
        "Người bán trợ giá": f"{seller_subsidy}.00",
        "Được Shopee trợ giá": f"{shopee_subsidy}.00",
        "Số lượng": str(quantity),
        "Tên Người nhận": "N*****A",
        "Số điện thoại": "******00",
        "Tỉnh/Thành phố": province,
        "TP / Quận / Huyện": district,
        "Quốc gia": "VN",
        **extra,
    }


def shopee_orders_file(path: Path, rows: list[dict], *, drop: tuple[str, ...] = ()) -> Path:
    headers = [h for h in SHOPEE_HEADERS if unicodedata.normalize("NFC", h) not in drop]
    data = [_by_header(headers, {k: v for k, v in r.items() if k not in drop}) for r in rows]
    return _write(path, "orders", headers, data)


def tiktok_row(
    order_id: str,
    product: str = "Sơn thử A - 1 lít",
    variation: str = "Màu 01, 1 lít",
    quantity: int = 1,
    price: int = 100000,
    seller_discount: int = 0,
    platform_discount: int = 0,
    created: str = "11/11/2026 09:30:00",
    district: str = "Phường Hai",
    province: str = "Tỉnh Thử",
) -> dict[str, object]:
    return {
        "Order ID": order_id,
        "Order Status": "Cần vận chuyển",
        "Seller SKU": "5",
        "Product Name": product,
        "Variation": variation,
        "Quantity": str(quantity),
        "SKU Unit Original Price": str(price),
        "SKU Subtotal Before Discount": str(price * quantity),
        "SKU Platform Discount": str(platform_discount),
        "SKU Seller Discount": str(seller_discount),
        "Created Time": created,
        "Recipient": "T****",
        "Country": "Việt Nam",
        "Province": province,
        "District": district,
        "Detail Address": "**********",
    }


def tiktok_orders_file(path: Path, rows: list[dict]) -> Path:
    description = [TIKTOK_DESCRIPTIONS.get(h, "") for h in TIKTOK_HEADERS]
    data = [description] + [_by_header(TIKTOK_HEADERS, r) for r in rows]
    return _write(path, "OrderSKUList", TIKTOK_HEADERS, data)


def zrsd001_row(
    so_number: str,
    po_no: str,
    material: str,
    quantity: float = 1.0,
    net_value_incl: int = 100000,
    item_no: str = "10",
    sold_to: str = "1200001145",
    doc_date: date = date(2026, 11, 11),
) -> dict[str, object]:
    return {
        "SOffc": "1401",
        "DChl": "13",
        "PO No": po_no,
        "Doc.Date": datetime.combine(doc_date, datetime.min.time()),
        "SalesDoc": so_number,
        "Sold-To": sold_to,
        "Customer": "Thử",
        "SalesDoc Item": item_no,
        "Material No": material,
        "Desc": f"MAT {material}",
        "Order Qty": quantity,
        "Net Value (Incl)": net_value_incl,
        "Curr": "VND",
    }


def zrsd001_file(path: Path, rows: list[dict]) -> Path:
    return _write(path, "Sheet1", ZRSD001_HEADERS, [_by_header(ZRSD001_HEADERS, r) for r in rows])


def zrsd004_row(
    delivery: str,
    so_number: str,
    material: str,
    quantity: int = 1,
    sold_to: str = "1200001145",
    line_item: int = 10,
    delivery_date: date = date(2026, 11, 11),
    gi_date: date = date(2026, 11, 12),
) -> dict[str, object]:
    return {
        "Delivery Date": datetime.combine(delivery_date, datetime.min.time()),
        "Actual GI Date": datetime.combine(gi_date, datetime.min.time()),
        "Delivery": delivery,
        "SO Reference": so_number,
        "Req. Type": "KSV",
        "Sold-to Party": sold_to,
        "Ship-to Party": sold_to,
        "Name of Ship-to": "Shopee",
        "Material": material,
        "Description": f"MAT {material}",
        "Delivery Qty": quantity,
        "Actual Delivery Qty": quantity,
        "Sales Unit": "PC",
        "Line Item": line_item,
        "Total Movement Goods Stat": "C",
    }


def zrsd004_file(path: Path, rows: list[dict], *, total_rows: bool = True) -> Path:
    data = [_by_header(ZRSD004_HEADERS, r) for r in rows]
    if total_rows:
        qty = sum(r.get("Delivery Qty", 0) for r in rows)
        total = _by_header(ZRSD004_HEADERS, {"Delivery Qty": qty, "Actual Delivery Qty": qty})
        total[0] = total[1] = None
        data += [total, list(total)]
    wb_path = _write(path, "Sheet1", ZRSD004_HEADERS, data)
    return wb_path


def write_sample_set(folder: Path) -> list[Path]:
    """A small consistent day: Shopee + TikTok files and the matching SAP reports."""
    return [
        shopee_orders_file(
            folder / "shopee-orders.xlsx",
            [
                shopee_row("2611110AAAAAAA", quantity=2),
                shopee_row("2611110BBBBBBB", variation="Màu 02,1 lít", seller_subsidy=10000),
                shopee_row("2611110CCCCCCC", product="Bộ thử B", variation="Bộ 1"),
            ],
        ),
        tiktok_orders_file(
            folder / "tiktok-orders.xlsx", [tiktok_row("587000000000000001", quantity=2)]
        ),
        zrsd001_file(
            folder / "zrsd001.xlsx",
            [
                zrsd001_row("210000001", "2611110AAAAAAA", "100000001", 2, 200000),
                zrsd001_row("210000002", "2611110BBBBBBB", "100000002", 1, 90000),
                zrsd001_row("210000003", "2611110CCCCCCC", "100000003", 1, 100000),
                zrsd001_row("210000003", "2611110CCCCCCC", "100000004", 1, 0, item_no="11"),
                zrsd001_row(
                    "210000004", "587000000000000001", "100000001", 2, 200000, sold_to="1200001146"
                ),
            ],
        ),
        zrsd004_file(
            folder / "zrsd004.xlsx",
            [
                zrsd004_row("1900000001", "210000001", "100000001", 2),
                zrsd004_row("1900000002", "210000002", "100000002"),
                zrsd004_row("1900000003", "210000003", "100000003"),
                zrsd004_row("1900000003", "210000003", "100000004", line_item=20),
                zrsd004_row("1900000004", "210000004", "100000001", 2, sold_to="1200001146"),
            ],
        ),
    ]


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "sample-files")
    for written in write_sample_set(target):
        print(written)
