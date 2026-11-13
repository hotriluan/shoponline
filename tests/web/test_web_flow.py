from datetime import date
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.accounting import ledger
from shoponline.config import Settings
from shoponline.db.models import (
    AccountingSentDelivery,
    ImportBatch,
    OrderBatch,
    SalesOrder,
    SkuMapping,
)
from shoponline.domain import states
from shoponline.web.app import create_app
from shoponline.web.auth import set_user
from tests.fixtures.build_fixtures import (
    shopee_orders_file,
    shopee_row,
    zrsd001_file,
    zrsd001_row,
    zrsd004_file,
    zrsd004_row,
)

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def app(db, tmp_path):
    settings = Settings(database_url="unused", secret_key="s" * 40, data_dir=tmp_path / "data")
    set_user(db, "admin", "admin-password", "admin")
    set_user(db, "viewer", "viewer-password", "viewer")

    def factory():
        return Session(
            bind=db.bind, join_transaction_mode="create_savepoint", expire_on_commit=False
        )

    return create_app(settings, session_factory=factory, env={})


def _client(app, username=None, password=None):
    client = TestClient(app)
    if username:
        resp = client.post(
            "/login", data={"username": username, "password": password}, follow_redirects=False
        )
        assert resp.status_code == 303
    return client


def _upload(client, url, path, **data):
    with open(path, "rb") as fh:
        return client.post(
            url, data=data, files={"file": (path.name, fh, XLSX)}, follow_redirects=False
        )


def test_pages_require_login(app):
    client = _client(app)
    resp = client.get("/batches", follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == "/login"
    resp = client.post("/login", data={"username": "admin", "password": "nope"})
    assert "Sai tên đăng nhập" in resp.text


def test_manual_mode_end_to_end(app, db, tmp_path, frozen_today):
    client = _client(app, "admin", "admin-password")
    shopee = shopee_orders_file(
        tmp_path / "Order.toship.xlsx",
        [
            shopee_row("2611110AAAAAAA", quantity=2),
            shopee_row("2611110BBBBBBB", variation="Màu 02,1 lít"),
        ],
    )

    # 1. upload platform file: both orders lack mapping
    resp = _upload(client, "/imports", shopee, platform="SHOPEE", processing_date="2026-11-11")
    assert resp.status_code == 200
    assert "2 đơn mới" in resp.text and "2 đơn cần xử lý" in resp.text

    # 2. mapping screen lists missing products; import one via form, fix both
    page = client.get("/sku-mappings?platform=SHOPEE").text
    assert "Màu 02,1 lít" in page
    for variation, material in (("Màu 01,1 lít", "100000001"), ("Màu 02,1 lít", "100000002")):
        client.post(
            "/sku-mappings",
            data={
                "platform": "SHOPEE",
                "product_name": "Sơn thử A",
                "variation_name": variation,
                "material_number": material,
                "sap_name": f"SAP {material}",
            },
        )
    orders = db.scalars(select(SalesOrder)).all()
    assert {o.status for o in orders} == {states.READY}
    batch = db.scalar(select(OrderBatch))
    assert batch.gi_date == date(2026, 11, 12)

    # 3. order file for sales admin
    resp = client.get(f"/batches/{batch.id}/order-file")
    assert resp.status_code == 200
    ws = load_workbook(BytesIO(resp.content))["SHOPEE"]
    assert ws["C10"].value == "2611110AAAAAAA" and ws["E10"].value == 100000001

    # 4. customer name entered on the web
    client.post(
        "/customers/save",
        data={
            "platform": "SHOPEE",
            "platform_order_id": "2611110AAAAAAA",
            "customer_name": "Người Thử",
            "address": "Phường Một, Tỉnh Thử, Việt Nam",
            "return_to": f"/customers?batch_id={batch.id}",
        },
    )

    # 5. confirm batch, upload zrsd001: one SO correct, one with mistyped PO No
    client.post(f"/batches/{batch.id}/confirm")
    z1 = zrsd001_file(
        tmp_path / "zrsd001.xlsx",
        [
            zrsd001_row("210000001", "2611110AAAAAAA", "100000001", 2, 200000),
            zrsd001_row("210000002", "2611110BBBBBBX", "100000002", 1, 100000),
        ],
    )
    resp = _upload(client, "/sap-reports/zrsd001", z1, batch_id=str(batch.id))
    assert resp.headers["location"] == f"/batches/{batch.id}"
    page = client.get(f"/batches/{batch.id}").text
    assert "2611110BBBBBBX" in page  # unmatched SO listed for manual link
    wrong = db.scalar(select(SalesOrder).where(SalesOrder.platform_order_id == "2611110BBBBBBB"))
    client.post(f"/batches/{batch.id}/link", data={"so_number": "210000002", "order_id": wrong.id})
    db.refresh(wrong)
    assert wrong.status == states.SO_LINKED

    # 6. zrsd004 uploaded by hand -> preview with a warning for the order without a name
    z4 = zrsd004_file(
        tmp_path / "zrsd004.xlsx",
        [
            zrsd004_row("1900000001", "210000001", "100000001", 2),
            zrsd004_row("1900000002", "210000002", "100000002"),
        ],
    )
    resp = _upload(client, "/sap-reports/zrsd004", z4)
    assert "SO 210000002" in resp.text and "tên khách" in resp.text
    assert "/accounting" in resp.text and "accounting-file" not in resp.text
    db.expire_all()
    assert {o.status for o in db.scalars(select(SalesOrder))} == {states.DELIVERED}
    record = db.scalar(select(ImportBatch).where(ImportBatch.kind == "zrsd004"))

    # 7. accounting run: the earlier upload is offered, then draft, finalize and download
    ledger.set_cutoff(db, date(2000, 1, 1), "test")  # the migration set it to the day it ran
    resp = client.post("/accounting/runs", follow_redirects=False)
    run_url = resp.headers["location"]
    assert run_url.startswith("/accounting/runs/")
    assert "zrsd004.xlsx" in client.get(run_url).text
    client.post(f"{run_url}/attach", data={"import_batch_id": record.id})
    page = client.get(run_url).text
    assert "Xong, có DO" in page and "Chưa có việc" in page  # 12/11 covered, 13/11 not read
    fingerprint = page.split('name="fingerprint" value="')[1].split('"')[0]

    draft = client.get(f"{run_url}/draft")
    assert "NH%C3%81P%20SHOP%20ONLINE%20121126.xlsx" in draft.headers["content-disposition"]
    ws = load_workbook(BytesIO(draft.content)).active
    assert [ws.cell(2, c).value for c in (5, 6, 7)] == [
        "2611110AAAAAAA",
        "Người Thử",
        "Phường Một, Tỉnh Thử, Việt Nam",
    ]
    assert ws.cell(3, 5).value == "2611110BBBBBBB"  # manual link wins over mistyped PO No
    assert not db.scalars(select(AccountingSentDelivery)).all()  # a draft records nothing

    refused = client.post(f"{run_url}/finalize", data={"fingerprint": fingerprint}).text
    assert "Còn chưa có dữ liệu" in refused and "SHOPEE 13/11/2026" in refused
    assert not db.scalars(select(AccountingSentDelivery)).all()

    client.post(f"{run_url}/finalize", data={"fingerprint": fingerprint, "allow_partial": "1"})
    db.expire_all()
    assert {d.delivery for d in db.scalars(select(AccountingSentDelivery))} == {
        "1900000001",
        "1900000002",
    }
    final = client.get(f"{run_url}/file")
    assert final.status_code == 200
    ws = load_workbook(BytesIO(final.content)).active
    assert ws.cell(3, 5).value == "2611110BBBBBBB"
    assert client.get(f"{run_url}/file").content == final.content

    # 8. a stored file that is gone gives a clear 404, not a server error
    for stored in app.state.settings.export_dir.glob("*.xlsx"):
        stored.unlink()
    resp = client.get(f"{run_url}/file")
    assert resp.status_code == 404 and "không còn trên máy chủ" in resp.text


def test_viewer_cannot_change_data(app, db, tmp_path):
    client = _client(app, "viewer", "viewer-password")
    shopee = shopee_orders_file(tmp_path / "s.xlsx", [shopee_row("A1")])
    resp = _upload(client, "/imports", shopee, platform="SHOPEE", processing_date="2026-11-11")
    assert resp.status_code == 303
    assert db.scalar(select(SalesOrder)) is None
    assert client.get("/batches").status_code == 200


def test_rejects_non_xlsx_and_missing_columns(app, db, tmp_path):
    client = _client(app, "admin", "admin-password")
    bad = tmp_path / "orders.csv"
    bad.write_text("a,b")
    resp = _upload(client, "/imports", bad, platform="SHOPEE", processing_date="2026-11-11")
    assert "Chỉ nhận file .xlsx" in resp.text
    missing = shopee_orders_file(tmp_path / "m.xlsx", [shopee_row("A1")], drop=("Giá gốc",))
    resp = _upload(client, "/imports", missing, platform="SHOPEE", processing_date="2026-11-11")
    assert "Giá gốc" in resp.text
    assert db.scalar(select(SalesOrder)) is None


def test_cancel_order(app, db, tmp_path):
    client = _client(app, "admin", "admin-password")
    shopee = shopee_orders_file(tmp_path / "s.xlsx", [shopee_row("A1")])
    _upload(client, "/imports", shopee, platform="SHOPEE", processing_date="2026-11-11")
    order = db.scalar(select(SalesOrder))
    client.post(f"/orders/{order.id}/cancel", data={"reason": "khách hủy"})
    db.refresh(order)
    assert order.status == states.CANCELLED
    assert "khách hủy" in client.get(f"/orders/{order.id}").text


def _three_unmapped_orders(client, tmp_path):
    shopee = shopee_orders_file(
        tmp_path / "s.xlsx",
        [
            shopee_row("A1", variation="Màu 01,1 lít"),
            shopee_row("A2", variation="Màu 02,1 lít"),
            shopee_row("A3", variation="Màu 03,1 lít"),
        ],
    )
    _upload(client, "/imports", shopee, platform="SHOPEE", processing_date="2026-11-11")


def _bulk(client, rows):
    data = {
        "platform": "SHOPEE",
        "product_name": [],
        "variation_name": [],
        "material_number": [],
        "sap_name": [],
    }
    for variation, material, sap_name in rows:
        data["product_name"].append("Sơn thử A")
        data["variation_name"].append(variation)
        data["material_number"].append(material)
        data["sap_name"].append(sap_name)
    return client.post("/sku-mappings/bulk", data=data, follow_redirects=False)


def test_bulk_save_keeps_every_filled_row(app, db, tmp_path):
    client = _client(app, "admin", "admin-password")
    _three_unmapped_orders(client, tmp_path)
    resp = _bulk(
        client,
        [
            ("Màu 01,1 lít", "100000001", "SAP 1"),
            ("Màu 02,1 lít", "100000002", "SAP 2"),
            ("Màu 03,1 lít", "", ""),  # left blank: skipped, still unmapped
        ],
    )
    assert resp.status_code == 303
    mapped = set(db.scalars(select(SkuMapping.material_number)))
    assert mapped == {"100000001", "100000002"}
    statuses = {o.platform_order_id: o.status for o in db.scalars(select(SalesOrder))}
    assert statuses == {"A1": states.READY, "A2": states.READY, "A3": states.MAPPING_ERROR}


def test_bulk_save_rejects_all_and_keeps_typed_values(app, db, tmp_path):
    client = _client(app, "admin", "admin-password")
    _three_unmapped_orders(client, tmp_path)
    resp = _bulk(
        client,
        [
            ("Màu 01,1 lít", "100000001", "SAP 1"),
            ("Màu 02,1 lít", "ABC", "SAP 2"),
            ("Màu 03,1 lít", "100000003", "SAP 3"),
        ],
    )
    assert resp.status_code == 200
    assert db.scalar(select(SkuMapping)) is None
    for typed in ("100000001", "ABC", "SAP 3", "Mã SAP phải là chữ số"):
        assert typed in resp.text


def test_unmapped_excel_round_trip(app, db, tmp_path):
    client = _client(app, "admin", "admin-password")
    _three_unmapped_orders(client, tmp_path)
    resp = client.get("/sku-mappings/unmapped.xlsx?platform=SHOPEE")
    assert resp.status_code == 200
    workbook = load_workbook(BytesIO(resp.content))
    sheet = workbook.active
    assert [c.value for c in sheet[1]] == ["Tên sản phẩm", "Tên phân loại", "Mã SAP", "Tên SAP"]
    assert sheet.max_row == 4
    sheet["C2"], sheet["D2"] = "100000001", "SAP 1"
    sheet["C3"], sheet["D3"] = "100000002", "SAP 2"
    filled = tmp_path / "filled.xlsx"
    workbook.save(filled)
    resp = _upload(client, "/sku-mappings/import", filled, platform="SHOPEE")
    assert resp.status_code == 303
    page = client.get("/sku-mappings?platform=SHOPEE").text
    assert "Đã lưu 2 ánh xạ" in page and "1 dòng để trống bỏ qua" in page
    statuses = {o.platform_order_id: o.status for o in db.scalars(select(SalesOrder))}
    assert sorted(statuses.values()) == sorted([states.READY, states.READY, states.MAPPING_ERROR])


AUTOSAVE = {"X-Autosave": "1"}


def test_autosave_answers_json_and_saves_one_row(app, db, tmp_path):
    client = _client(app, "admin", "admin-password")
    _three_unmapped_orders(client, tmp_path)
    page = client.get("/sku-mappings?platform=SHOPEE").text
    assert 'data-autosave="/sku-mappings"' in page

    row = {"platform": "SHOPEE", "product_name": "Sơn thử A", "variation_name": "Màu 01,1 lít"}
    resp = client.post(
        "/sku-mappings", data={**row, "material_number": "X1", "sap_name": "S"}, headers=AUTOSAVE
    )
    assert resp.status_code == 422 and "chữ số" in resp.json()["message"]
    resp = client.post(
        "/sku-mappings",
        data={**row, "material_number": "100000001", "sap_name": "S"},
        headers=AUTOSAVE,
    )
    assert resp.json() == {"ok": True, "message": "Đã lưu, 1 đơn sẵn sàng"}

    resp = client.post(
        "/customers/save",
        data={"platform": "SHOPEE", "platform_order_id": "A1", "customer_name": "Người Thử"},
        headers=AUTOSAVE,
    )
    assert resp.json()["ok"] is True
    assert "Người Thử" in client.get("/customers?platform=SHOPEE").text

    batch = db.scalar(select(OrderBatch))
    resp = client.post(
        f"/batches/{batch.id}/gi-date", data={"gi_date": "2026-11-01"}, headers=AUTOSAVE
    )
    assert resp.status_code == 422 and resp.json()["ok"] is False
    resp = client.post(
        f"/batches/{batch.id}/gi-date", data={"gi_date": "2026-11-13"}, headers=AUTOSAVE
    )
    assert resp.json()["ok"] is True
    db.refresh(batch)
    assert batch.gi_date == date(2026, 11, 13)


def test_autosave_refused_for_viewer_and_expired_login(app, db, tmp_path):
    form = {"platform": "SHOPEE", "platform_order_id": "A1", "customer_name": "X"}
    resp = _client(app).post("/customers/save", data=form, headers=AUTOSAVE)
    assert resp.status_code == 401 and "đăng nhập" in resp.json()["message"]
    viewer = _client(app, "viewer", "viewer-password")
    resp = viewer.post("/customers/save", data=form, headers=AUTOSAVE)
    assert resp.status_code == 403 and resp.json()["ok"] is False
    assert 'data-autosave="/customers/save"' not in viewer.get("/customers?platform=SHOPEE").text
