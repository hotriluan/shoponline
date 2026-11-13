"""Robot loop: stop switch → claim → log in / check target system → wrap in the T-code guard →
run → log off → record outcome. Between jobs the robot holds no SAP logon.

One robot per database: the worker holds a PostgreSQL advisory lock for its whole life.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Connection, Engine, text
from sqlalchemy.orm import Session

from shoponline.config import Settings
from shoponline.db.models import OrderBatch, SapJob
from shoponline.domain import states
from shoponline.reconcile.report_ingest import ingest_zrsd001, ingest_zrsd004
from shoponline.sapjobs import queue, sap_settings
from shoponline.saprobot import credentials, evidence
from shoponline.saprobot.desktop import SaveDialogs, WindowsDesktop
from shoponline.saprobot.errors import (
    ConnectionNotFound,
    ForeignSession,
    GuardViolation,
    LoginUnavailable,
    LogonFailed,
    RobotError,
    SapLogonNotRunning,
    ScriptingUnavailable,
    UnknownPopup,
    WrongSystem,
)
from shoponline.saprobot.guard import GuardedSession
from shoponline.saprobot.popups import PopupRule, SeenPopup, handle_popups
from shoponline.saprobot.saplogon_entries import EntriesReader
from shoponline.saprobot.screen import Screens
from shoponline.saprobot.session import Identity, LoginConfig, ensure_session, logoff
from shoponline.saprobot.statusbar import StatusMessage, check_status
from shoponline.web.uploads import store_file

log = logging.getLogger(__name__)

ROBOT = "robot"
ADVISORY_LOCK_KEY = 0x5A9_0B07  # any fixed number; only the robot takes it


@dataclass
class JobContext:
    """What a transaction gets: the guarded SAP session, screen IDs, popup rules, a work folder.

    Transactions never see the raw SAP session; every action goes through the T-code guard.
    """

    job_id: int
    payload: dict
    gui: GuardedSession
    screens: Screens
    popups: list[PopupRule]
    work_dir: Path
    desktop: SaveDialogs = field(default_factory=WindowsDesktop)
    seen_popups: list[SeenPopup] = field(default_factory=list)
    identity: Identity | None = None  # who is logged on in gui
    gui_version: str = ""

    def step(self) -> StatusMessage:
        """Call after every action: answer known popups, then fail on an error message."""
        self.seen_popups.extend(handle_popups(self.gui, self.popups))
        return check_status(self.gui)


@dataclass
class TransactionResult:
    file: Path | None = None  # report exported by SAP, read by the phase 4 importers
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Transaction:
    run: Callable[[JobContext], TransactionResult]
    writes: bool  # True: an interruption leaves the job UNKNOWN, never FAILED


# Filled by shoponline.saprobot.transactions as recorded SAP steps become available.
TRANSACTIONS: dict[str, Transaction] = {}


# ---------------------------------------------------------------- after a report was read


def _stored_report(settings: Settings, out: TransactionResult, kind: str):
    if out.file is None or not out.file.is_file():
        raise RobotError(f"Thao tác {kind} không trả về file báo cáo")
    return store_file(
        settings, out.file.read_bytes(), out.file.name, kind=kind, platform=None, actor=ROBOT
    )


def _after_zrsd001(db: Session, job: SapJob, out: TransactionResult, settings: Settings) -> dict:
    record = _stored_report(settings, out, "zrsd001")
    batch_id = queue.payload_of(job).get("batch_id")
    batch = db.get(OrderBatch, batch_id) if batch_id else None
    result = ingest_zrsd001(db, record, ROBOT, expect_batch=batch)
    job.import_batch_id = record.id
    return {
        "new": result.new,
        "updated": result.updated,
        "unchanged": result.unchanged,
        "linked": len(result.linked),
        "warnings": result.warnings,
    }


def _after_zrsd004(db: Session, job: SapJob, out: TransactionResult, settings: Settings) -> dict:
    record = _stored_report(settings, out, "zrsd004")
    imported = ingest_zrsd004(db, record, ROBOT)
    job.import_batch_id = record.id
    return {
        "rows": len(imported.rows),
        "delivered": imported.delivered,
        "warnings": imported.preview.warnings,
    }


AFTER: dict[str, Callable[[Session, SapJob, TransactionResult, Settings], dict]] = {
    queue.READ_ZRSD001: _after_zrsd001,
    queue.READ_ZRSD004: _after_zrsd004,
}


# ---------------------------------------------------------------- worker


@dataclass
class Outcome:
    status: str
    error: str | None = None
    evidence: Path | None = None
    pause_reason: str | None = None
    pause_event: str = "robot_wrong_system"


CHECK_ONLY = frozenset({queue.CHECK_CONNECTION})


def _gui_version(engine) -> str:
    try:
        return f"{engine.MajorVersion}.{engine.MinorVersion}.{engine.Revision}"
    except Exception:  # not every engine exposes it
        return ""


def check_failure(exc: Exception) -> tuple[str, str]:
    """A reason code and a Vietnamese message with the way to fix it, for a failed check."""
    detail = str(exc)
    if isinstance(exc, LoginUnavailable):
        return exc.reason, detail
    if isinstance(exc, SapLogonNotRunning):
        return exc.reason, f"Không mở được SAP Logon trên máy robot. {detail}"
    if isinstance(exc, ScriptingUnavailable):
        return exc.reason, (
            "SAP Logon chưa chạy hoặc chưa bật scripting. Mở SAP Logon, vào Options > "
            "Accessibility & Scripting > Scripting, bật Enable scripting. "
            f"Chi tiết: {detail}"
        )
    if isinstance(exc, ConnectionNotFound):
        return exc.reason, (
            "Không mở được mục SAP Logon đã chọn. Chọn lại đúng tên mục trong danh sách "
            f"(tên phải khớp từng ký tự). Chi tiết: {detail}"
        )
    if isinstance(exc, LogonFailed):
        return exc.reason, (
            f"{detail}. Kiểm tra user SAP và mật khẩu đã đặt trên máy robot "
            "(sai nhiều lần sẽ khóa user)."
        )
    if isinstance(exc, ForeignSession):
        return exc.reason, (
            f"{detail}. Có phiên SAP khác đang mở trên máy robot; đóng phiên đó rồi kiểm tra lại. "
            "Robot không đăng nhập cạnh phiên của người khác."
        )
    if isinstance(exc, WrongSystem):
        return "wrong_system", (
            f"{detail}. Mục SAP Logon đã chọn trỏ tới hệ thống khác với cấu hình; "
            "chọn mục đúng hoặc sửa hệ thống và client."
        )
    if isinstance(exc, GuardViolation):
        return "guard_violation", detail
    if isinstance(exc, UnknownPopup):
        return "unknown_popup", f"SAP hiện hộp thoại chưa biết cách xử lý: {detail}"
    return "error", f"{type(exc).__name__}: {detail}"


class Worker:
    def __init__(
        self,
        settings: Settings,
        session_factory: Callable[[], Session],
        engine_provider: Callable[[], object],
        screens: Screens,
        popups: list[PopupRule],
        *,
        transactions: dict[str, Transaction] | None = None,
        desktop: SaveDialogs | None = None,
        env: Mapping[str, str] | None = None,
        login_provider: Callable[[Session], LoginConfig] | None = None,
        read_password: Callable[[str, Mapping[str, str]], str | None] = credentials.read_password,
        entries_provider: Callable[[], list[str]] | None = None,
    ):
        self.settings = settings
        self.session_factory = session_factory
        self.engine_provider = engine_provider
        self.screens = screens
        self.popups = popups
        self.transactions = TRANSACTIONS if transactions is None else transactions
        self.desktop = desktop or WindowsDesktop()
        self.env = os.environ if env is None else env
        self.read_password = read_password
        self.login_provider = login_provider or self._login_from_settings
        self.entries_provider = entries_provider or EntriesReader().read

    # ---------------------------------------------------------------- configuration

    def _login_from_settings(self, db: Session) -> LoginConfig:
        config = sap_settings.load(db, self.env)
        required = (("mục SAP Logon", config.connection), ("user SAP", config.sap_user))
        missing = [label for label, value in required if not value]
        if missing:
            raise LoginUnavailable(
                "Thiếu cấu hình SAP: " + ", ".join(missing) + ". Điền ở trang Kết nối SAP.",
                "missing_settings",
            )
        password = self.read_password(config.sap_user, self.env)
        if not password:
            raise LoginUnavailable(
                f"Chưa có mật khẩu cho user {config.sap_user} trên máy robot. Chạy "
                "'uv run shoponline sap-password set' dưới tài khoản Windows chạy robot.",
                "missing_password",
            )
        return LoginConfig(config.connection, config.sap_user, password, config.language)

    def _login_config(self) -> LoginConfig:
        with self.session_factory() as db:
            return self.login_provider(db)

    def heartbeat(self) -> None:
        """Tell the web the robot is alive, whether it has a password, and what SAP Logon offers."""
        entries = self.entries_provider()
        with self.session_factory() as db:
            config = sap_settings.load(db, self.env)
            row = queue.control(db)
            row.last_seen_at = datetime.now(UTC)
            row.robot_host = socket.gethostname()[:100]
            row.saplogon_entries = json.dumps(entries, ensure_ascii=False)
            row.password_present = (
                self.read_password(config.sap_user, self.env) is not None
                if config.sap_user
                else None
            )
            db.commit()

    # ---------------------------------------------------------------- one job

    def run_once(self) -> bool:
        """Process at most one job. Returns False when nothing can be claimed.

        While the robot is paused, or the configured system has no successful connection check
        yet, only connection checks are claimed.
        """
        with self.session_factory() as db:
            config = sap_settings.load(db, self.env)
            checks_only = queue.control(db).paused or not config.target_verified
            job = queue.claim(db, CHECK_ONLY if checks_only else None)
            if (
                job is not None
                and job.kind != queue.CHECK_CONNECTION
                and queue.target_of(job) != config.target
            ):
                queue.fail(
                    db,
                    job,
                    f"Việc nhắm {queue.target_of(job)} nhưng cấu hình SAP hiện là "
                    f"{config.target or 'chưa đặt'}; xếp lại việc sau khi kiểm tra kết nối.",
                )
                db.commit()
                return True
            db.commit()
            if job is None:
                return False
            job_id, kind, payload = job.id, job.kind, queue.payload_of(job)
            target = queue.target_of(job)
        log.info("Bắt đầu việc #%s %s trên %s", job_id, kind, target)
        if kind == queue.CHECK_CONNECTION:
            self._run_check(job_id, target)
            return True

        txn = self.transactions.get(kind)
        out: TransactionResult | None = None
        raw = gui = None
        try:
            if txn is None:
                raise RobotError(f"Chưa có thao tác SAP cho loại việc {kind}")
            raw, _ = ensure_session(
                self.engine_provider(), target, self._login_config(), self.screens, self.popups
            )
            gui = GuardedSession(raw)
            gui.check()  # a session left on a foreign T-code stops the job before any action
            ctx = JobContext(
                job_id=job_id,
                payload=payload,
                gui=gui,
                screens=self.screens,
                popups=self.popups,
                work_dir=self.settings.robot_work_dir / f"job-{job_id}",
                desktop=self.desktop,
            )
            ctx.work_dir.mkdir(parents=True, exist_ok=True)
            out = txn.run(ctx)
            outcome = Outcome(queue.DONE)
        except WrongSystem as exc:
            outcome = Outcome(queue.FAILED, str(exc), pause_reason=f"Sai hệ thống SAP: {exc}")
        except GuardViolation as exc:
            outcome = Outcome(
                queue.FAILED,
                str(exc),
                self._capture(gui or exc.session, job_id),
                pause_reason=str(exc),
                pause_event="robot_guard_violation",
            )
        except UnknownPopup as exc:
            outcome = Outcome(queue.NEED_REVIEW, str(exc), self._capture(gui, job_id))
        except Exception as exc:
            status = queue.UNKNOWN if txn is not None and txn.writes else queue.FAILED
            outcome = Outcome(status, f"{type(exc).__name__}: {exc}", self._capture(gui, job_id))
        if raw is not None:
            # Only a session of the robot user ever gets here (ensure_session checked it);
            # the screenshot above is taken first. The next job logs in again.
            logoff(raw)
        self._finish(job_id, outcome, out)
        return True

    def _capture(self, gui: GuardedSession | None, job_id: int) -> Path | None:
        return evidence.capture(gui, self.settings.evidence_dir, job_id) if gui else None

    # ---------------------------------------------------------------- connection check

    def _run_check(self, job_id: int, target: queue.SapTarget) -> None:
        """Log on, report who is logged on, log off.

        A check always ends DONE or FAILED. It never pauses the robot and never counts as a
        failed job, so a wrong password cannot stop report reads. No screenshot is taken before
        a session exists: the logon screen has the password field.
        """
        raw = gui = None
        try:
            txn = self.transactions.get(queue.CHECK_CONNECTION)
            if txn is None:
                raise RobotError("Chưa có thao tác kiểm tra kết nối")
            engine = self.engine_provider()
            raw, who = ensure_session(
                engine, target, self._login_config(), self.screens, self.popups
            )
            gui = GuardedSession(raw)
            gui.check()
            ctx = JobContext(
                job_id=job_id,
                payload={},
                gui=gui,
                screens=self.screens,
                popups=self.popups,
                work_dir=self.settings.robot_work_dir / f"job-{job_id}",
                desktop=self.desktop,
                identity=who,
                gui_version=_gui_version(engine),
            )
            data = txn.run(ctx).data
            failure = None
        except Exception as exc:
            data = None
            failure = (*check_failure(exc), self._capture(gui, job_id))
        if raw is not None:
            logoff(raw)
        with self.session_factory() as db:
            job = db.get(SapJob, job_id)
            if failure is None:
                queue.complete(db, job, data)
                sap_settings.mark_verified(db, self.env, data["system"], data["client"])
            else:
                reason, message, proof = failure
                queue.fail(
                    db, job, message, str(proof) if proof else None, result={"reason": reason}
                )
            db.commit()
        log.info("Việc #%s: kiểm tra kết nối %s", job_id, "xong" if not failure else failure[0])

    def _finish(self, job_id: int, outcome: Outcome, out: TransactionResult | None) -> None:
        with self.session_factory() as db:
            job = db.get(SapJob, job_id)
            if outcome.status == queue.DONE:
                try:
                    after = AFTER.get(job.kind)
                    result = after(db, job, out, self.settings) if after else dict(out.data)
                    queue.complete(db, job, result)
                except Exception as exc:  # a bad result must not leave the job RUNNING
                    log.exception("Việc #%s: không nhập được kết quả", job_id)
                    db.rollback()
                    job = db.get(SapJob, job_id)
                    outcome = Outcome(queue.FAILED, f"Không nhập được kết quả: {exc}")
            proof = str(outcome.evidence) if outcome.evidence else None
            if outcome.status == queue.FAILED:
                queue.fail(db, job, outcome.error, proof)
            elif outcome.status == queue.UNKNOWN:
                queue.mark_unknown(db, job, outcome.error, proof)
            elif outcome.status == queue.NEED_REVIEW:
                queue.need_review(db, job, outcome.error, proof)
            if outcome.pause_reason:
                queue.pause(db, ROBOT, outcome.pause_reason)
                states.log_event(db, ROBOT, outcome.pause_event, detail={"job_id": job_id})
            max_failures = sap_settings.load(db, self.env).max_failures
            queue.record_outcome(db, outcome.status == queue.DONE, max_failures)
            db.commit()
        log.info("Việc #%s: %s %s", job_id, outcome.status, outcome.error or "")


class RobotAlreadyRunning(RuntimeError):
    pass


def acquire_single_robot_lock(engine: Engine) -> Connection:
    """Keep the returned connection open while the robot runs; closing it releases the lock."""
    connection = engine.connect()
    got = connection.execute(
        text("SELECT pg_try_advisory_lock(:key)"), {"key": ADVISORY_LOCK_KEY}
    ).scalar()
    connection.commit()
    if not got:
        connection.close()
        raise RobotAlreadyRunning("Đã có một robot khác đang chạy với database này")
    return connection


def run_forever(
    worker: Worker,
    engine: Engine,
    poll_seconds: float = 5.0,
    on_start: Callable[[], None] | None = None,
) -> None:
    """on_start runs once after the single-robot lock is taken (a second robot never gets here)."""
    lock = acquire_single_robot_lock(engine)
    try:
        if on_start is not None:
            on_start()
        with worker.session_factory() as db:
            interrupted = queue.requeue_interrupted(db)
            keep_days = sap_settings.load(db, worker.env).evidence_keep_days
            db.commit()
        if interrupted:
            log.warning("%d việc bị cắt ngang lần chạy trước đã được xử lý lại", len(interrupted))
        evidence.prune(worker.settings.evidence_dir, keep_days)
        log.info("Robot bắt đầu; Ctrl+C để dừng")
        while True:
            try:
                worker.heartbeat()
            except Exception:  # a missed heartbeat must not stop the jobs
                log.exception("Không ghi được heartbeat")
            try:
                busy = worker.run_once()
            except Exception:  # database down or similar: wait and try again
                log.exception("Vòng robot lỗi")
                busy = False
            if not busy:
                time.sleep(poll_seconds)
    finally:
        lock.close()
