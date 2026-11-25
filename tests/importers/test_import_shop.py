from datetime import date

import pytest
from sqlalchemy import select

from shoponline.db.models import EventLog, ImportBatch, SalesOrder, Shop
from shoponline.domain import shops
from shoponline.domain.sku_mapping import upsert_mapping
from shoponline.importers.order_import import import_orders
from shoponline.importers.shopee_orders import read_shopee_orders
from tests.fixtures.build_fixtures import shopee_orders_file, shopee_row

D = date(2026, 11, 11)


def _file(tmp_path, *ids):
    return shopee_orders_file(tmp_path / "s.xlsx", [shopee_row(i) for i in ids])


def _shop_of(db, order_id):
    return db.scalar(select(SalesOrder.shop_code).where(SalesOrder.platform_order_id == order_id))


@pytest.fixture(autouse=True)
def mapped(db):
    upsert_mapping(db, "SHOPEE", "Sơn thử A", "Màu 01,1 lít", "100000001", "SAP", "test")


def test_new_orders_get_the_chosen_shop_and_the_batch_remembers_it(db, tmp_path):
    db.get(Shop, "SHOPEE_PGT").active = True
    record = ImportBatch(
        kind="shopee_orders", file_name="s", sha256="0" * 64, stored_path="s", imported_by="t"
    )
    db.add(record)
    db.flush()

    result = import_orders(
        db, read_shopee_orders(_file(tmp_path, "A1")), "SHOPEE", D, "t", record, "SHOPEE_PGT"
    )

    assert _shop_of(db, "A1") == "SHOPEE_PGT"
    assert record.shop_code == "SHOPEE_PGT" and result.shop_code == "SHOPEE_PGT"
    assert result.in_other_shop == []


def test_without_a_choice_the_platforms_default_shop_is_used(db, tmp_path):
    import_orders(db, read_shopee_orders(_file(tmp_path, "A1")), "SHOPEE", D, "t")

    assert _shop_of(db, "A1") == "SHOPEE_BD"


def test_an_order_already_in_another_shop_keeps_it_and_is_listed(db, tmp_path):
    db.get(Shop, "SHOPEE_PGT").active = True
    path = _file(tmp_path, "A1", "A2")
    import_orders(db, read_shopee_orders(path), "SHOPEE", D, "t", None, "SHOPEE_BD")

    result = import_orders(db, read_shopee_orders(path), "SHOPEE", D, "t", None, "SHOPEE_PGT")

    assert _shop_of(db, "A1") == "SHOPEE_BD"
    assert sorted(o.platform_order_id for o in result.in_other_shop) == ["A1", "A2"]
    event = db.scalars(
        select(EventLog).where(EventLog.kind == "file_imported").order_by(EventLog.id.desc())
    ).first()
    assert '"in_other_shop": 2' in event.detail


@pytest.mark.parametrize(
    ("shop_code", "message"),
    [
        (None, None),
        ("", None),
        ("TIKTOK_BD", "không thuộc sàn SHOPEE"),
        ("SHOPEE_DN", "đang tắt"),
        ("NOPE", "Chưa chọn shop"),
    ],
)
def test_require_choice_refuses_a_foreign_inactive_or_unknown_shop(db, shop_code, message):
    if message is None:
        with pytest.raises(shops.ShopRefused, match="Chưa chọn shop"):
            shops.require_choice(db, "SHOPEE", shop_code)
        return
    with pytest.raises(shops.ShopRefused, match=message):
        shops.require_choice(db, "SHOPEE", shop_code)


def test_default_shop_is_the_only_active_one_else_the_latest_upload_else_the_first(db):
    assert shops.default_shop_code(db, "SHOPEE") == "SHOPEE_BD"
    db.get(Shop, "SHOPEE_PGT").active = True
    db.flush()
    assert shops.default_shop_code(db, "SHOPEE") == "SHOPEE_BD"
    db.add(
        ImportBatch(
            kind="shopee_orders",
            platform="SHOPEE",
            file_name="s",
            sha256="0" * 64,
            stored_path="s",
            imported_by="t",
            shop_code="SHOPEE_PGT",
        )
    )
    db.flush()
    assert shops.default_shop_code(db, "SHOPEE") == "SHOPEE_PGT"
    db.get(Shop, "SHOPEE_PGT").active = False
    db.flush()
    assert shops.default_shop_code(db, "SHOPEE") == "SHOPEE_BD"
