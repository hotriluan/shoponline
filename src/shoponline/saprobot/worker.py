"""Robot loop: stop switch → claim → log in / check target system → wrap in the T-code guard →
run → log off → record outcome. Between jobs the robot holds no SAP logon.

One robot per database: the worker holds a PostgreSQL advisory lock for its whole life.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Connection, Engine, text
from sqlalchemy.orm import Session

from shoponline.config import Settings
from shoponline.db.models import OrderBatch, SapJob
from shoponline.domain import states
from shoponline.reconcile.report_ingest import ingest_zrsd001, ingest_zrsd004
from shoponline.sapjobs import queue
from shoponline.saprobot import evidence
from shoponline.saprobot.desktop import SaveDialogs, WindowsDesktop
from shoponline.saprobot.errors import GuardViolation, RobotError, UnknownPopup, WrongSystem
from shoponline.saprobot.guard import GuardedSession
from shoponline.saprobot.popups import PopupRule, SeenPopup, handle_popups
from shoponline.saprobot.screen import Screens
from shoponline.saprobot.session import LoginConfig, ensure_session, logoff
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


class Worker:
    def __init__(
        self,
        settings: Settings,
        session_factory: Callable[[], Session],
        engine_provider: Callable[[], object],
        login: LoginConfig,
        screens: Screens,
        popups: list[PopupRule],
        transactions: dict[str, Transaction] | None = None,
        desktop: SaveDialogs | None = None,
    ):
        self.settings = settings
        self.session_factory = session_factory
        self.engine_provider = engine_provider
        self.login = login
        self.screens = screens
        self.popups = popups
        self.transactions = TRANSACTIONS if transactions is None else transactions
        self.desktop = desktop or WindowsDesktop()

    def run_once(self) -> bool:
        """Process at most one job. Returns False when paused or nothing is pending."""
        with self.session_factory() as db:
            if queue.control(db).paused:
                return False
            job = queue.claim(db)
            db.commit()
            if job is None:
                return False
            job_id, kind, payload = job.id, job.kind, queue.payload_of(job)
            target = queue.target_of(job)
        log.info("Bắt đầu việc #%s %s trên %s", job_id, kind, target)

        txn = self.transactions.get(kind)
        out: TransactionResult | None = None
        raw = gui = None
        try:
            if txn is None:
                raise RobotError(f"Chưa có thao tác SAP cho loại việc {kind}")
            raw, _ = ensure_session(
                self.engine_provider(), target, self.login, self.screens, self.popups
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
            queue.record_outcome(db, outcome.status == queue.DONE, self.settings.robot_max_failures)
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
    poll_seconds: float = 10.0,
    on_start: Callable[[], None] | None = None,
) -> None:
    """on_start runs once after the single-robot lock is taken (a second robot never gets here)."""
    lock = acquire_single_robot_lock(engine)
    try:
        if on_start is not None:
            on_start()
        with worker.session_factory() as db:
            interrupted = queue.requeue_interrupted(db)
            db.commit()
        if interrupted:
            log.warning("%d việc bị cắt ngang lần chạy trước đã được xử lý lại", len(interrupted))
        evidence.prune(worker.settings.evidence_dir, worker.settings.evidence_keep_days)
        log.info("Robot bắt đầu; Ctrl+C để dừng")
        while True:
            try:
                busy = worker.run_once()
            except Exception:  # database down or similar: wait and try again
                log.exception("Vòng robot lỗi")
                busy = False
            if not busy:
                time.sleep(poll_seconds)
    finally:
        lock.close()
