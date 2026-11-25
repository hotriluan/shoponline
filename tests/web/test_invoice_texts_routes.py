from sqlalchemy import select

from shoponline.db.models import EventLog, InvoiceItemText, SkuMapping


def _mapping(db, material, product="Propan V-09"):
    db.add(
        SkuMapping(
            platform="TIKTOK",
            product_key=f"{product}|{material}".lower(),
            variation_key="v",
            product_name=product,
            variation_name="v",
            material_number=material,
            sap_name=f"SAP {material}",
            updated_by="t",
        )
    )
    db.flush()


def _saved(db):
    db.expire_all()
    return {
        r.material_number: (r.invoice_name, r.invoice_unit, r.stock_unit, r.source)
        for r in db.scalars(select(InvoiceItemText))
    }


def _form(*rows):
    data = {"material_number": [], "invoice_name": [], "invoice_unit": [], "stock_unit": []}
    for material, name, unit, stock in rows:
        data["material_number"].append(material)
        data["invoice_name"].append(name)
        data["invoice_unit"].append(unit)
        data["stock_unit"].append(stock)
    return data


def test_viewer_sees_the_list_with_unsaved_first_but_cannot_edit(db, login):
    _mapping(db, "100000001")
    _mapping(db, "100000002")
    db.add(
        InvoiceItemText(
            material_number="100000001",
            invoice_name="SƠN A",
            invoice_unit="LON",
            source="00008038",
            updated_by="t",
        )
    )
    db.flush()

    page = login("viewer").get("/invoice-texts").text

    assert page.index("100000002") < page.index("100000001")
    assert "<button>Lưu tất cả</button>" not in page and " readonly" in page
    assert "HĐ 00008038" in page
    only_missing = login("viewer").get("/invoice-texts?missing=true").text
    assert "100000002" in only_missing and "100000001" not in only_missing


def test_admin_saves_as_manual_with_the_default_stock_unit(db, login):
    _mapping(db, "100000001")
    _mapping(db, "100000002")

    resp = login("admin").post(
        "/invoice-texts",
        data=_form(("100000001", "SƠN V-09", "LON 0.8 LT", ""), ("100000002", "", "", "PC")),
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert _saved(db) == {"100000001": ("SƠN V-09", "LON 0.8 LT", "PC", "manual")}
    event = db.scalar(select(EventLog).where(EventLog.kind == "invoice_texts_saved"))
    assert "100000001" in event.detail


def test_a_half_filled_row_rejects_the_whole_save_and_keeps_typed_values(db, login):
    _mapping(db, "100000001")
    _mapping(db, "100000002")

    resp = login("admin").post(
        "/invoice-texts",
        data=_form(("100000001", "SƠN V-09", "LON", "PC"), ("100000002", "SƠN GÕ DỞ", "", "PC")),
    )

    assert resp.status_code == 200
    assert "chưa lưu dòng nào" in resp.text and "Cần đủ tên hàng và đơn vị tính" in resp.text
    assert 'value="SƠN GÕ DỞ"' in resp.text and 'value="SƠN V-09"' in resp.text
    assert _saved(db) == {}


def test_a_saved_row_cannot_be_blanked_and_an_unknown_material_is_refused(db, login):
    _mapping(db, "100000001")
    db.add(
        InvoiceItemText(
            material_number="100000001",
            invoice_name="SƠN A",
            invoice_unit="LON",
            source="manual",
            updated_by="t",
        )
    )
    db.flush()
    client = login("admin")

    blank = client.post("/invoice-texts", data=_form(("100000001", "", "", "PC")))
    assert "Không thể xóa trống" in blank.text
    unknown = client.post("/invoice-texts", data=_form(("999999999", "SƠN", "LON", "PC")))
    assert "Mã vật tư không có trong ánh xạ SAP: 999999999" in unknown.text
    assert _saved(db)["100000001"][:2] == ("SƠN A", "LON")


def test_overlong_text_is_refused(db, login):
    _mapping(db, "100000001")
    resp = login("admin").post("/invoice-texts", data=_form(("100000001", "S" * 201, "LON", "PC")))
    assert "Tối đa 200 ký tự" in resp.text and _saved(db) == {}


def test_viewer_cannot_save(db, login):
    _mapping(db, "100000001")
    resp = login("viewer").post(
        "/invoice-texts",
        data=_form(("100000001", "SƠN", "LON", "PC")),
        headers={"referer": "http://testserver/invoice-texts"},
        follow_redirects=False,
    )
    assert resp.status_code == 303 and _saved(db) == {}
