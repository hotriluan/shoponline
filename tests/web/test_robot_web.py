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
from shoponline.web.app import create_app
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
