"""Return rows through the Shop Online page: download, confirm, unconfirm, delete."""

from datetime import datetime
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy import func, select

from shoponline.db.models import (
    GeneratedFile,
    SalesHistoryFileReturn,
    SalesReturnHistoryExported,
)
from shoponline.returns import service
from tests import sales_history_setup as setup

pytestmark = pytest.mark.usefixtures("frozen_today")  # today is 2026-11-13
PAGE = "/sales-history?month=2026-11"


def _download(client):
    resp = client.get("/sales-history/file?month=2026-11", follow_redirects=False)
    assert resp.status_code == 200, resp.text
    return load_workbook(BytesIO(resp.content)).active


def _files(db):
    db.expire_all()
    return list(
        db.scalars(
            select(GeneratedFile.id)
            .where(GeneratedFile.kind == "sales_history")
            .order_by(GeneratedFile.id)
        )
    )


def _exported(db):
    db.expire_all()
    return sorted(
        db.execute(
            select(SalesReturnHistoryExported.return_id, SalesReturnHistoryExported.kind)
        ).all()
    )


def _order_and_return(db, order_id="A"):
    setup.report_name(db)
    order = setup.order(db, order_id, datetime(2026, 11, 11, 9))
    return order, setup.returned(db, order, 80)


def test_a_return_before_pasting_goes_into_the_same_file_and_is_confirmed_with_it(db, login):
    order, sales_return = _order_and_return(db)
    admin = login("admin")
    assert "dòng trả hàng của <b>1</b> phiếu chờ dán" in admin.get(PAGE).text
    ws = _download(admin)
    assert ws.max_row == 3 and ws["N3"].value == -1 and ws["I3"].value == -1
    (file_id,) = _files(db)
    assert db.scalar(select(func.count()).select_from(SalesHistoryFileReturn)) == 1

    admin.post(f"/sales-history/files/{file_id}/confirm")
    assert _exported(db) == [(sales_return.id, "ISSUE")]
    assert "chờ dán" not in admin.get(PAGE).text


def test_a_file_with_only_return_rows_can_be_downloaded_confirmed_and_unconfirmed(db, login):
    setup.report_name(db)
    order = setup.order(db, "B", datetime(2026, 11, 11, 9))
    setup.pasted_order(db, order, setup.history_file(db))
    sales_return = setup.returned(db, order, 81)
    admin = login("admin")
    ws = _download(admin)
    assert ws.max_row == 2 and ws["J2"].value == -120000
    *_, file_id = _files(db)

    admin.post(f"/sales-history/files/{file_id}/confirm")
    assert _exported(db) == [(sales_return.id, "ISSUE")]
    assert "Gỡ xác nhận" in admin.get(PAGE).text

    admin.post(f"/sales-history/files/{file_id}/unconfirm")
    assert _exported(db) == []
    assert _download(admin).max_row == 2  # the rows come back


def test_a_confirmed_return_file_cannot_be_deleted(db, login):
    setup.report_name(db)
    order = setup.order(db, "C", datetime(2026, 11, 11, 9))
    setup.pasted_order(db, order, setup.history_file(db))
    setup.returned(db, order, 82)
    admin = login("admin")
    _download(admin)
    *_, file_id = _files(db)
    admin.post(f"/sales-history/files/{file_id}/confirm")
    page = admin.post(f"/sales-history/files/{file_id}/delete").text
    assert "gỡ xác nhận trước khi xóa" in page and file_id in _files(db)


def test_deleting_an_unconfirmed_return_file_keeps_its_rows_pending(db, login):
    setup.report_name(db)
    order = setup.order(db, "D", datetime(2026, 11, 11, 9))
    setup.pasted_order(db, order, setup.history_file(db))
    setup.returned(db, order, 83)
    admin = login("admin")
    _download(admin)
    *_, file_id = _files(db)
    admin.post(f"/sales-history/files/{file_id}/delete")
    assert file_id not in _files(db)
    assert db.scalar(select(func.count()).select_from(SalesHistoryFileReturn)) == 0
    assert _download(admin).max_row == 2


def test_confirming_drops_another_unconfirmed_file_with_the_same_return_rows(db, login):
    setup.report_name(db)
    order = setup.order(db, "E", datetime(2026, 11, 11, 9))
    setup.pasted_order(db, order, setup.history_file(db))
    setup.returned(db, order, 84)
    admin = login("admin")
    _download(admin)
    _download(admin)
    *_, first, second = _files(db)
    admin.post(f"/sales-history/files/{first}/confirm")
    assert second not in _files(db)


def test_unconfirming_negative_rows_whose_reversal_was_confirmed_later_is_refused(
    db, login, monkeypatch
):
    setup.report_name(db)
    order = setup.order(db, "F", datetime(2026, 11, 11, 9))
    setup.pasted_order(db, order, setup.history_file(db))
    sales_return = setup.returned(db, order, 85)
    admin = login("admin")
    _download(admin)
    *_, issue_file = _files(db)
    admin.post(f"/sales-history/files/{issue_file}/confirm")

    service.void(db, sales_return.id, "lập nhầm", "admin")
    db.commit()
    ws = _download(admin)
    assert ws["N2"].value == 1 and ws["I2"].value == 1
    *_, void_file = _files(db)
    admin.post(f"/sales-history/files/{void_file}/confirm")
    assert _exported(db) == [(sales_return.id, "ISSUE"), (sales_return.id, "VOID")]

    page = admin.post(f"/sales-history/files/{issue_file}/unconfirm").text
    assert "gỡ xác nhận file đó trước" in page
    assert len(_exported(db)) == 2

    admin.post(f"/sales-history/files/{void_file}/unconfirm")
    admin.post(f"/sales-history/files/{issue_file}/unconfirm")
    assert _exported(db) == []


def test_a_return_file_is_kept_on_disk_until_its_rows_are_confirmed(db, login):
    setup.report_name(db)
    order = setup.order(db, "G", datetime(2026, 11, 11, 9))
    setup.pasted_order(db, order, setup.history_file(db))
    setup.returned(db, order, 86)
    admin = login("admin")
    _download(admin)
    *_, file_id = _files(db)
    stored = Path(db.get(GeneratedFile, file_id).stored_path)
    assert stored.exists()
    admin.post(f"/sales-history/files/{file_id}/confirm")
    assert not stored.exists()
