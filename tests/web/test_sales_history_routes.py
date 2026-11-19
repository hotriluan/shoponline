from datetime import datetime
from io import BytesIO
from pathlib import Path
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


def _stored(db, file_id):
    return Path(db.get(GeneratedFile, file_id).stored_path)


def test_a_file_with_an_order_still_unconfirmed_is_kept(db, login):
    setup.report_name(db)
    setup.order(db, "A-1", datetime(2026, 11, 11))
    admin = login("admin")
    _download(admin)
    setup.order(db, "A-2", datetime(2026, 11, 11, 1))
    _download(admin)  # A-1 again, and A-2
    first, second = _file_ids(db)

    admin.post(f"/sales-history/files/{first}/confirm")

    assert not _stored(db, first).exists()
    assert _stored(db, second).exists()  # A-2 is not confirmed yet


def _download(client):
    resp = client.get("/sales-history/file", follow_redirects=False)
    assert resp.status_code == 200, resp.text
    return resp


def _order_ids_in_sheet(resp):
    ws = load_workbook(BytesIO(resp.content))["sheet1"]
    return ws.max_row - 1


def test_blocked_order_is_left_out_of_the_download(db, login):
    setup.report_name(db)
    setup.order(db, "GOOD", datetime(2026, 11, 11, 8))
    setup.order(db, "NO-NAME", datetime(2026, 11, 11, 9), name=None)
    client = login("admin")

    page = client.get("/sales-history").text

    assert 'value="2026-11-13"' in page
    assert "NO-NAME" in page and "Thiếu tên khách" in page
    assert "/customers?batch_id=" in page
    assert "/sales-history/file" in page
    assert "1 đơn bị chặn chưa có trong file này" in page
    ws = load_workbook(BytesIO(_download(client).content))["sheet1"]
    assert [ws.cell(r, 18).value for r in range(2, ws.max_row + 1)] == ["GOOD"]
    assert len(_file_ids(db)) == 1
    assert _count(db, SalesHistoryFileOrder) == 1


def test_blocked_order_goes_into_a_later_file_once_complete(db, login):
    setup.report_name(db)
    setup.order(db, "GOOD", datetime(2026, 11, 11, 8))
    late = setup.order(db, "LATE", datetime(2026, 11, 10, 9), invoice=None)
    admin = login("admin")
    assert f"DO {late.do_number} chưa có Tax Invoice Doc." in admin.get("/sales-history").text
    _download(admin)
    (first,) = _file_ids(db)
    admin.post(f"/sales-history/files/{first}/confirm")

    setup.tax_invoice(db, late.do_number, "HDLATE")
    ws = load_workbook(BytesIO(_download(admin).content))["sheet1"]

    assert [ws.cell(r, 18).value for r in range(2, ws.max_row + 1)] == ["LATE"]


def test_only_blocked_orders_offer_no_download(db, login):
    setup.report_name(db)
    setup.order(db, "NO-NAME", datetime(2026, 11, 11, 9), name=None)
    client = login("admin")

    assert "/sales-history/file" not in client.get("/sales-history").text
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
    assert not _stored(db, file_id).exists()  # every order in it is confirmed
    assert "(đã xóa sau khi xác nhận)" in page
    resp = admin.get(f"/sales-history/files/{file_id}", follow_redirects=True)
    assert "File đã bị xóa sau khi xác nhận đã dán" in resp.text

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
    # The first file holds the same orders: both are spent.
    assert not _stored(db, first).exists() and not _stored(db, second).exists()
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


def test_orders_waiting_for_invoices_offer_a_zrsd003_read(db, login):
    from shoponline.db.models import SapJob
    from shoponline.sapjobs import queue
    from shoponline.sapjobs.queue import SapTarget
    from tests.sap_setup import configure_sap

    setup.report_name(db)
    setup.order(db, "HAS-INVOICE", datetime(2026, 11, 9))
    early = setup.order(db, "EARLY", datetime(2026, 11, 10, 8), invoice=None)
    setup.order(db, "LATE", datetime(2026, 11, 12, 8), invoice=None)
    admin = login("admin")

    page = admin.get("/sales-history").text
    assert f"DO {early.do_number} chưa có Tax Invoice Doc." in page
    assert 'href="#tax-invoice"' in page and "<b>2</b> đơn đã có DO" in page
    assert "Robot chưa được bật" in page and 'href="/sap-reports"' in page
    assert "/sales-history/read-zrsd003" not in page  # no robot configured

    configure_sap(db, SapTarget("QAS", "300"))
    db.expire_all()
    page = admin.get("/sales-history").text
    assert 'action="/sales-history/read-zrsd003"' in page
    assert "từ\n    10/11/2026 đến 13/11/2026" in page

    viewer = login("viewer")
    assert "/sales-history/read-zrsd003" not in viewer.get("/sales-history").text
    viewer.post("/sales-history/read-zrsd003", data={"until": "2026-11-13"})
    assert _count(db, SapJob) == 0

    resp = admin.post("/sales-history/read-zrsd003", data={"until": "2026-11-13"})
    assert "Robot sẽ đọc zrsd003 từ 10/11/2026 đến 13/11/2026" in resp.text
    job = db.scalar(select(SapJob))
    assert job.kind == queue.READ_ZRSD003
    assert queue.payload_of(job) == {"date_from": "2026-11-10", "date_to": "2026-11-13"}
    again = admin.post("/sales-history/read-zrsd003", data={"until": "2026-11-13"}).text
    assert "Đã có việc" in again and _count(db, SapJob) == 1


def test_no_zrsd003_box_when_every_order_has_its_invoice(db, login):
    setup.report_name(db)
    setup.order(db, "A-1", datetime(2026, 11, 11))
    admin = login("admin")
    assert 'id="tax-invoice"' not in admin.get("/sales-history").text
    resp = admin.post("/sales-history/read-zrsd003", data={"until": "2026-11-13"})
    assert "Không có đơn nào chờ Tax Invoice Doc." in resp.text
