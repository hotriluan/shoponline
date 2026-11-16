from sqlalchemy import select

from shoponline.db.models import EventLog, ReportItemName, SkuMapping

PRODUCT = "Propan - ULTRAN VERNIS - V-09 - Sơn Dầu Bóng Màu - 0.8 lít"


def _mapping(db, material, product=PRODUCT, variation="Cánh gián - 2004, 0.8 lít"):
    db.add(
        SkuMapping(
            platform="TIKTOK",
            product_key=f"{product}|{material}".lower(),
            variation_key=variation.lower(),
            product_name=product,
            variation_name=variation,
            material_number=material,
            sap_name=f"SAP {material}",
            updated_by="t",
        )
    )
    db.flush()


def _saved(db):
    db.expire_all()
    return {
        r.material_number: (r.item_name, r.size, r.variation)
        for r in db.scalars(select(ReportItemName))
    }


def _form(*rows):
    data = {"material_number": [], "item_name": [], "size": [], "variation": []}
    for material, item, size, variation in rows:
        data["material_number"].append(material)
        data["item_name"].append(item)
        data["size"].append(size)
        data["variation"].append(variation)
    return data


def test_viewer_sees_suggestions_and_unsaved_first(db, login):
    _mapping(db, "100000001")
    _mapping(db, "100000002", product="Sơn khác", variation="Trắng, 1 lít")
    db.add(
        ReportItemName(
            material_number="100000001", item_name="X", size="1", variation="V", updated_by="t"
        )
    )
    db.flush()

    page = login("viewer").get("/report-names").text

    assert page.index("100000002") < page.index("100000001")
    assert "gợi ý, chưa lưu" in page and 'value="Màu sắc:Trắng"' in page
    assert "<button>Lưu tất cả</button>" not in page and " readonly" in page
    missing = login("viewer").get("/report-names?missing=true").text
    assert "100000002" in missing and "100000001" not in missing


def test_admin_saves_and_unchanged_rows_are_not_touched(db, login):
    _mapping(db, "100000001")
    _mapping(db, "100000002")
    client = login("admin")

    resp = client.post(
        "/report-names",
        data=_form(
            ("100000001", "Propan - A", "0.8 lít", "Màu sắc:2004 Cánh gián"),
            ("100000002", "", "", ""),  # left empty: skipped
        ),
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert _saved(db) == {"100000001": ("Propan - A", "0.8 lít", "Màu sắc:2004 Cánh gián")}
    first = db.get(ReportItemName, "100000001")
    stamp = first.updated_at

    client.post(
        "/report-names",
        data=_form(("100000001", "Propan - A", "0.8 lít", "Màu sắc:2004 Cánh gián")),
    )
    db.expire_all()
    assert db.get(ReportItemName, "100000001").updated_at == stamp
    events = db.scalars(select(EventLog).where(EventLog.kind == "report_names_saved")).all()
    assert [e.detail for e in events] == ['{"changed": 1}']


def test_a_partly_filled_row_rejects_the_whole_save(db, login):
    _mapping(db, "100000001")
    _mapping(db, "100000002")

    resp = login("admin").post(
        "/report-names",
        data=_form(
            ("100000001", "Propan - A", "0.8 lít", "Màu sắc:Đỏ"),
            ("100000002", "Propan - B gõ dở", "", "Màu sắc:Xanh"),
        ),
    )

    assert resp.status_code == 200
    assert "chưa lưu dòng nào" in resp.text
    assert "Cần đủ itemName, kích cỡ và variation" in resp.text
    assert 'value="Propan - B gõ dở"' in resp.text and 'value="Màu sắc:Đỏ"' in resp.text
    assert _saved(db) == {}


def test_viewer_cannot_save(db, login):
    _mapping(db, "100000001")

    resp = login("viewer").post(
        "/report-names",
        data=_form(("100000001", "Propan - A", "0.8 lít", "Màu sắc:Đỏ")),
        headers={"referer": "http://testserver/report-names"},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/report-names")
    assert _saved(db) == {}


def test_unknown_material_is_rejected(db, login):
    _mapping(db, "100000001")
    resp = login("admin").post(
        "/report-names", data=_form(("999999999", "Propan - A", "0.8 lít", "Màu sắc:Đỏ"))
    )
    assert "Mã vật tư không có trong ánh xạ SAP" in resp.text
    assert _saved(db) == {}
