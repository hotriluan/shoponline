import pytest

from shoponline.importers.excel_table import FileRejected
from shoponline.importers.lazada_orders import read_lazada_orders
from shoponline.importers.shopee_orders import read_shopee_orders
from shoponline.importers.tiktok_orders import read_tiktok_orders
from tests.fixtures.build_fixtures import (
    lazada_orders_file,
    lazada_row,
    shopee_orders_file,
    shopee_row,
    tiktok_orders_file,
    tiktok_row,
)


def test_reads_all_columns_when_sheet_dimension_is_wrong(tmp_path):
    # Real Shopee/TikTok exports declare <dimension ref="A1"/> although data spans many columns.
    import re
    import zipfile

    path = shopee_orders_file(tmp_path / "s.xlsx", [shopee_row("X1", quantity=2)])
    patched = tmp_path / "patched.xlsx"
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(patched, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename.startswith("xl/worksheets/sheet"):
                data = re.sub(rb'<dimension ref="[^"]*"/>', b'<dimension ref="A1"/>', data)
            dst.writestr(info, data)
    assert read_shopee_orders(patched)[0].items[0].quantity == 2


def test_shopee_groups_lines_and_reads_money(tmp_path):
    path = shopee_orders_file(
        tmp_path / "s.xlsx",
        [
            shopee_row("2611110AAAAAAA", quantity=3, price=120000),
            shopee_row(
                "2611110AAAAAAA", variation="Màu 02,1 lít", seller_subsidy=5000, shopee_subsidy=2000
            ),
            shopee_row("26111110NE59EY"),
        ],
    )
    orders = read_shopee_orders(path)
    assert [o.platform_order_id for o in orders] == ["2611110AAAAAAA", "26111110NE59EY"]
    first = orders[0]
    assert len(first.items) == 2
    assert first.items[0].quantity == 3
    assert first.items[0].unit_price == 120000
    assert first.items[1].unit_subsidy == 7000
    assert first.ordered_at.hour == 8
    assert first.default_address == "Phường Một, Tỉnh Thử, Việt Nam"


def test_shopee_finds_non_nfc_headers(tmp_path):
    # "Được Shopee trợ giá" is stored decomposed in the fixture, as in the real export
    path = shopee_orders_file(tmp_path / "s.xlsx", [shopee_row("X1", shopee_subsidy=3000)])
    assert read_shopee_orders(path)[0].items[0].unit_subsidy == 3000


def test_shopee_missing_column_rejects_with_name(tmp_path):
    path = shopee_orders_file(tmp_path / "s.xlsx", [shopee_row("X1")], drop=("Giá gốc", "Số lượng"))
    with pytest.raises(FileRejected) as err:
        read_shopee_orders(path)
    assert "Giá gốc" in str(err.value) and "Số lượng" in str(err.value)


def test_shopee_bad_row_rejects_whole_file(tmp_path):
    path = shopee_orders_file(
        tmp_path / "s.xlsx",
        [shopee_row("X1"), shopee_row("X2", **{"Giá gốc": "120000.50"})],
    )
    with pytest.raises(FileRejected, match="Dòng 3"):
        read_shopee_orders(path)


def test_shopee_wrong_sheet_rejected(tmp_path):
    path = tiktok_orders_file(tmp_path / "t.xlsx", [tiktok_row("587000000000000001")])
    with pytest.raises(FileRejected, match="orders"):
        read_shopee_orders(path)


def test_tiktok_skips_description_row_and_keeps_18_digit_id(tmp_path):
    path = tiktok_orders_file(
        tmp_path / "t.xlsx", [tiktok_row("587114288679978479", quantity=2, price=120000)]
    )
    orders = read_tiktok_orders(path)
    assert len(orders) == 1
    assert orders[0].platform_order_id == "587114288679978479"
    assert orders[0].ordered_at.day == 11 and orders[0].ordered_at.month == 11
    assert orders[0].items[0].quantity == 2
    assert orders[0].default_address == "Phường Hai, Tỉnh Thử, Việt Nam"


def test_tiktok_day_first_dates(tmp_path):
    path = tiktok_orders_file(
        tmp_path / "t.xlsx", [tiktok_row("587000000000000002", created="03/11/2026 10:00:00")]
    )
    ordered = read_tiktok_orders(path)[0].ordered_at
    assert (ordered.day, ordered.month) == (3, 11)


def test_tiktok_line_discount_divided_per_unit(tmp_path):
    path = tiktok_orders_file(
        tmp_path / "t.xlsx",
        [
            tiktok_row(
                "587000000000000003", quantity=2, seller_discount=6000, platform_discount=4000
            )
        ],
    )
    order = read_tiktok_orders(path)[0]
    assert order.items[0].unit_subsidy == 5000
    assert order.review_reasons == ()


def test_tiktok_indivisible_discount_needs_review(tmp_path):
    path = tiktok_orders_file(
        tmp_path / "t.xlsx", [tiktok_row("587000000000000004", quantity=3, seller_discount=10000)]
    )
    order = read_tiktok_orders(path)[0]
    assert order.review_reasons and "không chia hết" in order.review_reasons[0]


def test_lazada_groups_units_by_order_number(tmp_path):
    # One order, three units: two of the same colour, one of another colour.
    path = lazada_orders_file(
        tmp_path / "l.xlsx",
        [
            lazada_row("530000000000001", item_id="1", platform_discount=12500),
            lazada_row("530000000000001", item_id="2", platform_discount=12500),
            lazada_row(
                "530000000000001",
                item_id="3",
                variation="Màu sắc:Màu 02, Đóng Gói:0.8 lít",
                seller_discount=5000,
                platform_discount=2500,
            ),
            lazada_row("530000000000002", item_id="4", name="Người Khác"),
        ],
    )
    orders = read_lazada_orders(path)
    assert [o.platform_order_id for o in orders] == ["530000000000001", "530000000000002"]
    first = orders[0]
    assert [(i.variation_name, i.quantity, i.unit_price, i.unit_subsidy) for i in first.items] == [
        ("Màu sắc:Màu 01, Đóng Gói:0.8 lít", 2, 120000, 12500),
        ("Màu sắc:Màu 02, Đóng Gói:0.8 lít", 1, 120000, 7500),
    ]
    assert first.ordered_at.hour == 9 and first.ordered_at.month == 11
    assert first.customer_name == "Người Mua Thử"
    assert first.default_address == "12 Đường Thử, Phường Ba, Tỉnh Thử, Việt Nam"
    assert orders[1].customer_name == "Người Khác"


def test_lazada_drops_repeated_street_part(tmp_path):
    path = lazada_orders_file(
        tmp_path / "l.xlsx", [lazada_row("530000000000003", street="9 Đường A, 9 Đường A")]
    )
    assert read_lazada_orders(path)[0].default_address == "9 Đường A, Phường Ba, Tỉnh Thử, Việt Nam"


def test_lazada_missing_column_rejects_with_name(tmp_path):
    path = lazada_orders_file(
        tmp_path / "l.xlsx", [lazada_row("530000000000004")], drop=("billingName",)
    )
    with pytest.raises(FileRejected) as err:
        read_lazada_orders(path)
    assert "billingName" in str(err.value)


def test_lazada_bad_date_rejects_whole_file(tmp_path):
    path = lazada_orders_file(
        tmp_path / "l.xlsx",
        [lazada_row("530000000000005"), lazada_row("530000000000006", created="hôm qua")],
    )
    with pytest.raises(FileRejected) as err:
        read_lazada_orders(path)
    assert "createTime" in str(err.value)
