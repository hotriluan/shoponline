from datetime import date
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.config import Settings
from shoponline.db.models import OrderBatch, SalesOrder
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

    return create_app(settings, session_factory=factory)


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


def test_manual_mode_end_to_end(app, db, tmp_path):
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

    # 6. zrsd004 -> preview with warning for the order without name -> accounting file
    z4 = zrsd004_file(
        tmp_path / "zrsd004.xlsx",
        [
            zrsd004_row("1900000001", "210000001", "100000001", 2),
            zrsd004_row("1900000002", "210000002", "100000002"),
        ],
    )
    resp = _upload(client, "/sap-reports/zrsd004", z4)
    assert "SHOP ONLINE 121126.xlsx" in resp.text
    assert "SO 210000002" in resp.text and "tên khách" in resp.text
    record_id = resp.text.split("/sap-reports/zrsd004/")[1].split("/")[0]
    resp = client.get(f"/sap-reports/zrsd004/{record_id}/accounting-file")
    ws = load_workbook(BytesIO(resp.content)).active
    assert [ws.cell(2, c).value for c in (5, 6, 7)] == [
        "2611110AAAAAAA",
        "Người Thử",
        "Phường Một, Tỉnh Thử, Việt Nam",
    ]
    assert ws.cell(3, 5).value == "2611110BBBBBBB"  # manual link wins over mistyped PO No
    db.expire_all()
    assert {o.status for o in db.scalars(select(SalesOrder))} == {states.DELIVERED}


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
