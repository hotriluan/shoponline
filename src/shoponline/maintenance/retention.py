"""Delete stored files once nothing needs them, and customer data older than the retention period.

Files. One set of keep rules (kept_files) serves both the deletion at the moment a file is spent
(discard_unused, called by the web and the robot) and the nightly sweep (sweep_files), which
removes whatever is left over:

- uploads/: the zrsd004 files of a run that is still open (attached by hand, or read by the
  robot), and zrsd004 files uploaded by hand that still wait to be attached to a run, for at most
  retention_days. Platform files, mapping tables and zrsd001 are read once, at import.
- exports/: an accounting file a run points to, and a Shop Online history file that still holds
  an order not yet confirmed as pasted. Order files are deleted as soon as they are sent.
- robot-work/job-N: kept only while the job is not DONE, for at most evidence_keep_days.
- robot-evidence/: screenshots, for evidence_keep_days (saprobot.evidence.prune).

The sweep leaves files younger than an hour alone: a file may be written before the row that
keeps it is committed. A file that cannot be deleted is logged and left for the next sweep.

Customer data. Orders themselves stay (platform order id, SKU lines, SO and DO numbers): they
hold no personal data and keep re-imports idempotent. customer_info rows (name, address)
untouched for retention_days go, unless the order is still needed: its DO has not yet been
recorded as sent to accounting (accounting_sent_delivery), or it has not yet been confirmed as
pasted into the Shop Online history file (sales_history_exported), which carries the customer
name. Cancelled orders and rows typed in by hand for an order id with no sales_order go by age
alone.
"""

from __future__ import annotations

import logging
import re
import shutil
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from shoponline.accounting import runs
from shoponline.config import Settings
from shoponline.db.models import (
    AccountingRun,
    AccountingRunRead,
    AccountingRunSource,
    AccountingSentDelivery,
    CustomerInfo,
    GeneratedFile,
    ImportBatch,
    SalesHistoryExported,
    SalesHistoryFileOrder,
    SalesOrder,
    SapJob,
)
from shoponline.domain import states
from shoponline.sapjobs import queue
from shoponline.saprobot import evidence

log = logging.getLogger(__name__)

GRACE = timedelta(hours=1)
JOB_DIR = re.compile(r"job-(\d+)")


# ---------------------------------------------------------------- customer data


@dataclass
class RetentionPlan:
    cutoff: datetime
    customer_ids: list[int] = field(default_factory=list)
    customer_orders: list[tuple[str, str]] = field(default_factory=list)  # (platform, order id)
    held_orders: list[tuple[str, str]] = field(default_factory=list)  # expired but unfinished


def find_expired(
    session: Session, settings: Settings, now: datetime | None = None
) -> RetentionPlan:
    now = now or datetime.now(UTC)
    plan = RetentionPlan(cutoff=now - timedelta(days=settings.retention_days))
    rows = session.execute(
        select(
            CustomerInfo.id,
            CustomerInfo.platform,
            CustomerInfo.platform_order_id,
            SalesOrder.status,
            AccountingSentDelivery.delivery,
            SalesHistoryExported.sales_order_id,
        )
        .outerjoin(
            SalesOrder,
            and_(
                SalesOrder.platform == CustomerInfo.platform,
                SalesOrder.platform_order_id == CustomerInfo.platform_order_id,
            ),
        )
        .outerjoin(AccountingSentDelivery, AccountingSentDelivery.delivery == SalesOrder.do_number)
        .outerjoin(SalesHistoryExported, SalesHistoryExported.sales_order_id == SalesOrder.id)
        .where(CustomerInfo.updated_at < plan.cutoff)
        .order_by(CustomerInfo.platform, CustomerInfo.platform_order_id)
    ).all()
    for info_id, platform, order_id, status, sent, exported in rows:
        finished = sent is not None and exported is not None
        if status is None or status == states.CANCELLED or finished:
            plan.customer_ids.append(info_id)
            plan.customer_orders.append((platform, order_id))
        else:
            plan.held_orders.append((platform, order_id))
    return plan


def apply(session: Session, plan: RetentionPlan, actor: str) -> None:
    """Delete the expired customer rows and log the purge. The caller commits."""
    if plan.customer_ids:
        session.execute(delete(CustomerInfo).where(CustomerInfo.id.in_(plan.customer_ids)))
    states.log_event(
        session,
        actor,
        "retention_purge",
        detail={
            "cutoff": plan.cutoff.isoformat(),
            "customers": len(plan.customer_ids),
            "held": len(plan.held_orders),
        },
    )


# ---------------------------------------------------------------- files


def kept_files(session: Session, settings: Settings, now: datetime | None = None) -> set[Path]:
    """Files under uploads/ and exports/ that something still needs (see the module doc)."""
    now = now or datetime.now(UTC)
    open_run = select(AccountingRun.id).where(AccountingRun.status == runs.OPEN)
    attached = select(ImportBatch.stored_path).join(
        AccountingRunSource,
        and_(
            AccountingRunSource.import_batch_id == ImportBatch.id,
            AccountingRunSource.run_id.in_(open_run),
        ),
    )
    read = (
        select(ImportBatch.stored_path)
        .join(SapJob, SapJob.import_batch_id == ImportBatch.id)
        .join(
            AccountingRunRead,
            and_(AccountingRunRead.sap_job_id == SapJob.id, AccountingRunRead.run_id.in_(open_run)),
        )
    )
    waiting = (
        runs.waiting_uploads(session)
        .where(ImportBatch.imported_at >= now - timedelta(days=settings.retention_days))
        .with_only_columns(ImportBatch.stored_path)
    )
    accounting = select(GeneratedFile.stored_path).join(
        AccountingRun, AccountingRun.generated_file_id == GeneratedFile.id
    )
    unconfirmed = (
        select(GeneratedFile.stored_path)
        .join(SalesHistoryFileOrder, SalesHistoryFileOrder.generated_file_id == GeneratedFile.id)
        .outerjoin(
            SalesHistoryExported,
            SalesHistoryExported.sales_order_id == SalesHistoryFileOrder.sales_order_id,
        )
        .where(SalesHistoryExported.sales_order_id.is_(None))
    )
    paths: set[Path] = set()
    for stmt in (attached, read, waiting, accounting, unconfirmed):
        paths.update(Path(p).resolve() for p in session.scalars(stmt))
    return paths


def remove(path: Path) -> bool:
    """Delete a file or a folder. A failure (a file still open in SAP or Excel) is only logged."""
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("Không xóa được %s: %s", path, exc)
        return False
    return True


def discard_unused(
    session: Session, settings: Settings, paths: Iterable[str | Path | None]
) -> list[Path]:
    """Delete the given stored files that no keep rule holds. Call after the commit that made
    them spent; returns what was deleted. None entries, and paths outside uploads/ and exports/,
    are skipped."""
    roots = [settings.upload_dir.resolve(), settings.export_dir.resolve()]
    candidates = [
        Path(p)
        for p in paths
        if p and any(Path(p).resolve().is_relative_to(root) for root in roots)
    ]
    if not candidates:
        return []
    kept = kept_files(session, settings)
    removed = []
    for path in candidates:
        if path.exists() and path.resolve() not in kept and remove(path):
            removed.append(path)
    return removed


@dataclass
class SweepResult:
    files: list[Path] = field(default_factory=list)
    screenshots: int = 0


def sweep_files(
    session: Session,
    settings: Settings,
    keep_days: int,
    actor: str,
    now: datetime | None = None,
) -> SweepResult:
    """Delete every stored file no keep rule holds and log the count. The caller commits."""
    now = now or datetime.now(UTC)
    fresh = (now - GRACE).timestamp()
    kept = kept_files(session, settings, now)
    result = SweepResult()
    for root in (settings.upload_dir, settings.export_dir):
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if (
                    path.is_file()
                    and path.stat().st_mtime < fresh
                    and path.resolve() not in kept
                    and remove(path)
                ):
                    result.files.append(path)
    result.files.extend(_sweep_robot_work(session, settings, keep_days, now))
    result.screenshots = evidence.prune(settings.evidence_dir, keep_days, now.timestamp())
    states.log_event(
        session,
        actor,
        "retention_files",
        detail={"files": len(result.files), "screenshots": result.screenshots},
    )
    return result


def _sweep_robot_work(
    session: Session, settings: Settings, keep_days: int, now: datetime
) -> list[Path]:
    """A job folder stays while its job is not DONE, for at most keep_days."""
    root = settings.robot_work_dir
    if not root.is_dir():
        return []
    fresh = (now - GRACE).timestamp()
    expired = (now - timedelta(days=keep_days)).timestamp()
    entries = sorted(root.iterdir())
    job_ids = {int(m[1]) for p in entries if p.is_dir() and (m := JOB_DIR.fullmatch(p.name))}
    status = dict(
        session.execute(select(SapJob.id, SapJob.status).where(SapJob.id.in_(job_ids))).all()
    )
    removed = []
    for path in entries:
        mtime = path.stat().st_mtime
        if mtime >= fresh:
            continue
        match = JOB_DIR.fullmatch(path.name) if path.is_dir() else None
        unfinished = match is not None and status.get(int(match[1])) not in (None, queue.DONE)
        if unfinished and mtime >= expired:
            continue
        if remove(path):
            removed.append(path)
    return removed
