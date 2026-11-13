"""Worker logic against the fake SAP GUI; report results must match the phase 4 upload path."""

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.config import Settings
from shoponline.db.models import ImportBatch, SalesOrder, SapJob, SapSoRef
from shoponline.domain import states
from shoponline.domain.sku_mapping import upsert_mapping
from shoponline.importers.order_import import import_orders
from shoponline.importers.shopee_orders import read_shopee_orders
from shoponline.sapjobs import queue
from shoponline.sapjobs.queue import SapTarget
from shoponline.sapjobs.report_requests import request_zrsd001, request_zrsd004
from shoponline.saprobot.errors import NoReportData, SapMessageError
from shoponline.saprobot.screen import Screens
from shoponline.saprobot.session import LoginConfig
from shoponline.saprobot.worker import JobContext, Transaction, TransactionResult, Worker
from tests.fixtures.build_fixtures import (
    shopee_orders_file,
    shopee_row,
    zrsd001_file,
    zrsd001_row,
    zrsd004_file,
    zrsd004_row,
)
from tests.sap_setup import NO_ENV, configure_sap
from tests.saprobot.fake_sap import FakeEngine, FakeSession, Info, engine_with

QA = SapTarget("QAS", "300")
LOGIN = LoginConfig(connection="QA robot", user="robot01", password="pw")


@pytest.fixture
def settings(tmp_path):
    return Settings(
        database_url="unused",
        secret_key="s" * 40,
        data_dir=tmp_path / "data",
    )


@pytest.fixture(autouse=True)
def sap_ready(db):
    configure_sap(db, QA)


@pytest.fixture
def batch(db, tmp_path):
    upsert_mapping(db, "SHOPEE", "Sơn thử A", "Màu 01,1 lít", "100000001", "SAP A", "t")
    path = shopee_orders_file(tmp_path / "s.xlsx", [shopee_row("A1", quantity=2)])
    return import_orders(db, read_shopee_orders(path), "SHOPEE", date(2026, 11, 11), "t").batch


def _factory(db):
    return lambda: Session(
        bind=db.bind, join_transaction_mode="create_savepoint", expire_on_commit=False
    )


def _worker(db, settings, gui, transactions):
    return Worker(
        settings,
        _factory(db),
        lambda: engine_with(gui),
        Screens({}),
        [],
        transactions=transactions,
        env=NO_ENV,
        login_provider=lambda _db: LOGIN,
    )


def _qa_session():
    return FakeSession(Info("QAS", "300", "ROBOT01"))


def _job(db, job_id) -> SapJob:
    db.expire_all()
    return db.get(SapJob, job_id)


def test_zrsd001_read_goes_through_the_upload_functions(db, settings, batch, tmp_path):
    report = zrsd001_file(
        tmp_path / "export.xlsx", [zrsd001_row("210000001", "A1", "100000001", 2, 200000)]
    )
    seen = {}

    def read(ctx: JobContext) -> TransactionResult:
        seen.update(ctx.payload)
        ctx.step()
        return TransactionResult(file=report)

    job = request_zrsd001(db, QA, batch, "admin")
    worker = _worker(db, settings, _qa_session(), {queue.READ_ZRSD001: Transaction(read, False)})
    assert worker.run_once() is True

    job = _job(db, job.id)
    assert job.status == queue.DONE, job.error
    assert queue.result_of(job)["linked"] == 1
    assert seen["sold_to"] and seen["date_from"] == "2026-11-11" and seen["selection"] == "complete"
    order = db.scalar(select(SalesOrder).where(SalesOrder.platform_order_id == "A1"))
    assert order.status == states.SO_LINKED and order.so_number == "210000001"
    record = db.get(ImportBatch, job.import_batch_id)
    assert record.kind == "zrsd001" and record.imported_by == "robot"
    assert db.get(SapSoRef, "210000001").net_value_incl == 200000
    assert worker.run_once() is False  # queue empty


def test_reading_zrsd001_twice_creates_no_duplicate_links(db, settings, batch, tmp_path):
    report = zrsd001_file(
        tmp_path / "export.xlsx", [zrsd001_row("210000001", "A1", "100000001", 2, 200000)]
    )
    txn = Transaction(lambda ctx: TransactionResult(file=report), False)
    results = []
    for _ in range(2):
        job = request_zrsd001(db, QA, batch, "admin")
        _worker(db, settings, _qa_session(), {queue.READ_ZRSD001: txn}).run_once()
        results.append(queue.result_of(_job(db, job.id)))

    assert results[0]["linked"] == 1
    assert results[1].get("new", 0) == 0 and results[1].get("linked", 0) == 0
    assert len(db.scalars(select(SapSoRef)).all()) == 1
    order = db.scalar(select(SalesOrder).where(SalesOrder.platform_order_id == "A1"))
    assert order.so_number == "210000001"


def test_zrsd004_read_marks_delivered(db, settings, batch, tmp_path):
    from shoponline.importers.sap_reports import read_zrsd001
    from shoponline.reconcile.so_link import store_so_reports

    z1 = zrsd001_file(tmp_path / "z1.xlsx", [zrsd001_row("210000001", "A1", "100000001", 2)])
    store_so_reports(db, read_zrsd001(z1), "t")
    z4 = zrsd004_file(tmp_path / "z4.xlsx", [zrsd004_row("1900000001", "210000001", "100000001")])
    job = request_zrsd004(db, QA, batch.platform, batch.gi_date, "admin")
    assert queue.payload_of(job)["sold_to"] == "1200001145"
    txn = Transaction(lambda ctx: TransactionResult(file=z4), False)
    _worker(db, settings, _qa_session(), {queue.READ_ZRSD004: txn}).run_once()
    job = _job(db, job.id)
    assert job.status == queue.DONE and queue.result_of(job)["delivered"] == 1


def test_wrong_system_fails_the_job_and_pauses_the_robot(db, settings, batch):
    job = request_zrsd001(db, QA, batch, "admin")
    called = []
    txn = Transaction(lambda ctx: called.append(1), False)
    prod = FakeSession(Info("PRD", "100", "ROBOT01"))
    _worker(db, settings, prod, {queue.READ_ZRSD001: txn}).run_once()
    job = _job(db, job.id)
    assert job.status == queue.FAILED and "PRD/100" in job.error
    assert called == []
    assert queue.control(db).paused


def test_unknown_popup_needs_review_with_screenshot(db, settings, batch):
    job = request_zrsd001(db, QA, batch, "admin")
    gui = _qa_session()

    def read(ctx):
        gui.popup("Save changes?", "Unsaved data")
        ctx.step()

    _worker(db, settings, gui, {queue.READ_ZRSD001: Transaction(read, False)}).run_once()
    job = _job(db, job.id)
    assert job.status == queue.NEED_REVIEW and "Save changes" in job.error
    assert job.evidence_path and job.evidence_path.endswith(".png")
    assert gui.actions == []  # pressed nothing


def test_interruption_of_a_write_job_is_unknown_not_failed(db, settings):
    job = queue.enqueue(db, "create_so", QA, "so:A1", {}, "admin")

    def create(ctx):
        raise RuntimeError("The connection to SAP was lost")

    _worker(db, settings, _qa_session(), {"create_so": Transaction(create, True)}).run_once()
    assert _job(db, job.id).status == queue.UNKNOWN


def test_sap_error_message_fails_read_job(db, settings, batch):
    job = request_zrsd001(db, QA, batch, "admin")
    gui = _qa_session()

    def read(ctx):
        gui.status.MessageType, gui.status.Text = "E", "No authorization for ZRSD001"
        ctx.step()

    _worker(db, settings, gui, {queue.READ_ZRSD001: Transaction(read, False)}).run_once()
    job = _job(db, job.id)
    assert job.status == queue.FAILED and SapMessageError.__name__ in job.error


def test_bad_report_file_fails_without_storing_anything(db, settings, batch, tmp_path):
    bad = zrsd004_file(tmp_path / "wrong.xlsx", [zrsd004_row("19", "21", "1")])  # not zrsd001
    job = request_zrsd001(db, QA, batch, "admin")
    txn = Transaction(lambda ctx: TransactionResult(file=bad), False)
    _worker(db, settings, _qa_session(), {queue.READ_ZRSD001: txn}).run_once()
    job = _job(db, job.id)
    assert job.status == queue.FAILED and "Không nhập được" in job.error
    assert db.scalar(select(ImportBatch).where(ImportBatch.kind == "zrsd001")) is None


def test_missing_transaction_fails_and_three_failures_pause(db, settings):
    worker = _worker(db, settings, _qa_session(), {})
    for i in range(4):
        queue.enqueue(db, queue.READ_ZRSD004, QA, f"k{i}", {}, "admin")
    for _ in range(3):
        assert worker.run_once() is True
    assert queue.control(db).paused
    assert worker.run_once() is False  # paused: the fourth job waits
    pending = db.scalars(select(SapJob).where(SapJob.status == queue.PENDING)).all()
    assert len(pending) == 1
    failed = db.scalars(select(SapJob).where(SapJob.status == queue.FAILED)).all()
    assert all("Chưa có thao tác" in j.error for j in failed)


def test_guard_trip_fails_the_job_pauses_the_robot_and_keeps_a_screenshot(db, settings, batch):
    from shoponline.db.models import EventLog

    job = request_zrsd001(db, QA, batch, "admin")
    gui = _qa_session()
    gui.Info.Transaction = "ZRSD001"
    gui.on_press = lambda element_id: setattr(gui.Info, "Transaction", "VA02")
    after_trip = []

    def read(ctx):
        ctx.gui.find("wnd[0]/usr/btnOPEN").press()  # SAP jumps to VA02
        after_trip.append(1)

    _worker(db, settings, gui, {queue.READ_ZRSD001: Transaction(read, False)}).run_once()
    job = _job(db, job.id)
    assert job.status == queue.FAILED and "VA02" in job.error
    assert job.evidence_path and job.evidence_path.endswith(".png")
    assert after_trip == []
    control = queue.control(db)
    assert control.paused and "VA02" in control.paused_reason
    events = db.scalars(select(EventLog.kind).where(EventLog.actor == "robot")).all()
    assert "robot_guard_violation" in events


def test_session_left_on_a_foreign_tcode_stops_before_the_transaction(db, settings, batch):
    job = request_zrsd001(db, QA, batch, "admin")
    gui = _qa_session()
    gui.Info.Transaction = "VA02"
    called = []
    txn = Transaction(lambda ctx: called.append(1), False)
    _worker(db, settings, gui, {queue.READ_ZRSD001: txn}).run_once()
    assert _job(db, job.id).status == queue.FAILED
    assert called == [] and gui.actions == []
    assert queue.control(db).paused


# ---------------------------------------------------------------- logon only for a job


def test_logs_in_for_the_job_and_logs_off_right_after(db, settings, batch, tmp_path):
    report = zrsd001_file(
        tmp_path / "export.xlsx", [zrsd001_row("210000001", "A1", "100000001", 2, 200000)]
    )
    engine = FakeEngine(login_as=Info("QAS", "300", "ROBOT01"))  # nobody logged on
    screens = Screens({"login": {"user": "wnd[0]/usr/user", "password": "wnd[0]/usr/pw"}})
    worker = Worker(
        settings,
        _factory(db),
        lambda: engine,
        screens,
        [],
        transactions={
            queue.READ_ZRSD001: Transaction(lambda ctx: TransactionResult(report), False)
        },
        env=NO_ENV,
        login_provider=lambda _db: LOGIN,
    )
    job = request_zrsd001(db, QA, batch, "admin")
    worker.run_once()
    assert _job(db, job.id).status == queue.DONE
    assert engine.opened == ["QA robot"]
    assert engine.connections == [] and len(engine.closed) == 1


def test_failed_job_still_logs_off_after_the_screenshot(db, settings, batch):
    job = request_zrsd001(db, QA, batch, "admin")
    gui = _qa_session()

    def read(ctx):
        gui.status.MessageType, gui.status.Text = "E", "No authorization for ZRSD001"
        ctx.step()

    _worker(db, settings, gui, {queue.READ_ZRSD001: Transaction(read, False)}).run_once()
    job = _job(db, job.id)
    assert job.status == queue.FAILED and job.evidence_path
    assert gui.Parent.closed


def test_someone_elses_session_is_never_logged_off(db, settings, batch):
    request_zrsd001(db, QA, batch, "admin")
    person = FakeSession(Info("QAS", "300", "ANNA"))
    txn = Transaction(lambda ctx: TransactionResult(), False)
    _worker(db, settings, person, {queue.READ_ZRSD001: txn}).run_once()
    assert not person.Parent.closed


# ---------------------------------------------------------------- "No data to display"


def _no_data(ctx: JobContext) -> TransactionResult:
    raise NoReportData("ZRSD004: SAP không có dữ liệu với bộ lọc này")


def _failures(db) -> int:
    db.expire_all()
    return queue.control(db).consecutive_failures


def test_zrsd004_without_data_is_done_and_neutral(db, settings, batch):
    job = request_zrsd004(db, QA, batch.platform, batch.gi_date, "admin")
    worker = _worker(
        db, settings, _qa_session(), {queue.READ_ZRSD004: Transaction(_no_data, False)}
    )

    assert worker.run_once() is True

    job = _job(db, job.id)
    assert job.status == queue.DONE and job.import_batch_id is None and job.error is None
    result = queue.result_of(job)
    assert result["no_data"] is True and result["rows"] == 0 and result["delivered"] == 0
    assert _failures(db) == 0


def test_no_data_neither_counts_nor_clears_failures(db, settings, batch):
    queue.control(db).consecutive_failures = 1
    db.flush()
    worker = _worker(
        db, settings, _qa_session(), {queue.READ_ZRSD004: Transaction(_no_data, False)}
    )
    for day in range(11, 14):
        request_zrsd004(db, QA, batch.platform, date(2026, 11, day), "admin")
        assert worker.run_once() is True

    assert _failures(db) == 1
    assert not queue.control(db).paused


def test_zrsd001_without_data_is_still_a_failure(db, settings, batch):
    job = request_zrsd001(db, QA, batch, "admin")
    worker = _worker(
        db, settings, _qa_session(), {queue.READ_ZRSD001: Transaction(_no_data, False)}
    )

    worker.run_once()

    job = _job(db, job.id)
    assert job.status == queue.FAILED and "không có dữ liệu" in job.error
    assert _failures(db) == 1
