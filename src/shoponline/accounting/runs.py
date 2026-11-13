"""Accounting runs: read zrsd004 for every platform and goods issue day that still has orders
waiting, merge the reads into one file, check it against the web's orders, and record the
deliveries as sent.

Callers own the transaction: every function flushes, none commits.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shoponline.accounting import ledger
from shoponline.accounting.ledger import CANCELLED, FINALIZED, OPEN, REVOKED
from shoponline.clock import today_vn
from shoponline.config import Settings
from shoponline.db.models import (
    AccountingRun,
    AccountingRunRead,
    AccountingRunSource,
    AccountingSentDelivery,
    GeneratedFile,
    ImportBatch,
    OrderBatch,
    PlatformSetting,
    SalesOrder,
    SapJob,
)
from shoponline.domain import states
from shoponline.exports.accounting_workbook import (
    MergedAccountingFile,
    build_merged_accounting_workbook,
    preloaded_lookup,
)
from shoponline.importers.excel_table import FileRejected
from shoponline.importers.sap_reports import read_zrsd004
from shoponline.sapjobs import queue
from shoponline.sapjobs.queue import SapTarget
from shoponline.sapjobs.report_requests import request_zrsd004, zrsd004_key
from shoponline.web.uploads import save_generated

# The oldest goods issue day a run reads back to; older waiting orders are only warned about.
LOOKBACK_DAYS = 31
NO_NEW_DO = "Không có DO mới"
ROBOT = "robot"

# Read states of one (platform, day).
READING = "reading"
HAS_DATA = "has_data"
NO_DATA = "no_data"
ERROR = "error"
MISSING_FILE = "missing_file"
NO_JOB = "no_job"
STATE_LABELS = {
    READING: "Đang đọc",
    HAS_DATA: "Xong, có DO",
    NO_DATA: "SAP chưa có DO",
    ERROR: "Lỗi",
    MISSING_FILE: "Thiếu file nguồn",
    NO_JOB: "Chưa có việc",
}
# A pair in one of these states has produced nothing yet, so closing without it is a choice.
INCOMPLETE = (READING, ERROR, MISSING_FILE, NO_JOB)


class NothingDue(ValueError):
    pass


class RunNotOpen(ValueError):
    pass


class StaleReview(ValueError):
    pass


class ReadsIncomplete(ValueError):
    def __init__(self, pairs: list[str]):
        self.pairs = pairs
        super().__init__("Còn chưa có dữ liệu: " + ", ".join(pairs))


class MissingNotAcknowledged(ValueError):
    pass


# ---------------------------------------------------------------- what is waiting


def _pending_orders(session: Session, today: date) -> list[tuple[SalesOrder, date]]:
    """Orders whose DO has not reached accounting: SO linked, or DO read but not yet sent."""
    unsent_do = and_(
        SalesOrder.status == states.DELIVERED,
        SalesOrder.do_number.is_not(None),
        ~exists().where(AccountingSentDelivery.delivery == SalesOrder.do_number),
    )
    rows = session.execute(
        select(SalesOrder, OrderBatch.gi_date)
        .join(OrderBatch, SalesOrder.order_batch_id == OrderBatch.id)
        .where(OrderBatch.gi_date <= today)
        .where(or_(SalesOrder.status == states.SO_LINKED, unsent_do))
        .order_by(OrderBatch.gi_date, SalesOrder.platform, SalesOrder.platform_order_id)
    ).all()
    return [(order, gi) for order, gi in rows]


@dataclass
class DuePairs:
    pairs: list[tuple[str, date]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pending: int = 0


def due_pairs(session: Session, today: date | None = None) -> DuePairs:
    """The (platform, goods issue day) reads a run needs.

    Per platform with waiting orders: every day from the oldest expected goods issue day of those
    orders (at most LOOKBACK_DAYS back) to today. The expected day is the batch's, which may differ
    from the real one, so each day in between is read. Pairs of revoked runs come back until a
    later finalized run holds them.
    """
    today = today or today_vn()
    oldest_allowed = today - timedelta(days=LOOKBACK_DAYS)
    pending = _pending_orders(session, today)
    first_day: dict[str, date] = {}
    too_old: dict[str, int] = defaultdict(int)
    for order, gi in pending:
        first_day[order.platform] = min(gi, first_day.get(order.platform, gi))
        if gi < oldest_allowed:
            too_old[order.platform] += 1
    result = DuePairs(pending=len(pending))
    pairs: set[tuple[str, date]] = set()
    for platform, start in first_day.items():
        day = max(start, oldest_allowed)
        while day <= today:
            pairs.add((platform, day))
            day += timedelta(days=1)
    for platform, count in sorted(too_old.items()):
        result.warnings.append(
            f"{platform}: {count} đơn chờ có ngày goods issue dự kiến trước "
            f"{oldest_allowed:%d/%m/%Y}, ngoài cửa sổ đọc {LOOKBACK_DAYS} ngày. Đọc riêng bằng "
            "form Ra lệnh cho robot ở trang Robot SAP."
        )
    pairs |= _revoked_pairs(session)
    result.pairs = sorted(pairs)
    return result


def _revoked_pairs(session: Session) -> set[tuple[str, date]]:
    revoked = session.execute(
        select(AccountingRunRead.platform, AccountingRunRead.gi_date, AccountingRunRead.run_id)
        .join(AccountingRun, AccountingRun.id == AccountingRunRead.run_id)
        .where(AccountingRun.status == REVOKED)
    ).all()
    if not revoked:
        return set()
    finalized = session.execute(
        select(AccountingRunRead.platform, AccountingRunRead.gi_date, AccountingRunRead.run_id)
        .join(AccountingRun, AccountingRun.id == AccountingRunRead.run_id)
        .where(AccountingRun.status == FINALIZED)
    ).all()
    latest_final: dict[tuple[str, date], int] = {}
    for platform, day, run_id in finalized:
        key = (platform, day)
        latest_final[key] = max(run_id, latest_final.get(key, 0))
    return {
        (platform, day)
        for platform, day, run_id in revoked
        if latest_final.get((platform, day), 0) < run_id
    }


# ---------------------------------------------------------------- start, sync, read again


def open_run(session: Session) -> AccountingRun | None:
    return session.scalar(select(AccountingRun).where(AccountingRun.status == OPEN))


def start_run(
    session: Session,
    target: SapTarget | None,
    actor: str,
    today: date | None = None,
) -> AccountingRun:
    """Open a run, or return the one already open (adding reads that became due since).

    Without a verified target the run still opens, with reads that have no job, so the files can
    be uploaded by hand.
    """
    today = today or today_vn()
    run = open_run(session)
    if run is not None:
        sync_pairs(session, run, actor, target, today)
        if target is not None:  # the run opened while the robot was unavailable
            for status in run_status(session, run):
                if status.state == NO_JOB:
                    status.read.sap_job_id = _queue_job(
                        session, status.read.platform, status.read.gi_date, target, actor
                    ).id
            session.flush()
        return run
    due = due_pairs(session, today)
    if not due.pairs:
        raise NothingDue("Không có đơn nào đang chờ gửi kế toán")
    try:
        with session.begin_nested():
            run = AccountingRun(status=OPEN, created_by=actor)
            session.add(run)
            session.flush()
    except IntegrityError:  # someone opened a run a moment ago; join it, queue nothing twice
        existing = open_run(session)
        if existing is None:
            raise
        return existing
    for platform, day in due.pairs:
        _add_read(session, run, platform, day, target, actor)
    states.log_event(
        session,
        actor,
        "accounting_run_started",
        detail={"run_id": run.id, "pairs": len(due.pairs), "robot": target is not None},
    )
    return run


def sync_pairs(
    session: Session,
    run: AccountingRun,
    actor: str,
    target: SapTarget | None,
    today: date | None = None,
) -> int:
    """Add the reads that became due after the run opened. Returns how many were added."""
    if run.status != OPEN:
        return 0
    have = {
        (r.platform, r.gi_date)
        for r in session.scalars(
            select(AccountingRunRead).where(AccountingRunRead.run_id == run.id)
        )
    }
    added = 0
    for platform, day in due_pairs(session, today).pairs:
        if (platform, day) not in have:
            _add_read(session, run, platform, day, target, actor)
            added += 1
    return added


def _add_read(
    session: Session,
    run: AccountingRun,
    platform: str,
    day: date,
    target: SapTarget | None,
    actor: str,
) -> AccountingRunRead:
    read = AccountingRunRead(run_id=run.id, platform=platform, gi_date=day)
    session.add(read)
    if target is not None:
        read.sap_job_id = _queue_job(session, platform, day, target, actor).id
    session.flush()
    return read


def _queue_job(session: Session, platform: str, day: date, target: SapTarget, actor: str) -> SapJob:
    """Queue the read, or take the job already open for it when that one can still do the work.

    An open job is taken only when it is waiting or running for this very target. Any other open
    job (unknown outcome, needs review, aimed at another system) is closed so a stale one never
    blocks or answers for the new run.
    """
    try:
        return request_zrsd004(session, target, platform, day, actor)
    except queue.DuplicateJob:
        pass
    key = zrsd004_key(platform, day)
    old = session.scalar(
        select(SapJob).where(SapJob.dedupe_key == key, SapJob.status.in_(queue.ACTIVE_STATUSES))
    )
    if old is not None:
        if old.status == queue.RUNNING or (
            old.status == queue.PENDING and queue.target_of(old) == target
        ):
            return old
        queue.close_waiting(session, old, "Thay bằng việc của đợt gửi kế toán", actor)
    return request_zrsd004(session, target, platform, day, actor)


def retry_read(
    session: Session,
    run: AccountingRun,
    read: AccountingRunRead,
    actor: str,
    target: SapTarget,
) -> SapJob:
    """Read the pair again: a failed job goes back to the queue, a finished one is replaced."""
    if run.status != OPEN or read.run_id != run.id:
        raise RunNotOpen("Đợt này không còn mở")
    job = session.get(SapJob, read.sap_job_id) if read.sap_job_id else None
    if job is not None and job.status in (queue.PENDING, queue.RUNNING):
        raise queue.JobStateError(f"Việc #{job.id} đang chờ hoặc đang chạy")
    if (
        job is not None
        and job.status in (queue.FAILED, queue.UNKNOWN, queue.NEED_REVIEW)
        and queue.target_of(job) == target
    ):
        queue.retry(session, job, actor)
        return job
    job = _queue_job(session, read.platform, read.gi_date, target, actor)
    read.sap_job_id = job.id
    session.flush()
    return job


def available_uploads(session: Session) -> list[ImportBatch]:
    """zrsd004 files uploaded by hand since the last finalized run that no open or finalized run
    holds yet."""
    last = session.scalar(
        select(AccountingRun.finalized_at)
        .where(AccountingRun.status == FINALIZED)
        .order_by(AccountingRun.finalized_at.desc())
        .limit(1)
    )
    held = (
        select(AccountingRunSource.import_batch_id)
        .join(AccountingRun, AccountingRun.id == AccountingRunSource.run_id)
        .where(AccountingRun.status.in_((OPEN, FINALIZED)))
    )
    stmt = (
        select(ImportBatch)
        .where(
            ImportBatch.kind == "zrsd004",
            ImportBatch.imported_by != ROBOT,
            ImportBatch.id.not_in(held),
        )
        .order_by(ImportBatch.id.desc())
    )
    if last is not None:
        stmt = stmt.where(ImportBatch.imported_at > last)
    return [b for b in session.scalars(stmt) if Path(b.stored_path).is_file()]


def attach_upload(session: Session, run: AccountingRun, batch: ImportBatch, actor: str) -> None:
    """Hold an uploaded zrsd004 file in the run. Only called from the run page."""
    if run.status != OPEN:
        raise RunNotOpen("Đợt này không còn mở")
    if batch.kind != "zrsd004":
        raise FileRejected("Đây không phải file zrsd004")
    rows = read_zrsd004(Path(batch.stored_path))
    coverage = sorted(
        {f"{r.sold_to}|{r.gi_date.isoformat()}" for r in rows if r.gi_date is not None}
    )
    link = session.get(AccountingRunSource, (run.id, batch.id))
    if link is None:
        link = AccountingRunSource(run_id=run.id, import_batch_id=batch.id)
        session.add(link)
    link.coverage = json.dumps(coverage)
    session.flush()
    states.log_event(
        session,
        actor,
        "accounting_source_attached",
        detail={"run_id": run.id, "import_batch_id": batch.id, "rows": len(rows)},
    )


# ---------------------------------------------------------------- progress


@dataclass
class PairStatus:
    read: AccountingRunRead
    state: str
    detail: str = ""
    job_id: int | None = None

    @property
    def label(self) -> str:
        return STATE_LABELS[self.state]

    @property
    def name(self) -> str:
        return f"{self.read.platform} {self.read.gi_date:%d/%m/%Y}"


def run_status(session: Session, run: AccountingRun) -> list[PairStatus]:
    """State of every read of the run. Cheap: reads rows only, never opens a workbook."""
    reads = session.scalars(
        select(AccountingRunRead)
        .where(AccountingRunRead.run_id == run.id)
        .order_by(AccountingRunRead.platform, AccountingRunRead.gi_date)
    ).all()
    job_ids = [r.sap_job_id for r in reads if r.sap_job_id]
    jobs = {j.id: j for j in session.scalars(select(SapJob).where(SapJob.id.in_(job_ids)))}
    batch_ids = [j.import_batch_id for j in jobs.values() if j.import_batch_id]
    stored = {
        b.id: b.stored_path
        for b in session.scalars(select(ImportBatch).where(ImportBatch.id.in_(batch_ids)))
    }
    customers = {s.platform: s.sap_customer for s in session.scalars(select(PlatformSetting))}
    covered: set[str] = set()
    for link in session.scalars(
        select(AccountingRunSource).where(AccountingRunSource.run_id == run.id)
    ):
        covered.update(json.loads(link.coverage or "[]"))
    return [_status_of(r, jobs.get(r.sap_job_id), stored, customers, covered) for r in reads]


def _status_of(
    read: AccountingRunRead,
    job: SapJob | None,
    stored: dict[int, str],
    customers: dict[str, str],
    covered: set[str],
) -> PairStatus:
    job_id = job.id if job else None
    if f"{customers.get(read.platform)}|{read.gi_date.isoformat()}" in covered:
        return PairStatus(read, HAS_DATA, "Có file zrsd004 tải lên", job_id)
    if job is None:
        return PairStatus(read, NO_JOB, "Tải zrsd004 lên đợt hoặc bật robot", None)
    if job.status in (queue.PENDING, queue.RUNNING):
        return PairStatus(read, READING, queue.LABELS[job.status], job_id)
    if job.status != queue.DONE:
        return PairStatus(read, ERROR, job.error or queue.LABELS[job.status], job_id)
    if queue.result_of(job).get("no_data"):
        return PairStatus(read, NO_DATA, "", job_id)
    path = stored.get(job.import_batch_id) if job.import_batch_id else None
    if path is None or not Path(path).is_file():
        return PairStatus(read, MISSING_FILE, "File đã bị xóa hoặc không có", job_id)
    return PairStatus(read, HAS_DATA, "", job_id)


# ---------------------------------------------------------------- reconcile


@dataclass(frozen=True)
class MissingOrder:
    platform: str
    order_id: str
    so_number: str
    gi_date: date
    note: str = ""


@dataclass
class Reconciliation:
    merged: MergedAccountingFile | None
    source_ids: list[int]
    statuses: list[PairStatus]
    pending: int
    missing: list[MissingOrder]
    unknown: list[tuple[str, str]]  # (delivery, SO) of deliveries no web order belongs to
    warnings: list[str]
    old_warnings: list[str]
    fingerprint: str

    @property
    def deliveries(self) -> set[str]:
        return self.merged.deliveries if self.merged else set()

    @property
    def dropped(self) -> dict[str, int]:
        return self.merged.dropped if self.merged else {}

    @property
    def incomplete(self) -> list[PairStatus]:
        return [s for s in self.statuses if s.state in INCOMPLETE]

    @property
    def summary(self) -> str:
        return (
            f"Web đáng ra có {self.pending} đơn, file có {len(self.deliveries)} DO, "
            f"thiếu {len(self.missing)}"
        )


def run_sources(session: Session, run: AccountingRun) -> list[ImportBatch]:
    """The zrsd004 files of the run: those the robot read, then those attached by hand."""
    job_ids = session.scalars(
        select(AccountingRunRead.sap_job_id)
        .where(AccountingRunRead.run_id == run.id, AccountingRunRead.sap_job_id.is_not(None))
        .order_by(AccountingRunRead.platform, AccountingRunRead.gi_date)
    ).all()
    robot_ids = []
    for job_id in job_ids:
        job = session.get(SapJob, job_id)
        if job.status == queue.DONE and job.import_batch_id:
            robot_ids.append(job.import_batch_id)
    attached = session.scalars(
        select(AccountingRunSource.import_batch_id)
        .where(AccountingRunSource.run_id == run.id)
        .order_by(AccountingRunSource.import_batch_id)
    ).all()
    ordered: list[int] = []
    for batch_id in [*robot_ids, *attached]:
        if batch_id not in ordered:
            ordered.append(batch_id)
    batches = {
        b.id: b for b in session.scalars(select(ImportBatch).where(ImportBatch.id.in_(ordered)))
    }
    return [batches[i] for i in ordered if Path(batches[i].stored_path).is_file()]


def reconcile(session: Session, run: AccountingRun, today: date | None = None) -> Reconciliation:
    """Build the merged file for the run and compare it with the orders waiting on the web."""
    today = today or today_vn()
    statuses = run_status(session, run)
    batches = run_sources(session, run)
    paths = [Path(b.stored_path) for b in batches]
    so_numbers: set[str] = set()
    for path in paths:
        try:
            so_numbers.update(row.so_number for row in read_zrsd004(path))
        except FileRejected:
            continue  # the build below reports it
    customers = list(session.scalars(select(PlatformSetting.sap_customer)))
    merged: MergedAccountingFile | None
    try:
        merged = build_merged_accounting_workbook(
            paths,
            preloaded_lookup(session, so_numbers),
            exclude_deliveries=ledger.sent_deliveries(session),
            cutoff=ledger.get_cutoff(session),
            today=today,
            platform_sold_to=customers,
        )
    except FileRejected as exc:
        if exc.message != NO_NEW_DO:
            raise
        merged = None

    in_file = merged.so_numbers if merged else set()
    not_issued = {s.so_number for s in merged.skipped} if merged else set()
    pending = _pending_orders(session, today)
    missing = [
        MissingOrder(
            order.platform,
            order.platform_order_id,
            order.so_number or "",
            gi,
            "DO có nhưng SAP chưa goods issue xong" if order.so_number in not_issued else "",
        )
        for order, gi in pending
        if order.so_number not in in_file
    ]
    known = set(
        session.scalars(select(SalesOrder.so_number).where(SalesOrder.so_number.in_(list(in_file))))
    )
    unknown = sorted(
        (delivery, so)
        for delivery, so in (merged.delivery_so.items() if merged else [])
        if so not in known
    )
    due = due_pairs(session, today)
    payload = {
        "sources": sorted(b.id for b in batches),
        "deliveries": sorted(merged.deliveries) if merged else [],
        "incomplete": sorted(f"{s.name}:{s.state}" for s in statuses if s.state in INCOMPLETE),
        "missing": sorted(f"{m.platform}:{m.order_id}:{m.so_number}" for m in missing),
    }
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return Reconciliation(
        merged=merged,
        source_ids=[b.id for b in batches],
        statuses=statuses,
        pending=len(pending),
        missing=missing,
        unknown=unknown,
        warnings=merged.warnings if merged else [],
        old_warnings=due.warnings,
        fingerprint=fingerprint,
    )


@dataclass
class Draft:
    workbook: Workbook
    file_name: str
    fingerprint: str


def draft_file(session: Session, run: AccountingRun, today: date | None = None) -> Draft:
    """The file as it would be finalized now, named with the NHÁP prefix. Nothing is stored."""
    rec = reconcile(session, run, today)
    if rec.merged is None:
        raise FileRejected(NO_NEW_DO)
    return Draft(rec.merged.workbook, f"NHÁP {rec.merged.file_name}", rec.fingerprint)


# ---------------------------------------------------------------- finalize and cancel


def finalize(
    session: Session,
    settings: Settings,
    run_id: int,
    actor: str,
    fingerprint: str,
    *,
    allow_partial: bool,
    ack_missing: bool,
    today: date | None = None,
) -> GeneratedFile:
    """Save the file, record its deliveries as sent and close the run, in one transaction.

    Refused when the run is no longer open, when the data changed since the reviewed draft, when
    reads are incomplete and not accepted, or when orders without a DO are not acknowledged.
    """
    run = session.scalar(
        select(AccountingRun)
        .where(AccountingRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if run is None or run.status != OPEN:
        raise RunNotOpen("Đợt này không còn mở (đã chốt, hủy hoặc gỡ)")
    rec = reconcile(session, run, today)
    if rec.fingerprint != fingerprint:
        raise StaleReview("Dữ liệu đã đổi, xem lại bản nháp")
    lacking = [f"{s.name} ({s.label})" for s in rec.incomplete]
    if lacking and not allow_partial:
        raise ReadsIncomplete(lacking)
    if rec.missing and not ack_missing:
        raise MissingNotAcknowledged(
            "Còn đơn chưa thấy DO trong file, cần xác nhận đã xem danh sách"
        )
    if rec.merged is None:
        raise FileRejected(NO_NEW_DO)

    record = save_generated(
        session, settings, rec.merged.workbook, rec.merged.file_name, "accounting_file", actor
    )
    try:
        run.generated_file_id = record.id
        session.add_all(
            AccountingSentDelivery(delivery=d, run_id=run.id) for d in sorted(rec.merged.deliveries)
        )
        run.status = FINALIZED
        run.finalized_by = actor
        run.finalized_at = datetime.now().astimezone()
        orders = [f"{m.platform} {m.order_id}" for m in rec.missing]
        run.missing_note = (
            json.dumps({"pairs": lacking, "orders": orders}, ensure_ascii=False)
            if lacking or orders
            else None
        )
        session.flush()
        states.log_event(
            session,
            actor,
            "accounting_run_finalized",
            detail={
                "run_id": run.id,
                "deliveries": len(rec.merged.deliveries),
                "missing_pairs": lacking,
                "missing_orders": orders,
                "unknown": [f"{delivery}/{so}" for delivery, so in rec.unknown],
                "dropped": rec.merged.dropped,
            },
        )
        session.flush()
    except Exception:
        Path(record.stored_path).unlink(missing_ok=True)
        raise
    return record


def cancel_run(session: Session, run_id: int, actor: str) -> None:
    """Close an open run without touching the ledger. Reads already queued keep running."""
    run = session.scalar(
        select(AccountingRun)
        .where(AccountingRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if run is None or run.status != OPEN:
        raise RunNotOpen("Đợt này không còn mở")
    run.status = CANCELLED
    session.flush()
    states.log_event(session, actor, "accounting_run_cancelled", detail={"run_id": run_id})


revoke_run = ledger.revoke_run
