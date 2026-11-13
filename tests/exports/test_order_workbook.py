from datetime import date, datetime
from io import BytesIO

from openpyxl import load_workbook

from shoponline.db.models import OrderBatch, PlatformSetting, SalesOrder, SalesOrderItem
from shoponline.domain import states
from shoponline.exports.order_workbook import build_order_workbook, order_file_name

SETTING = PlatformSetting(platform="TIKTOK", display_name="TIKTOK", sap_customer="1200001146")
BATCH = OrderBatch(
    platform="TIKTOK", processing_date=date(2026, 11, 11), gi_date=date(2026, 11, 12)
)


def _order(order_id, hour, status=states.READY, subsidy=0, quantity=1, lines=1):
    order = SalesOrder(
        platform="TIKTOK",
        platform_order_id=order_id,
        ordered_at=datetime(2026, 11, 11, hour),
        status=status,
    )
    order.items = [
        SalesOrderItem(
            line_no=n,
            product_name="P",
            variation_name=f"V{n}",
            quantity=quantity,
            unit_price=120000,
            unit_subsidy=subsidy,
            material_number="100001787",
            sap_name="V-09 REDDISH CLAY 2004 VN-0.8L",
        )
        for n in range(1, lines + 1)
    ]
    return order


def _reload(order_file):
    buffer = BytesIO()
    order_file.workbook.save(buffer)
    buffer.seek(0)
    return load_workbook(buffer)


def test_layout_and_values():
    orders = [
        _order("587114288679978479", 9, quantity=2),
        _order("587000000000000002", 8, subsidy=15000),
        _order("587000000000000003", 10),
        _order("587000000000000004", 7, status=states.MAPPING_ERROR),
        _order("587000000000000005", 7, status=states.CANCELLED),
    ]
    result = build_order_workbook(SETTING, BATCH, orders)
    assert (result.included, result.excluded) == (3, 1)
    assert result.file_name == "ĐƠN HÀNG ONLINE TIKTOK 111126.xlsx"

    ws = _reload(result)["TIKTOK"]
    assert ws["E3"].value == "ĐƠN HÀNG THÁNG 11/2026"
    assert ws["E5"].value == "TIKTOK"
    assert ws["E6"].value == 1200001146
    header = [ws.cell(9, c).value for c in range(1, 10)]
    assert header == ["Ngày", "Đơn Hàng", "Mã Số Đơn Hàng", "Tên Sản Phẩm", "Mã SP",
                      "Số Lượng", "Đơn Giá", "Thành Tiền", "Sale"]

    ids = [ws.cell(r, 3).value for r in range(10, 13)]
    # no-discount orders by order time, discounted order last
    assert ids == ["587114288679978479", "587000000000000003", "587000000000000002"]
    assert all(isinstance(i, str) for i in ids)
    assert ws.cell(10, 3).number_format == "@"
    assert ws.cell(10, 8).value == ws.cell(10, 6).value * ws.cell(10, 7).value == 240000
    assert ws.cell(10, 9).value is None
    assert ws.cell(12, 9).value == 15000
    assert ws.cell(13, 3).value is None
    assert ws.cell(10, 1).value.date() == date(2026, 11, 11)


def test_multi_line_order_shares_sequence_number():
    result = build_order_workbook(SETTING, BATCH, [_order("587000000000000006", 8, lines=2)])
    ws = _reload(result)["TIKTOK"]
    assert ws.cell(10, 2).value == ws.cell(11, 2).value == "1"


def test_file_name_uses_platform_and_day():
    assert order_file_name("shopee", date(2026, 1, 5)) == "ĐƠN HÀNG ONLINE SHOPEE 050126.xlsx"
