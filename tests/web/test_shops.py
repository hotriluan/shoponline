from datetime import datetime

from sqlalchemy import select

from shoponline.db.models import EventLog, SalesOrder, Shop
from tests import sales_history_setup as setup

WHEN = datetime(2026, 11, 12, 9)


def _shop(db, code):
    db.expire_all()
    return db.get(Shop, code)


def test_viewer_sees_the_catalog_without_forms(db, login):
    page = login("viewer").get("/shops").text

    assert "Shopee Bình Dương" in page and "Lazada Mall" in page
    assert 'action="/shops"' not in page


def test_admin_turns_a_shop_on_and_renames_its_division(db, login):
    admin = login("admin")

    admin.post("/shops/SHOPEE_PGT/update", data={"division": "Shopee PGT 2", "active": "on"})

    shop = _shop(db, "SHOPEE_PGT")
    assert shop.active and shop.division == "Shopee PGT 2"
    assert db.scalars(select(EventLog).where(EventLog.kind == "shop_updated")).all()


def test_the_last_active_shop_of_a_platform_cannot_be_turned_off(db, login):
    page = login("admin").post("/shops/TIKTOK_BD/update", data={"division": "tiktok Bình Dương"})

    assert "ít nhất một shop đang bán" in page.text
    assert _shop(db, "TIKTOK_BD").active


def test_a_division_already_used_is_refused(db, login):
    page = login("admin").post(
        "/shops/SHOPEE_PGT/update", data={"division": "Shopee Bình Dương", "active": "on"}
    )

    assert "đã là của shop SHOPEE_BD" in page.text
    assert _shop(db, "SHOPEE_PGT").division == "Shopee PGT"


def test_admin_adds_a_shop_and_deletes_it_while_it_has_no_orders(db, login):
    admin = login("admin")

    admin.post("/shops", data={"code": "tiktok_hn", "platform": "TIKTOK", "division": "tiktok HN"})
    assert _shop(db, "TIKTOK_HN").sort_order == 2
    admin.post("/shops/TIKTOK_HN/delete")
    assert _shop(db, "TIKTOK_HN") is None


def test_a_shop_with_orders_cannot_be_deleted(db, login):
    setup.order(db, "A-1", WHEN)
    db.commit()

    page = login("admin").post("/shops/SHOPEE_BD/delete")

    assert "không xóa được" in page.text
    assert _shop(db, "SHOPEE_BD") is not None


def test_viewer_cannot_change_a_shop(db, login):
    login("viewer").post("/shops/SHOPEE_PGT/update", data={"division": "X", "active": "on"})

    assert not _shop(db, "SHOPEE_PGT").active


def test_the_import_form_lists_active_shops_with_the_default_per_platform(db, login):
    db.get(Shop, "SHOPEE_PGT").active = True
    db.commit()

    page = login("admin").get("/imports").text

    assert 'name="shop_code"' in page
    assert 'data-platform="SHOPEE">Shopee PGT<' in page
    assert "Shopee Da Nang" not in page  # still off


def test_an_upload_for_a_shop_of_another_platform_is_refused(db, login, tmp_path):
    from tests.fixtures.build_fixtures import shopee_orders_file, shopee_row

    path = shopee_orders_file(tmp_path / "s.xlsx", [shopee_row("A1")])
    with open(path, "rb") as handle:
        page = login("admin").post(
            "/imports",
            data={"platform": "SHOPEE", "processing_date": "2026-11-11", "shop_code": "TIKTOK_BD"},
            files={"file": ("s.xlsx", handle, "application/octet-stream")},
        )

    assert "không thuộc sàn SHOPEE" in page.text
    assert db.scalar(select(SalesOrder.id)) is None


def test_admin_changes_the_shop_of_an_order_and_it_is_logged(db, login):
    order = setup.order(db, "A-1", WHEN)
    db.get(Shop, "SHOPEE_PGT").active = True
    db.commit()

    login("admin").post(f"/orders/{order.id}/shop", data={"shop_code": "SHOPEE_PGT"})

    db.expire_all()
    assert db.get(SalesOrder, order.id).shop_code == "SHOPEE_PGT"
    event = db.scalars(select(EventLog).where(EventLog.kind == "order_shop_changed")).one()
    assert "SHOPEE_BD" in event.detail and "SHOPEE_PGT" in event.detail
    page = login("viewer").get(f"/orders/{order.id}").text
    assert "Shopee PGT" in page and "Lưu shop" not in page
