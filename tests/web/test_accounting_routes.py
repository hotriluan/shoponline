import hashlib
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shoponline.accounting import ledger, runs
from shoponline.config import Settings
from shoponline.db.models import (
    AccountingRun,
    AccountingRunRead,
    AccountingRunSource,
    AccountingSentDelivery,
    EventLog,
    GeneratedFile,
    SapJob,
)
from shoponline.sapjobs import queue
from shoponline.web.app import create_app
from shoponline.web.auth import set_user
from tests.accounting.scenario import (
    QA,
    TODAY,
    delivery_row,
    finish_job,
    make_batch,
    make_order,
    make_source,
)
from tests.sap_setup import NO_ENV, configure_sap

pytestmark = pytest.mark.usefixtures("frozen_today")


@pytest.fixture(autouse=True)
def old_cutoff(db):
    ledger.set_cutoff(db, date(2000, 1, 1), "test")


@pytest.fixture
def app(db, tmp_path):
    settings = Settings(database_url="unused", secret_key="s" * 40, data_dir=tmp_path / "data")
    configure_sap(db, QA)
    set_user(db, "admin", "admin-password", "admin")
    set_user(db, "viewer", "viewer-password", "viewer")
    return create_app(
        settings,
        session_factory=lambda: Session(
            bind=db.bind, join_transaction_mode="create_savepoint", expire_on_commit=False
        ),
        env=NO_ENV,
    )


def _login(app, username):
    client = TestClient(app)
    client.post("/login", data={"username": username, "password": f"{username}-password"})
    return client


def _prepare(db, tmp_path, *, extra_order=False):
    """An open run whose reads are done: 12/11 holds DO 1900000001, 13/11 has no data."""
    make_order(db, make_batch(db, gi=date(2026, 11, 12)), "A1", "210000001")
    if extra_order:
        make_order(
            db, make_batch(db, gi=date(2026, 11, 12), processing=date(2026, 11, 9)), "A2", "2"
        )
    run = runs.start_run(db, QA, "admin", TODAY)
    first, second = db.scalars(
        select(AccountingRunRead)
        .where(AccountingRunRead.run_id == run.id)
        .order_by(AccountingRunRead.gi_date)
    ).all()
    record = make_source(db, tmp_path / "a.xlsx", [delivery_row("1900000001", "210000001")])
    finish_job(db, first.sap_job_id, record=record)
    finish_job(db, second.sap_job_id, no_data=True)
    db.flush()
    return run


def _fingerprint(client, run):
    page = client.get(f"/accounting/runs/{run.id}").text
    return re.search(r'name="fingerprint" value="([0-9a-f]+)"', page).group(1)


def _counts(db):
    db.expire_all()
    return (
        db.scalar(select(func.count()).select_from(AccountingRun)),
        db.scalar(select(func.count()).select_from(AccountingSentDelivery)),
        db.scalar(select(func.count()).select_from(AccountingRunSource)),
        db.scalar(select(func.count()).select_from(SapJob)),
    )


def test_viewer_is_refused_every_action_and_nothing_changes(db, app, tmp_path):
    run = _prepare(db, tmp_path)
    before = _counts(db)
    fingerprint = _fingerprint(_login(app, "admin"), run)
    viewer = _login(app, "viewer")
    read = db.scalar(select(AccountingRunRead).where(AccountingRunRead.run_id == run.id))

    responses = [
        viewer.post("/accounting/runs", follow_redirects=False),
        viewer.post(f"/accounting/runs/{run.id}/reads/{read.id}/retry", follow_redirects=False),
        viewer.post(
            f"/accounting/runs/{run.id}/upload",
            files={"file": ("z.xlsx", b"x", "application/octet-stream")},
            follow_redirects=False,
        ),
        viewer.post(
            f"/accounting/runs/{run.id}/attach", data={"import_batch_id": 1}, follow_redirects=False
        ),
        viewer.post(
            f"/accounting/runs/{run.id}/finalize",
            data={"fingerprint": fingerprint, "allow_partial": "1", "ack_missing": "1"},
            follow_redirects=False,
        ),
        viewer.post(f"/accounting/runs/{run.id}/cancel", follow_redirects=False),
        viewer.get(f"/accounting/runs/{run.id}/draft", follow_redirects=False),
    ]

    assert all(r.status_code == 303 for r in responses)
    assert "không được thay đổi" in viewer.get("/accounting").text
    assert _counts(db) == before
    assert db.get(AccountingRun, run.id).status == ledger.OPEN


def test_viewer_can_look_and_download_a_finalized_file(db, app, tmp_path):
    run = _prepare(db, tmp_path)
    admin = _login(app, "admin")
    admin.post(
        f"/accounting/runs/{run.id}/finalize",
        data={"fingerprint": _fingerprint(admin, run)},
    )
    viewer = _login(app, "viewer")

    assert viewer.get("/accounting").status_code == 200
    page = viewer.get(f"/accounting/runs/{run.id}").text
    assert "Đã chốt" in page and "Chốt và ghi sổ" not in page
    assert viewer.get(f"/accounting/runs/{run.id}/file").status_code == 200


def test_admin_starts_a_run_and_a_second_click_joins_it(db, app):
    make_order(db, make_batch(db, gi=date(2026, 11, 12)), "A1", "210000001")
    admin = _login(app, "admin")

    first = admin.post("/accounting/runs", follow_redirects=False)
    second = admin.post("/accounting/runs", follow_redirects=False)

    assert first.headers["location"] == second.headers["location"]
    db.expire_all()
    assert len(db.scalars(select(SapJob)).all()) == 2
    assert "Đang mở" in admin.get("/accounting").text


def test_nothing_waiting_is_said_plainly(db, app):
    admin = _login(app, "admin")
    resp = admin.post("/accounting/runs", follow_redirects=True)
    assert "Không có đơn nào đang chờ" in resp.text


def test_finalize_is_gated_by_the_reviewed_fingerprint(db, app, tmp_path):
    run = _prepare(db, tmp_path)
    admin = _login(app, "admin")
    fingerprint = _fingerprint(admin, run)
    upload = make_source(
        db, tmp_path / "b.xlsx", [delivery_row("1900000099", "299")], imported_by="luan"
    )
    runs.attach_upload(db, run, upload, "admin")  # the data moved since the draft was reviewed

    page = admin.post(f"/accounting/runs/{run.id}/finalize", data={"fingerprint": fingerprint}).text

    assert "Dữ liệu đã đổi" in page
    db.expire_all()
    assert db.get(AccountingRun, run.id).status == ledger.OPEN
    assert not db.scalars(select(AccountingSentDelivery)).all()


def test_orders_without_a_do_need_the_acknowledgement(db, app, tmp_path):
    run = _prepare(db, tmp_path, extra_order=True)
    admin = _login(app, "admin")
    fingerprint = _fingerprint(admin, run)
    page = admin.get(f"/accounting/runs/{run.id}").text
    assert "Chưa thấy DO (1)" in page and "Tôi đã xem danh sách đơn chưa có DO" in page
    assert 'id="finalize-button" disabled' in page

    refused = admin.post(f"/accounting/runs/{run.id}/finalize", data={"fingerprint": fingerprint})
    assert "cần xác nhận" in refused.text
    assert not db.scalars(select(AccountingSentDelivery)).all()

    admin.post(
        f"/accounting/runs/{run.id}/finalize",
        data={"fingerprint": fingerprint, "ack_missing": "1"},
    )
    db.expire_all()
    run = db.get(AccountingRun, run.id)
    assert run.status == ledger.FINALIZED and "SHOPEE A2" in run.missing_note
    event = db.scalars(select(EventLog).where(EventLog.kind == "accounting_run_finalized")).one()
    assert "SHOPEE A2" in event.detail


def test_unread_pairs_need_the_partial_acknowledgement(db, app, tmp_path):
    run = _prepare(db, tmp_path)
    read = db.scalars(
        select(AccountingRunRead)
        .where(AccountingRunRead.run_id == run.id)
        .order_by(AccountingRunRead.gi_date.desc())
    ).first()
    finish_job(db, read.sap_job_id, status=queue.FAILED, error="SAP lỗi")
    admin = _login(app, "admin")
    fingerprint = _fingerprint(admin, run)

    refused = admin.post(f"/accounting/runs/{run.id}/finalize", data={"fingerprint": fingerprint})
    assert "SHOPEE 13/11/2026" in refused.text and "Còn chưa có dữ liệu" in refused.text
    assert db.get(AccountingRun, run.id).status == ledger.OPEN

    admin.post(
        f"/accounting/runs/{run.id}/finalize",
        data={"fingerprint": fingerprint, "allow_partial": "1"},
    )
    db.expire_all()
    assert db.get(AccountingRun, run.id).status == ledger.FINALIZED


def test_finalized_file_downloads_as_stored_and_run_is_read_only(db, app, tmp_path):
    run = _prepare(db, tmp_path)
    admin = _login(app, "admin")
    admin.post(
        f"/accounting/runs/{run.id}/finalize", data={"fingerprint": _fingerprint(admin, run)}
    )
    db.expire_all()
    record = db.scalars(select(GeneratedFile)).one()

    first = admin.get(f"/accounting/runs/{run.id}/file")
    second = admin.get(f"/accounting/runs/{run.id}/file")

    assert first.content == second.content
    assert hashlib.sha256(first.content).hexdigest() == record.sha256
    page = admin.get(f"/accounting/runs/{run.id}").text
    assert "Chốt và ghi sổ" not in page and "Hủy đợt" not in page
    assert "Đã ghi 1 DO vào sổ" in page

    again = admin.post(
        f"/accounting/runs/{run.id}/finalize", data={"fingerprint": "x"}, follow_redirects=True
    )
    assert "không còn mở" in again.text


def test_draft_download_is_named_and_records_nothing(db, app, tmp_path):
    run = _prepare(db, tmp_path)
    before = _counts(db)
    resp = _login(app, "admin").get(f"/accounting/runs/{run.id}/draft")
    assert resp.status_code == 200 and "NH" in resp.headers["content-disposition"]
    assert _counts(db) == before and not db.scalars(select(GeneratedFile)).all()


def test_cancel_closes_the_run_without_touching_the_ledger(db, app, tmp_path):
    run = _prepare(db, tmp_path)
    admin = _login(app, "admin")
    admin.post(f"/accounting/runs/{run.id}/cancel")
    db.expire_all()
    assert db.get(AccountingRun, run.id).status == ledger.CANCELLED
    assert not db.scalars(select(AccountingSentDelivery)).all()


def test_retry_a_failed_read_from_the_run_page(db, app, tmp_path):
    make_order(db, make_batch(db, gi=date(2026, 11, 12)), "A1", "210000001")
    run = runs.start_run(db, QA, "admin", TODAY)
    read = db.scalars(select(AccountingRunRead).where(AccountingRunRead.run_id == run.id)).first()
    job = finish_job(db, read.sap_job_id, status=queue.FAILED, error="SAP lỗi")
    admin = _login(app, "admin")
    assert "Đọc lại" in admin.get(f"/accounting/runs/{run.id}").text

    admin.post(f"/accounting/runs/{run.id}/reads/{read.id}/retry")

    db.expire_all()
    assert db.get(SapJob, job.id).status == queue.PENDING


def test_upload_to_the_run_covers_a_pair_and_a_missing_robot_still_allows_a_run(db, tmp_path):
    settings = Settings(database_url="unused", secret_key="s" * 40, data_dir=tmp_path / "data")
    configure_sap(db, None)
    set_user(db, "admin", "admin-password", "admin")
    app = create_app(
        settings,
        session_factory=lambda: Session(
            bind=db.bind, join_transaction_mode="create_savepoint", expire_on_commit=False
        ),
        env=NO_ENV,
    )
    make_order(db, make_batch(db, gi=date(2026, 11, 12)), "A1", "210000001")
    admin = _login(app, "admin")

    start = admin.post("/accounting/runs", follow_redirects=True)
    assert "Robot chưa được bật" in start.text and "Chưa có việc" in start.text
    assert not db.scalars(select(SapJob)).all()
    run_url = str(start.url).split("testserver")[1]

    from tests.fixtures.build_fixtures import zrsd004_file

    path = zrsd004_file(tmp_path / "z4.xlsx", [delivery_row("1900000001", "210000001")])
    with open(path, "rb") as fh:
        resp = admin.post(
            f"{run_url}/upload",
            files={"file": (path.name, fh, "application/octet-stream")},
            follow_redirects=True,
        )
    assert "Đã thêm file zrsd004 vào đợt" in resp.text
    assert "Xong, có DO" in resp.text
