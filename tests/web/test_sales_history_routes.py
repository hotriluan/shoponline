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
    PlatformSettlement,
    SalesHistoryExported,
    SalesHistoryFileOrder,
)
from tests import sales_history_setup as setup
from tests.fixtures.build_fixtures import (
    lazada_settlement_file,
    shopee_settlement_file,
    shopee_settlement_row,
)

pytestmark = pytest.mark.usefixtures("frozen_today")  # today is 2026-11-13
PAGE = "/sales-history?month=2026-11"


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
    resp = client.get("/sales-history/file?month=2026-11", follow_redirects=False)
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

    page = client.get(PAGE).text

    assert 'value="2026-11"' in page
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
    assert f"DO {late.do_number} chưa có Tax Invoice Doc." in admin.get(PAGE).text
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

    assert "/sales-history/file" not in client.get(PAGE).text
    resp = client.get("/sales-history/file?month=2026-11", follow_redirects=False)
    assert resp.status_code == 303
    assert _file_ids(db) == []


def test_missing_report_name_links_to_the_names_page(db, login):
    setup.order(db, "A-1", datetime(2026, 11, 11))
    page = login("viewer").get(PAGE).text
    assert 'href="/report-names?missing=true"' in page
    assert f"Mã {setup.MATERIAL} chưa có tên báo cáo" in page


def test_an_order_after_the_chosen_month_is_left_for_later(db, login):
    setup.report_name(db)
    setup.order(db, "OCT-31", datetime(2026, 10, 31, 23, 30))
    setup.order(db, "NOV-01", datetime(2026, 11, 1, 0, 5))
    client = login("admin")

    october = client.get("/sales-history?month=2026-10").text
    assert "<b>1</b> đơn" in october and "/sales-history/file?month=2026-10" in october
    ws = load_workbook(BytesIO(client.get("/sales-history/file?month=2026-10").content))["sheet1"]
    assert [ws.cell(r, 18).value for r in range(2, ws.max_row + 1)] == ["OCT-31"]
    draft = client.get("/sales-history/draft?month=2026-10").content
    assert load_workbook(BytesIO(draft))["sheet1"].max_row == 2
    assert "<b>2</b> đơn" in client.get(PAGE).text  # OCT-31 stays until it is confirmed


def test_the_page_opens_on_last_month(db, login):
    setup.report_name(db)
    setup.order(db, "OCT", datetime(2026, 10, 20))
    setup.order(db, "NOV", datetime(2026, 11, 2))
    page = login("viewer").get("/sales-history").text
    assert 'name="month" value="2026-10"' in page
    assert "<b>1</b> đơn" in page and "31/10/2026" in page


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "abc", "2026-11-13"])
def test_a_malformed_month_is_refused(db, login, month):
    client = login("admin")
    assert client.get(f"/sales-history?month={month}").status_code == 422
    assert client.get(f"/sales-history/file?month={month}").status_code == 422
    resp = client.post("/sales-history/read-zrsd003", data={"month": month})
    assert resp.status_code == 422


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
    page = admin.get(PAGE).text
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
    assert "<b>3</b> đơn" in admin.get(PAGE).text
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
    assert "<button>Xác nhận đã dán</button>" not in viewer.get(PAGE).text

    resp = viewer.post(
        f"/sales-history/files/{file_id}/confirm",
        headers={"referer": "http://testserver/sales-history"},
        follow_redirects=False,
    )
    assert resp.status_code == 303 and resp.headers["location"].endswith("/sales-history")
    assert _count(db, SalesHistoryExported) == 0
    assert "Tài khoản xem không được thay đổi dữ liệu" in viewer.get(PAGE).text

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

    page = admin.get(PAGE).text
    assert f"DO {early.do_number} chưa có Tax Invoice Doc." in page
    assert 'href="#tax-invoice"' in page and "<b>2</b> đơn đã có DO" in page
    assert "Robot chưa được bật" in page and 'href="/sap-reports"' in page
    assert "/sales-history/read-zrsd003" not in page  # no robot configured

    configure_sap(db, SapTarget("QAS", "300"))
    db.expire_all()
    page = admin.get(PAGE).text
    assert 'action="/sales-history/read-zrsd003"' in page
    assert "từ\n    01/11/2026 đến 13/11/2026" in page  # whole month up to today

    viewer = login("viewer")
    assert "/sales-history/read-zrsd003" not in viewer.get(PAGE).text
    viewer.post("/sales-history/read-zrsd003", data={"month": "2026-11"})
    assert _count(db, SapJob) == 0

    resp = admin.post("/sales-history/read-zrsd003", data={"month": "2026-11"})
    assert "Robot sẽ đọc zrsd003 từ 01/11/2026 đến 13/11/2026" in resp.text
    assert str(resp.url).endswith("/sales-history?month=2026-11")  # back on the chosen month
    job = db.scalar(select(SapJob))
    assert job.kind == queue.READ_ZRSD003
    assert queue.payload_of(job) == {"date_from": "2026-11-01", "date_to": "2026-11-13"}
    again = admin.post("/sales-history/read-zrsd003", data={"month": "2026-11"}).text
    assert "Đã có việc" in again and _count(db, SapJob) == 1


def test_the_zrsd003_read_reaches_back_to_an_older_order_still_waiting(db, login):
    from shoponline.db.models import SapJob
    from shoponline.sapjobs import queue
    from shoponline.sapjobs.queue import SapTarget
    from tests.sap_setup import configure_sap

    setup.report_name(db)
    configure_sap(db, SapTarget("QAS", "300"))
    setup.order(db, "END-OCT", datetime(2026, 10, 30, 8), invoice=None)
    admin = login("admin")

    # The October file is made in November: the invoice of a 30/10 order is billed later.
    page = admin.get("/sales-history?month=2026-10").text
    assert "từ\n    01/10/2026 đến 13/11/2026" in page

    setup.order(db, "SEPT", datetime(2026, 9, 25, 8), invoice=None)
    admin.post("/sales-history/read-zrsd003", data={"month": "2026-10"})
    job = db.scalar(select(SapJob))
    assert queue.payload_of(job) == {"date_from": "2026-09-25", "date_to": "2026-11-13"}


def test_no_zrsd003_box_when_every_order_has_its_invoice(db, login):
    setup.report_name(db)
    setup.order(db, "A-1", datetime(2026, 11, 11))
    admin = login("admin")
    assert 'id="tax-invoice"' not in admin.get(PAGE).text
    resp = admin.post("/sales-history/read-zrsd003", data={"month": "2026-11"})
    assert "Không có đơn nào chờ Tax Invoice Doc." in resp.text


def _upload(client, path):
    with path.open("rb") as handle:
        return client.post(
            "/sales-history/settlement",
            data={"month": "2026-11"},
            files={"file": (path.name, handle, "application/octet-stream")},
        )


def _uploads(app):
    folder = app.state.settings.upload_dir
    return list(folder.glob("*")) if folder.exists() else []


def test_orders_waiting_for_settlement_have_their_own_box_and_enter_after_the_upload(
    db, login, app, tmp_path
):
    setup.report_name(db)
    setup.order(db, "GOOD", datetime(2026, 11, 11, 8))
    setup.order(db, "WAIT-1", datetime(2026, 11, 10, 9), settlement=None)
    setup.order(db, "NO-NAME", datetime(2026, 11, 11, 9), name=None, settlement=None)
    admin = login("admin")

    page = admin.get(PAGE).text
    assert 'id="settlement"' in page and "Đơn chờ tiền vô (2)" in page
    assert "<b>2</b> đơn chờ tiền vô" in page
    assert "10/11/2026 đến 13/11/2026" in page
    assert ">1</b> đơn bị chặn" in page  # NO-NAME also waits for money but is fixed elsewhere
    assert 'href="#settlement"' in page and 'action="/sales-history/settlement"' in page
    ws = load_workbook(BytesIO(_download(admin).content))["sheet1"]
    assert [ws.cell(r, 18).value for r in range(2, ws.max_row + 1)] == ["GOOD"]

    path = shopee_settlement_file(tmp_path / "s.xlsx", [shopee_settlement_row("WAIT-1", 55000.0)])
    resp = _upload(admin, path)
    assert "Tiền vô Shopee: 1 giao dịch của 1 đơn (1 mới, 0 đổi, 0 không đổi)" in resp.text
    assert _uploads(app) == []  # read once, then deleted

    assert "Đơn chờ tiền vô (1)" in admin.get(PAGE).text
    ws = load_workbook(BytesIO(_download(admin).content))["sheet1"]
    assert [(ws.cell(r, 18).value, ws.cell(r, 20).value) for r in range(2, ws.max_row + 1)] == [
        ("WAIT-1", 55000),
        ("GOOD", setup.SETTLED),
    ]


def test_a_page_with_only_waiting_orders_is_not_empty(db, login):
    setup.report_name(db)
    setup.order(db, "WAIT-1", datetime(2026, 11, 10, 9), settlement=None)
    admin = login("admin")

    page = admin.get(PAGE).text

    assert "Không có đơn nào chờ xuất" not in page
    assert "/sales-history/file" not in page
    resp = admin.get("/sales-history/file?month=2026-11", follow_redirects=True)
    assert "Không có đơn nào chờ xuất" not in resp.text
    assert "đang chờ hoặc bị chặn" in resp.text


def test_the_settlement_upload_is_for_admins_only(db, login, app, tmp_path):
    setup.order(db, "WAIT-1", datetime(2026, 11, 10, 9), settlement=None)
    path = shopee_settlement_file(tmp_path / "s.xlsx", [shopee_settlement_row("WAIT-1", 1.0)])
    viewer = login("viewer")

    assert 'action="/sales-history/settlement"' not in viewer.get(PAGE).text
    _upload(viewer, path)
    assert _count(db, PlatformSettlement) == 0
    assert _uploads(app) == []


def test_a_lazada_or_broken_file_is_refused_and_not_kept(db, login, app, tmp_path):
    admin = login("admin")

    resp = _upload(admin, lazada_settlement_file(tmp_path / "l.xlsx"))
    assert "Lazada Balance Transactions không có mã đơn" in resp.text
    bad = shopee_settlement_file(tmp_path / "b.xlsx", [shopee_settlement_row("A", "")])
    assert "không nhập gì" in _upload(admin, bad).text

    assert _count(db, PlatformSettlement) == 0
    assert _uploads(app) == []


def test_an_unexpected_error_still_deletes_the_uploaded_file(db, login, app, tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("shoponline.web.routes.sales_history.ingest_settlement", boom)
    path = shopee_settlement_file(tmp_path / "s.xlsx", [shopee_settlement_row("A", 1.0)])
    admin = login("admin")

    with pytest.raises(RuntimeError):
        _upload(admin, path)

    assert _uploads(app) == []


def _draft(client):
    resp = client.get("/sales-history/draft?month=2026-11", follow_redirects=False)
    assert resp.status_code == 200, resp.text
    return resp


def test_the_draft_downloads_without_storing_or_remembering_anything(db, login):
    setup.report_name(db)
    setup.order(db, "FULL", datetime(2026, 11, 11, 1))
    setup.order(db, "NO-INV", datetime(2026, 11, 11, 2), invoice=None)
    setup.order(db, "NO-NAME", datetime(2026, 11, 11, 3), name=None)
    admin = login("admin")

    resp = _draft(admin)

    disposition = resp.headers["content-disposition"]
    name = unquote(disposition.split("filename*=utf-8''")[1])
    assert name == "NHÁP SHOP ONLINE LỊCH SỬ 131126.xlsx"
    ws = load_workbook(BytesIO(resp.content))["sheet1"]
    assert [(ws.cell(r, 18).value, ws.cell(r, 21).value) for r in (2, 3)] == [
        ("FULL", None),
        ("NO-INV", "Chờ hóa đơn"),
    ]
    assert ws.max_row == 3
    assert _file_ids(db) == []
    assert _count(db, SalesHistoryFileOrder) == 0
    assert "NHÁP" not in admin.get(PAGE).text.split("File đã tải")[1]
    _download(admin)  # the real file is unchanged: only the complete order
    assert _count(db, SalesHistoryFileOrder) == 1


def test_a_draft_is_offered_and_downloads_when_only_waiting_orders_exist(db, login):
    setup.report_name(db)
    setup.order(db, "WAIT-1", datetime(2026, 11, 10, 9), settlement=None)
    viewer = login("viewer")

    page = viewer.get(PAGE).text

    assert "/sales-history/draft?month=2026-11" in page and "/sales-history/file" not in page
    assert _draft(viewer).content
    resp = viewer.get("/sales-history/file?month=2026-11", follow_redirects=True)
    assert "đang chờ hoặc bị chặn" in resp.text


def test_no_draft_when_no_order_can_be_one(db, login):
    setup.report_name(db)
    setup.order(db, "NO-NAME", datetime(2026, 11, 11), name=None)
    admin = login("admin")

    assert "/sales-history/draft" not in admin.get(PAGE).text
    resp = admin.get("/sales-history/draft?month=2026-11", follow_redirects=True)
    assert "Không có đơn nào để xuất nháp." in resp.text
