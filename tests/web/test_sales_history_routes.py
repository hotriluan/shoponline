from datetime import datetime
from io import BytesIO
from urllib.parse import unquote

import pytest
from openpyxl import load_workbook
from sqlalchemy import func, select

from shoponline.db.models import (
    EventLog,
    GeneratedFile,
    SalesHistoryExported,
    SalesHistoryFileOrder,
)
from tests import sales_history_setup as setup

pytestmark = pytest.mark.usefixtures("frozen_today")  # today is 2026-11-13


def _count(db, model):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(model))


def _file_ids(db):
    db.expire_all()
    return list(
        db.scalars(
            select(GeneratedFile.id)
            .where(GeneratedFile.kind == "sales_history")
            .order_by(GeneratedFile.id)
        )
    )


def _download(client):
    resp = client.get("/sales-history/file", follow_redirects=False)
    assert resp.status_code == 200, resp.text
    return resp


def _order_ids_in_sheet(resp):
    ws = load_workbook(BytesIO(resp.content))["sheet1"]
    return ws.max_row - 1


def test_blocked_order_hides_the_download(db, login):
    setup.report_name(db)
    setup.order(db, "GOOD", datetime(2026, 11, 11, 8))
    setup.order(db, "NO-NAME", datetime(2026, 11, 11, 9), name=None)
    client = login("admin")

    page = client.get("/sales-history").text

    assert 'value="2026-11-13"' in page
    assert "NO-NAME" in page and "Thiếu tên khách" in page
    assert "/customers?batch_id=" in page
    assert "/sales-history/file" not in page
    resp = client.get("/sales-history/file", follow_redirects=False)
    assert resp.status_code == 303
    assert _file_ids(db) == []


def test_missing_report_name_links_to_the_names_page(db, login):
    setup.order(db, "A-1", datetime(2026, 11, 11))
    page = login("viewer").get("/sales-history").text
    assert 'href="/report-names?missing=true"' in page
    assert f"Mã {setup.MATERIAL} chưa có tên báo cáo" in page


def test_order_after_the_chosen_day_is_left_for_later(db, login):
    setup.report_name(db)
    setup.order(db, "TODAY", datetime(2026, 11, 13, 10))
    client = login("admin")
    assert "<b>0</b> đơn" in client.get("/sales-history?until=2026-11-12").text
    assert "<b>1</b> đơn" in client.get("/sales-history").text


def test_download_confirm_and_unconfirm(db, login):
    setup.report_name(db)
    first = setup.order(db, "A-1", datetime(2026, 11, 11, 8))
    setup.order(db, "A-2", datetime(2026, 11, 11, 9), lines=((setup.MATERIAL, 1, 1, 0),) * 2)
    admin = login("admin")

    resp = _download(admin)
    assert unquote(resp.headers["content-disposition"]).endswith("SHOP ONLINE LỊCH SỬ 131126.xlsx")
    assert _order_ids_in_sheet(resp) == 3  # A-1 one line, A-2 two lines
    (file_id,) = _file_ids(db)
    assert _count(db, SalesHistoryFileOrder) == 2
    page = admin.get("/sales-history").text
    assert "Chưa xác nhận" in page and "Xác nhận đã dán" in page

    # A late DO arrives before the paste is confirmed: it waits for the next file.
    late = setup.order(db, "LATE", datetime(2026, 10, 31, 23))
    page = admin.post(f"/sales-history/files/{file_id}/confirm").text
    assert "Đã xác nhận 2 đơn, bỏ qua 0 đơn" in page

    resp = _download(admin)
    assert _order_ids_in_sheet(resp) == 1
    second_id = _file_ids(db)[-1]
    assert list(
        db.scalars(
            select(SalesHistoryFileOrder.sales_order_id).where(
                SalesHistoryFileOrder.generated_file_id == second_id
            )
        )
    ) == [late.id]

    # Unconfirming the first file brings its orders back.
    admin.post(f"/sales-history/files/{file_id}/unconfirm")
    db.expire_all()
    exported = set(db.scalars(select(SalesHistoryExported.sales_order_id)))
    assert first.id not in exported
    assert "<b>3</b> đơn" in admin.get("/sales-history").text
    kinds = [
        e.kind for e in db.scalars(select(EventLog).where(EventLog.kind.like("sales_history_%")))
    ]
    assert kinds == ["sales_history_confirmed", "sales_history_unconfirmed"]


def test_an_order_is_confirmed_once_across_files(db, login):
    setup.report_name(db)
    setup.order(db, "A-1", datetime(2026, 11, 11))
    setup.order(db, "A-2", datetime(2026, 11, 11, 1))
    admin = login("admin")
    _download(admin)
    _download(admin)  # forgot to confirm the first one, downloaded again
    first, second = _file_ids(db)

    assert "Đã xác nhận 2 đơn" in admin.post(f"/sales-history/files/{second}/confirm").text
    page = admin.post(f"/sales-history/files/{first}/confirm").text
    assert "Đã xác nhận 0 đơn, bỏ qua 2 đơn" in page
    assert _count(db, SalesHistoryExported) == 2
    db.expire_all()
    assert set(db.scalars(select(SalesHistoryExported.generated_file_id))) == {second}


def test_saved_file_downloads_again_unchanged(db, login):
    setup.report_name(db)
    setup.order(db, "A-1", datetime(2026, 11, 11))
    admin = login("admin")
    original = _download(admin).content
    (file_id,) = _file_ids(db)
    resp = admin.get(f"/sales-history/files/{file_id}")
    assert resp.status_code == 200 and resp.content == original
    assert admin.get("/sales-history/files/999999").status_code == 404


def test_viewer_downloads_but_cannot_confirm(db, login):
    setup.report_name(db)
    setup.order(db, "A-1", datetime(2026, 11, 11))
    viewer = login("viewer")
    _download(viewer)
    (file_id,) = _file_ids(db)
    assert "<button>Xác nhận đã dán</button>" not in viewer.get("/sales-history").text

    resp = viewer.post(
        f"/sales-history/files/{file_id}/confirm",
        headers={"referer": "http://testserver/sales-history"},
        follow_redirects=False,
    )
    assert resp.status_code == 303 and resp.headers["location"].endswith("/sales-history")
    assert _count(db, SalesHistoryExported) == 0
    assert "Tài khoản xem không được thay đổi dữ liệu" in viewer.get("/sales-history").text

    login("admin").post(f"/sales-history/files/{file_id}/confirm")
    viewer.post(f"/sales-history/files/{file_id}/unconfirm")
    assert _count(db, SalesHistoryExported) == 1
