from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.config import Settings
from shoponline.db.models import SapJob
from shoponline.domain.sku_mapping import upsert_mapping
from shoponline.importers.order_import import import_orders
from shoponline.importers.shopee_orders import read_shopee_orders
from shoponline.sapjobs import queue
from shoponline.sapjobs.queue import SapTarget
from shoponline.web.app import UNVERIFIED_MESSAGE, create_app
from shoponline.web.auth import set_user
from tests.fixtures.build_fixtures import shopee_orders_file, shopee_row
from tests.sap_setup import NO_ENV, configure_sap

QA = SapTarget("QAS", "300")


def _app(db, tmp_path, target):
    settings = Settings(database_url="unused", secret_key="s" * 40, data_dir=tmp_path / "data")
    configure_sap(db, target)
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


@pytest.fixture
def batch(db, tmp_path):
    upsert_mapping(db, "SHOPEE", "Sơn thử A", "Màu 01,1 lít", "100000001", "SAP A", "t")
    path = shopee_orders_file(tmp_path / "s.xlsx", [shopee_row("A1")])
    return import_orders(db, read_shopee_orders(path), "SHOPEE", date(2026, 11, 11), "t").batch


def _jobs(db):
    db.expire_all()
    return db.scalars(select(SapJob).order_by(SapJob.id)).all()


def test_without_robot_confirm_queues_nothing(db, tmp_path, batch):
    client = _login(_app(db, tmp_path, None), "admin")
    client.post(f"/batches/{batch.id}/confirm")
    assert _jobs(db) == []
    page = client.get(f"/batches/{batch.id}").text
    assert "robot đọc zrsd004" not in page
    assert "Robot chưa được bật" in client.get("/robot").text


def test_confirm_queues_zrsd001_and_button_queues_zrsd004(db, tmp_path, batch):
    client = _login(_app(db, tmp_path, QA), "admin")
    page = client.post(f"/batches/{batch.id}/confirm").text
    assert "robot sẽ đọc zrsd001" in page and "robot đọc zrsd004 ngày 12/11/2026" in page

    client.post(f"/batches/{batch.id}/accounting-file")
    client.post(f"/batches/{batch.id}/accounting-file")  # second click is refused
    jobs = _jobs(db)
    assert [(j.kind, j.target_system, j.target_client) for j in jobs] == [
        (queue.READ_ZRSD001, "QAS", "300"),
        (queue.READ_ZRSD004, "QAS", "300"),
    ]
    assert queue.payload_of(jobs[1]) == {
        "platform": "SHOPEE",
        "sold_to": "1200001145",
        "gi_date": "2026-11-12",
    }
    page = client.get("/robot").text
    assert "read_zrsd001" in page and "QAS/300" in page


def test_pause_shows_banner_and_viewer_cannot_switch(db, tmp_path):
    app = _app(db, tmp_path, QA)
    viewer = _login(app, "viewer")
    viewer.post("/robot/pause", data={"reason": "thử"})
    assert not queue.control(db).paused

    admin = _login(app, "admin")
    admin.post("/robot/pause", data={"reason": "bảo trì SAP"})
    db.expire_all()
    assert queue.control(db).paused
    assert "Robot SAP đang dừng: bảo trì SAP" in admin.get("/batches").text
    admin.post("/robot/resume")
    db.expire_all()
    assert not queue.control(db).paused
    assert "Robot SAP đang dừng" not in admin.get("/batches").text


def test_retry_failed_read_job_and_evidence_stays_inside_folder(db, tmp_path):
    app = _app(db, tmp_path, QA)
    job = queue.enqueue(db, queue.READ_ZRSD004, QA, "k", {}, "admin")
    queue.claim(db)
    queue.fail(db, job, "boom", evidence=str(tmp_path / "outside.png"))
    (tmp_path / "outside.png").write_bytes(b"x")

    client = _login(app, "admin")
    assert client.get(f"/robot/jobs/{job.id}/evidence").status_code == 404
    client.post(f"/robot/jobs/{job.id}/retry")
    db.expire_all()
    assert db.get(SapJob, job.id).status == queue.PENDING


def _finish(db, job):
    queue.claim(db)
    queue.complete(db, job, {})


def test_reread_zrsd001_after_the_first_read_is_done(db, tmp_path, batch):
    client = _login(_app(db, tmp_path, QA), "admin")
    client.post(f"/batches/{batch.id}/confirm")
    first = _jobs(db)[0]

    page = client.post(f"/batches/{batch.id}/read-zrsd001").text
    assert f"Đã có việc #{first.id}" in page  # still open: refused with the job number
    assert len(_jobs(db)) == 1

    _finish(db, first)
    page = client.post(f"/batches/{batch.id}/read-zrsd001").text
    assert "Robot sẽ đọc lại zrsd001" in page
    assert [j.kind for j in _jobs(db)] == [queue.READ_ZRSD001, queue.READ_ZRSD001]


def test_reread_is_refused_for_unconfirmed_batch(db, tmp_path, batch):
    client = _login(_app(db, tmp_path, QA), "admin")
    page = client.post(f"/batches/{batch.id}/read-zrsd001").text
    assert "Lô chưa xác nhận" in page and _jobs(db) == []


def test_robot_form_queues_the_same_zrsd004_as_the_batch_button(db, tmp_path, batch):
    client = _login(_app(db, tmp_path, QA), "admin")
    client.post(f"/batches/{batch.id}/accounting-file")
    from_button = queue.payload_of(_jobs(db)[0])
    _finish(db, _jobs(db)[0])

    form = {"report": "zrsd004", "platform": "SHOPEE", "gi_date": "2026-11-12"}
    assert "Robot sẽ đọc zrsd004" in client.post("/robot/jobs/new", data=form).text
    assert queue.payload_of(_jobs(db)[1]) == from_button
    assert "Đã có việc" in client.post("/robot/jobs/new", data=form).text
    assert len(_jobs(db)) == 2


def test_robot_form_reads_a_day_without_batches_but_not_the_future(db, tmp_path):
    client = _login(_app(db, tmp_path, QA), "admin")
    ok = {"report": "zrsd004", "platform": "SHOPEE", "gi_date": "2026-01-05"}
    client.post("/robot/jobs/new", data=ok)
    assert queue.payload_of(_jobs(db)[0])["gi_date"] == "2026-01-05"

    future = {**ok, "gi_date": "2999-01-01"}
    assert "chưa tới" in client.post("/robot/jobs/new", data=future).text
    unknown = {**ok, "platform": "NOPE"}
    assert "Không có sàn NOPE" in client.post("/robot/jobs/new", data=unknown).text
    assert len(_jobs(db)) == 1


def test_robot_form_zrsd001_needs_a_confirmed_batch(db, tmp_path, batch):
    client = _login(_app(db, tmp_path, QA), "admin")
    form = {"report": "zrsd001", "batch_id": str(batch.id)}
    assert "chưa xác nhận" in client.post("/robot/jobs/new", data=form).text
    assert "Chọn một lô" in client.post("/robot/jobs/new", data={"report": "zrsd001"}).text
    assert _jobs(db) == []

    client.post(f"/batches/{batch.id}/confirm")
    _finish(db, _jobs(db)[0])
    assert "Robot sẽ đọc zrsd001" in client.post("/robot/jobs/new", data=form).text
    assert len(_jobs(db)) == 2
    assert client.post("/robot/jobs/new", data={"report": "zrsd005"}).status_code == 400


def test_commands_are_refused_until_the_connection_is_verified(db, tmp_path, batch):
    app = _app(db, tmp_path, QA)
    client = _login(app, "admin")
    client.post(f"/batches/{batch.id}/confirm")
    _finish(db, _jobs(db)[0])
    configure_sap(db, SapTarget("QAS", "400"), verified=False)  # a changed system is unchecked
    db.expire_all()
    assert UNVERIFIED_MESSAGE in client.post(f"/batches/{batch.id}/read-zrsd001").text
    form = {"report": "zrsd004", "platform": "SHOPEE", "gi_date": "2026-11-12"}
    assert UNVERIFIED_MESSAGE in client.post("/robot/jobs/new", data=form).text
    assert len(_jobs(db)) == 1
    assert "Đọc zrsd001" not in client.get("/robot").text


def test_viewer_cannot_command_and_sees_no_form(db, tmp_path, batch):
    app = _app(db, tmp_path, QA)
    admin = _login(app, "admin")
    admin.post(f"/batches/{batch.id}/confirm")
    _finish(db, _jobs(db)[0])
    assert 'action="/robot/jobs/new"' in admin.get("/robot").text
    assert "Đọc lại zrsd001" in admin.get(f"/batches/{batch.id}").text

    viewer = _login(app, "viewer")
    form = {"report": "zrsd004", "platform": "SHOPEE", "gi_date": "2026-11-12"}
    viewer.post("/robot/jobs/new", data=form)
    viewer.post(f"/batches/{batch.id}/read-zrsd001")
    assert len(_jobs(db)) == 1
    assert 'action="/robot/jobs/new"' not in viewer.get("/robot").text
    assert "Đọc lại zrsd001" not in viewer.get(f"/batches/{batch.id}").text


def test_robot_without_target_shows_no_form(db, tmp_path):
    client = _login(_app(db, tmp_path, None), "admin")
    assert 'action="/robot/jobs/new"' not in client.get("/robot").text
