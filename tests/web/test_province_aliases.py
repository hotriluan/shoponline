from sqlalchemy import select

from shoponline.db.models import CustomerInfo, ProvinceAlias
from tests import sales_history_setup as setup


def _line(db, city="Huyện Châu Thành"):
    from datetime import date

    from shoponline.db.models import HistorySaleLine, ImportBatch

    batch = ImportBatch(
        kind="history_sales", file_name="h", sha256="x", stored_path="p", imported_by="t"
    )
    db.add(batch)
    db.flush()
    db.add(
        HistorySaleLine(
            period=date(2025, 1, 1), shop_code="SHOPEE_BD", city_raw=city, quantity=1,
            customer_paid=1, order_key="o", line_key=f"k{city}", source_row=2,
            import_batch_id=batch.id,
        )
    )  # fmt: skip
    db.commit()


def test_the_page_lists_unresolved_names_with_their_row_counts(db, login):
    _line(db)
    _line(db, "Kiên Giang")

    page = login("viewer").get("/province-aliases").text

    assert "Huyện Châu Thành" in page and "Kiên Giang" not in page
    assert 'action="/province-aliases"' not in page


def test_admin_assigns_a_province_and_the_name_leaves_the_list(db, login):
    _line(db)
    admin = login("admin")

    admin.post("/province-aliases", data={"raw": "Huyện Châu Thành", "province": "Lâm Đồng"})

    db.expire_all()
    assert db.get(ProvinceAlias, "huyen chau thanh").province == "Lâm Đồng"
    assert "Huyện Châu Thành" not in admin.get("/province-aliases").text.split("Đã quy đổi tay")[0]


def test_a_province_outside_the_34_is_refused(db, login):
    page = login("admin").post(
        "/province-aliases", data={"raw": "Châu Thành", "province": "Kiên Giang"}
    )

    assert "Chọn một trong 34 tỉnh" in page.text
    assert db.get(ProvinceAlias, "chau thanh") is None


def test_viewer_cannot_save(db, login):
    resp = login("viewer").post(
        "/province-aliases",
        data={"raw": "Châu Thành", "province": "Lâm Đồng"},
        follow_redirects=False,
    )

    assert resp.status_code in (303, 403)
    assert db.get(ProvinceAlias, "chau thanh") is None


def test_addresses_without_a_province_show_their_last_part(db, login):
    db.add(
        CustomerInfo(
            platform="SHOPEE", platform_order_id="Z1", address="1 Lê Lợi, Quận 1, Hà Đông, Việt Nam"
        )
    )
    db.commit()

    page = login("viewer").get("/province-aliases").text

    assert "Hà Đông" in page


def test_a_customer_address_gets_its_province_when_saved(db, login):
    setup.order(db, "P-1", __import__("datetime").datetime(2026, 11, 12, 9))
    db.commit()

    login("admin").post(
        "/customers/save",
        data={
            "platform": "SHOPEE",
            "platform_order_id": "P-1",
            "customer_name": "A",
            "address": setup.ADDRESS,
        },
    )

    info = db.scalar(select(CustomerInfo).where(CustomerInfo.platform_order_id == "P-1"))
    db.refresh(info)
    assert info.province == "Hồ Chí Minh"


def test_editing_only_the_name_keeps_the_address_source(db, login):
    setup.order(db, "P-2", __import__("datetime").datetime(2026, 11, 12, 9))
    info = db.scalar(select(CustomerInfo).where(CustomerInfo.platform_order_id == "P-2"))
    if info is None:
        info = CustomerInfo(platform="SHOPEE", platform_order_id="P-2")
        db.add(info)
    info.customer_name, info.address, info.address_source = "A", setup.ADDRESS, "label"
    db.commit()
    admin = login("admin")
    form = {"platform": "SHOPEE", "platform_order_id": "P-2", "address": setup.ADDRESS}

    admin.post("/customers/save", data={**form, "customer_name": "Tên mới"})
    db.refresh(info)
    assert (info.customer_name, info.address_source) == ("Tên mới", "label")

    admin.post("/customers/save", data={**form, "customer_name": "Tên mới", "address": "Số 9"})
    db.refresh(info)
    assert (info.address, info.address_source) == ("Số 9", "admin")

    admin.post("/customers/save", data={**form, "customer_name": "Tên mới", "address": ""})
    db.refresh(info)
    assert (info.address, info.address_source) == (None, None)
