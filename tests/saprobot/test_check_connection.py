"""The connection check: who gets claimed when, how each failure is named, what is never leaked."""

import json
import logging

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.config import Settings
from shoponline.db.models import EventLog, SapJob
from shoponline.sapjobs import queue, sap_settings
from shoponline.sapjobs.queue import SapTarget
from shoponline.saprobot.errors import SapLogonNotRunning, ScriptingUnavailable
from shoponline.saprobot.screen import Screens
from shoponline.saprobot.session import LoginConfig
from shoponline.saprobot.transactions import check_connection
from shoponline.saprobot.worker import TRANSACTIONS, Transaction, TransactionResult, Worker
from tests.sap_setup import NO_ENV, configure_sap
from tests.saprobot.fake_sap import FakeEngine, FakeSession, Info, engine_with

AEP = SapTarget("AEP", "300")
PASSWORD = "s3cret-pw-9431"
LOGIN = LoginConfig(connection="SAP PROD", user="AL17016", password=PASSWORD)
SCREENS = Screens({"login": {"user": "wnd[0]/usr/user", "password": "wnd[0]/usr/pw"}})
ME = Info("AEP", "300", "AL17016")


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url="unused", secret_key="s" * 40, data_dir=tmp_path / "data")


@pytest.fixture(autouse=True)
def sap_ready(db):
    configure_sap(db, AEP, verified=False, user="AL17016", connection="SAP PROD")


def _factory(db):
    return lambda: Session(
        bind=db.bind, join_transaction_mode="create_savepoint", expire_on_commit=False
    )


def _worker(db, settings, engine, **kw):
    kw.setdefault("login_provider", lambda _db: LOGIN)
    kw.setdefault("transactions", dict(TRANSACTIONS))
    return Worker(
        settings,
        _factory(db),
        engine if callable(engine) else (lambda: engine),
        SCREENS,
        [],
        env=NO_ENV,
        **kw,
    )


def _check(db) -> SapJob:
    return queue.enqueue(db, queue.CHECK_CONNECTION, AEP, queue.CHECK_KEY, {}, "admin")


def _job(db, job_id) -> SapJob:
    db.expire_all()
    return db.get(SapJob, job_id)


def _reason(job) -> str:
    return queue.result_of(job)["reason"]


# ---------------------------------------------------------------- success


def test_check_reports_the_session_and_verifies_the_target(db, settings):
    job = _check(db)
    session = FakeSession(ME)
    assert _worker(db, settings, engine_with(session)).run_once() is True

    job = _job(db, job.id)
    assert job.status == queue.DONE, job.error
    result = queue.result_of(job)
    assert (result["system"], result["client"], result["user"]) == ("AEP", "300", "AL17016")
    assert result["logged_on_at"]
    assert sap_settings.load(db, NO_ENV).target_verified
    assert session.Parent.closed and session.actions == []  # logged off, pressed nothing


def test_check_logs_on_and_off_when_nobody_is_logged_on(db, settings):
    job = _check(db)
    engine = FakeEngine(login_as=ME)
    _worker(db, settings, engine).run_once()
    assert _job(db, job.id).status == queue.DONE
    assert engine.opened == ["SAP PROD"] and engine.connections == []


# ---------------------------------------------------------------- failures, one reason each


def test_scripting_switched_off(db, settings):
    job = _check(db)

    def engine():
        raise ScriptingUnavailable("GetObject failed")

    _worker(db, settings, engine).run_once()
    job = _job(db, job.id)
    assert job.status == queue.FAILED and _reason(job) == "scripting_disabled"
    assert "Enable scripting" in job.error


def test_saplogon_cannot_be_started(db, settings):
    job = _check(db)

    def engine():
        raise SapLogonNotRunning("không thấy saplogon.exe")

    _worker(db, settings, engine).run_once()
    assert _reason(_job(db, job.id)) == "saplogon_not_running"


def test_logon_entry_that_does_not_exist(db, settings):
    class NoEntry(FakeEngine):
        def OpenConnection(self, name, sync):  # noqa: N802
            raise RuntimeError("The system could not be found")

    job = _check(db)
    _worker(db, settings, NoEntry(login_as=ME)).run_once()
    job = _job(db, job.id)
    assert job.status == queue.FAILED and _reason(job) == "connection_not_found"
    assert "tên phải khớp" in job.error


def test_wrong_password_keeps_sap_wording_and_closes_the_logon_window(db, settings, caplog):
    caplog.set_level(logging.DEBUG)
    job = _check(db)
    engine = FakeEngine(login_as=None)  # SAP answers "Name or password is incorrect"
    _worker(db, settings, engine).run_once()

    job = _job(db, job.id)
    assert job.status == queue.FAILED and _reason(job) == "logon_failed"
    assert "Name or password is incorrect" in job.error
    assert job.evidence_path is None  # the logon screen has the password field
    assert engine.connections == []
    assert PASSWORD not in (job.error or "") + (job.result or "") + caplog.text
    assert not sap_settings.load(db, NO_ENV).target_verified


def test_logon_into_another_system(db, settings):
    job = _check(db)
    engine = FakeEngine(login_as=Info("PRD", "100", "AL17016"))
    _worker(db, settings, engine).run_once()
    job = _job(db, job.id)
    assert _reason(job) == "wrong_system" and "PRD/100" in job.error
    assert engine.connections == []  # the robot closes the logon it opened itself


def test_someone_elses_session_is_a_foreign_session(db, settings):
    job = _check(db)
    person = FakeSession(Info("AEP", "300", "ANNA"))
    _worker(db, settings, engine_with(person)).run_once()
    job = _job(db, job.id)
    assert _reason(job) == "foreign_session" and "ANNA" in job.error
    assert not person.Parent.closed


def test_missing_settings_name_the_field_to_fill(db, settings):
    configure_sap(db, AEP, verified=False, user="AL17016", connection="")
    job = _check(db)
    worker = _worker(db, settings, FakeEngine(), login_provider=None)
    worker.run_once()
    job = _job(db, job.id)
    assert _reason(job) == "missing_settings" and "mục SAP Logon" in job.error
    assert "Kết nối SAP" in job.error


def test_missing_password_names_the_command_to_run(db, settings):
    job = _check(db)
    worker = _worker(
        db, settings, FakeEngine(), login_provider=None, read_password=lambda u, e: None
    )
    worker.run_once()
    job = _job(db, job.id)
    assert _reason(job) == "missing_password"
    assert "sap-password set" in job.error and "AL17016" in job.error


def test_stored_password_reaches_the_login_screen_only(db, settings):
    job = _check(db)
    engine = FakeEngine(login_as=ME)
    worker = _worker(db, settings, engine, login_provider=None, read_password=lambda u, e: PASSWORD)
    worker.run_once()
    job = _job(db, job.id)
    assert job.status == queue.DONE
    assert PASSWORD not in json.dumps(queue.result_of(job)) and PASSWORD not in (job.error or "")


# ---------------------------------------------------------------- a check never stops the robot


def test_failed_checks_do_not_count_or_pause(db, settings):
    worker = _worker(db, settings, FakeEngine(login_as=None))
    for _ in range(4):
        _check(db)
        worker.run_once()
        db.expire_all()
    control = queue.control(db)
    assert control.consecutive_failures == 0 and not control.paused


def test_wrong_system_in_a_check_does_not_pause_the_robot(db, settings):
    _check(db)
    _worker(db, settings, FakeEngine(login_as=Info("PRD", "100", "AL17016"))).run_once()
    assert not queue.control(db).paused


# ---------------------------------------------------------------- who gets claimed


def _read_job(db):
    return queue.enqueue(db, queue.READ_ZRSD004, AEP, "k", {}, "admin")


def test_paused_robot_runs_the_check_but_not_the_report_read(db, settings):
    queue.pause(db, "admin", "bảo trì")
    read, check = _read_job(db), _check(db)
    ran = []
    transactions = {
        queue.CHECK_CONNECTION: Transaction(check_connection.run, False),
        queue.READ_ZRSD004: Transaction(lambda ctx: ran.append(1) or TransactionResult(), False),
    }
    worker = _worker(db, settings, engine_with(FakeSession(ME)), transactions=transactions)
    assert worker.run_once() is True
    assert _job(db, check.id).status == queue.DONE
    assert worker.run_once() is False  # still paused: the read waits
    assert _job(db, read.id).status == queue.PENDING and ran == []


def test_unverified_system_only_gets_checks(db, settings):
    read, check = _read_job(db), _check(db)
    worker = _worker(db, settings, engine_with(FakeSession(ME)))
    assert worker.run_once() is True  # the check, though the read was queued first
    assert _job(db, check.id).status == queue.DONE
    assert sap_settings.load(db, NO_ENV).target_verified
    assert _job(db, read.id).status == queue.PENDING


def test_unverified_system_leaves_reads_waiting(db, settings):
    read = _read_job(db)
    engine = FakeEngine(login_as=ME)
    assert _worker(db, settings, engine).run_once() is False
    assert _job(db, read.id).status == queue.PENDING and engine.opened == []


def test_read_for_another_system_fails_without_logging_on(db, settings):
    sap_settings.mark_verified(db, NO_ENV, "AEP", "300")
    read = queue.enqueue(db, queue.READ_ZRSD004, SapTarget("AEP", "400"), "k", {}, "admin")
    engine = FakeEngine(login_as=ME)
    _worker(db, settings, engine).run_once()
    job = _job(db, read.id)
    assert job.status == queue.FAILED and "AEP/400" in job.error and "AEP/300" in job.error
    assert engine.opened == []
    assert queue.control(db).consecutive_failures == 0


def test_a_new_check_replaces_the_one_still_waiting(db):
    first = _check(db)
    assert queue.supersede_checks(db, "admin") == 1
    second = _check(db)  # no DuplicateJob: the old one is closed
    first = _job(db, first.id)
    assert first.status == queue.FAILED and "Thay bằng" in first.error
    assert _job(db, second.id).status == queue.PENDING
    kinds = db.scalars(select(EventLog.kind).where(EventLog.actor == "admin")).all()
    assert "sap_job_failed" in kinds


def test_a_check_cut_off_by_a_robot_restart_is_queued_again(db):
    job = _check(db)
    queue.claim(db)
    queue.requeue_interrupted(db)
    assert _job(db, job.id).status == queue.PENDING


# ---------------------------------------------------------------- heartbeat


def test_heartbeat_reports_host_entries_and_password_presence(db, settings):
    worker = _worker(
        db,
        settings,
        FakeEngine(),
        login_provider=None,
        read_password=lambda u, e: PASSWORD,
        entries_provider=lambda: ["QAS server", "SAP PROD"],
    )
    worker.heartbeat()
    db.expire_all()
    control = queue.control(db)
    assert sap_settings.robot_alive(control)
    assert json.loads(control.saplogon_entries) == ["QAS server", "SAP PROD"]
    assert control.password_present is True and control.robot_host
    assert PASSWORD not in repr(vars(control))


def test_heartbeat_without_a_stored_password_says_so(db, settings):
    worker = _worker(
        db,
        settings,
        FakeEngine(),
        login_provider=None,
        read_password=lambda u, e: None,
        entries_provider=lambda: [],
    )
    worker.heartbeat()
    db.expire_all()
    assert queue.control(db).password_present is False
