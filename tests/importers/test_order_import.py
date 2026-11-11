from datetime import date

import pytest
from sqlalchemy import func, select

from shoponline.db.models import CustomerInfo, EventLog, SalesOrder, SalesOrderItem
from shoponline.domain import states
from shoponline.domain.sku_mapping import upsert_mapping
from shoponline.importers.excel_table import FileRejected
from shoponline.importers.order_import import import_orders, reevaluate_mapping_errors
from shoponline.importers.shopee_orders import read_shopee_orders
from shoponline.importers.tiktok_orders import read_tiktok_orders
from tests.fixtures.build_fixtures import (
    shopee_orders_file,
    shopee_row,
    tiktok_orders_file,
    tiktok_row,
)

D = date(2026, 11, 11)


def _map(
    db, platform="SHOPEE", product="Sơn thử A", variation="Màu 01,1 lít", material="100000001"
):
    upsert_mapping(db, platform, product, variation, material, f"SAP {material}", "test")


def _order(db, order_id, platform="SHOPEE"):
    return db.scalar(
        select(SalesOrder).where(
            SalesOrder.platform == platform, SalesOrder.platform_order_id == order_id
        )
    )


def _count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_import_twice_changes_nothing(db, tmp_path):
    _map(db)
    path = shopee_orders_file(tmp_path / "s.xlsx", [shopee_row("A1"), shopee_row("A2")])
    first = import_orders(db, read_shopee_orders(path), "SHOPEE", D, "test")
    assert (first.new, first.updated, first.unchanged) == (2, 0, 0)
    counts = (_count(db, SalesOrder), _count(db, SalesOrderItem), _count(db, CustomerInfo))
    second = import_orders(db, read_shopee_orders(path), "SHOPEE", D, "test")
    assert (second.new, second.updated, second.unchanged) == (0, 0, 2)
    assert counts == (_count(db, SalesOrder), _count(db, SalesOrderItem), _count(db, CustomerInfo))


def test_second_file_same_day_adds_orders(db, tmp_path):
    _map(db)
    import_orders(
        db,
        read_shopee_orders(shopee_orders_file(tmp_path / "1.xlsx", [shopee_row("A1")])),
        "SHOPEE",
        D,
        "test",
    )
    result = import_orders(
        db,
        read_shopee_orders(
            shopee_orders_file(tmp_path / "2.xlsx", [shopee_row("A1"), shopee_row("A3")])
        ),
        "SHOPEE",
        D,
        "test",
    )
    assert (result.new, result.unchanged) == (1, 1)
    assert _order(db, "A3").batch is _order(db, "A1").batch


def test_linked_order_is_not_moved_back(db, tmp_path):
    _map(db)
    path = shopee_orders_file(tmp_path / "s.xlsx", [shopee_row("A1")])
    import_orders(db, read_shopee_orders(path), "SHOPEE", D, "test")
    order = _order(db, "A1")
    order.so_number = "210000001"
    states.transition(db, order, states.SO_LINKED, "test")
    changed = shopee_orders_file(tmp_path / "s2.xlsx", [shopee_row("A1", quantity=5)])
    result = import_orders(db, read_shopee_orders(changed), "SHOPEE", D, "test")
    assert result.unchanged == 1
    assert order.status == states.SO_LINKED
    assert order.items[0].quantity == 1


def test_changed_open_order_is_updated(db, tmp_path):
    _map(db)
    import_orders(
        db,
        read_shopee_orders(shopee_orders_file(tmp_path / "1.xlsx", [shopee_row("A1")])),
        "SHOPEE",
        D,
        "test",
    )
    result = import_orders(
        db,
        read_shopee_orders(shopee_orders_file(tmp_path / "2.xlsx", [shopee_row("A1", quantity=4)])),
        "SHOPEE",
        D,
        "test",
    )
    assert result.updated == 1
    assert _order(db, "A1").items[0].quantity == 4


def test_missing_mapping_then_fixed(db, tmp_path):
    path = shopee_orders_file(tmp_path / "s.xlsx", [shopee_row("A1", variation="Màu lạ")])
    result = import_orders(db, read_shopee_orders(path), "SHOPEE", D, "test")
    order = _order(db, "A1")
    assert order.status == states.MAPPING_ERROR
    assert "Màu lạ" in order.status_reason
    assert result.problem_orders == [order]

    _map(db, variation="Màu  lạ")  # extra space still matches after normalization
    assert reevaluate_mapping_errors(db, "SHOPEE", "test") == 1
    assert order.status == states.READY
    assert order.items[0].material_number == "100000001"


def test_mapping_of_other_platform_is_not_used(db, tmp_path):
    _map(db, platform="TIKTOK", product="Sơn thử A", variation="Màu 01,1 lít")
    path = shopee_orders_file(tmp_path / "s.xlsx", [shopee_row("A1")])
    import_orders(db, read_shopee_orders(path), "SHOPEE", D, "test")
    assert _order(db, "A1").status == states.MAPPING_ERROR


def test_tiktok_indivisible_discount_goes_to_need_review(db, tmp_path):
    _map(db, platform="TIKTOK", product="Sơn thử A - 1 lít", variation="Màu 01, 1 lít")
    path = tiktok_orders_file(
        tmp_path / "t.xlsx", [tiktok_row("587000000000000009", quantity=3, seller_discount=10000)]
    )
    import_orders(db, read_tiktok_orders(path), "TIKTOK", D, "test")
    order = _order(db, "587000000000000009", "TIKTOK")
    assert order.status == states.NEED_REVIEW
    assert order.platform_order_id == "587000000000000009"


def test_date_far_from_processing_day_rejects_file(db, tmp_path):
    path = shopee_orders_file(
        tmp_path / "s.xlsx", [shopee_row("A1", ordered_at="2026-09-01 10:00")]
    )
    with pytest.raises(FileRejected, match="lệch"):
        import_orders(db, read_shopee_orders(path), "SHOPEE", D, "test")
    assert _count(db, SalesOrder) == 0


def test_customer_default_address_not_overwritten(db, tmp_path):
    _map(db)
    path = shopee_orders_file(tmp_path / "s.xlsx", [shopee_row("A1")])
    import_orders(db, read_shopee_orders(path), "SHOPEE", D, "test")
    customer = db.scalar(select(CustomerInfo).where(CustomerInfo.platform_order_id == "A1"))
    assert customer.address == "Phường Một, Tỉnh Thử, Việt Nam"
    customer.address = "Số 1 đường Thử, Phường Một"
    customer.customer_name = "Người Thử"
    import_orders(db, read_shopee_orders(path), "SHOPEE", D, "test")
    assert customer.address == "Số 1 đường Thử, Phường Một"


def test_events_do_not_contain_customer_data(db, tmp_path):
    _map(db)
    path = shopee_orders_file(tmp_path / "s.xlsx", [shopee_row("A1", district="Phường Riêng")])
    import_orders(db, read_shopee_orders(path), "SHOPEE", D, "test")
    details = " ".join(e.detail or "" for e in db.scalars(select(EventLog)))
    assert "Phường Riêng" not in details
