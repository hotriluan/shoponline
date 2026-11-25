"""Delete stored files once nothing needs them.

Files. One set of keep rules (kept_files) serves both the deletion at the moment a file is spent
(discard_unused, called by the web and the robot) and the nightly sweep (sweep_files), which
removes whatever is left over:

- uploads/: the zrsd004 files of a run that is still open (attached by hand, or read by the
  robot), and zrsd004 files uploaded by hand that still wait to be attached to a run, for at most
  retention_days. Platform files, mapping tables, zrsd001 and zrsd003 are read once, at import.
- exports/: every accounting file (the copy sent to accounting, including those from before runs
  existed), a Shop Online history file that still holds an order not yet confirmed as pasted,
  every file a sales return points at (the return documents, kept for good) and every history
  file loaded for the management reports (exports/history/, kept as evidence). Order files
  are deleted as soon as they are sent.
- robot-work/job-N: kept only while the job is not DONE, for at most evidence_keep_days.
- robot-evidence/: screenshots, for evidence_keep_days (saprobot.evidence.prune).

The sweep leaves files younger than an hour alone: a file may be written before the row that
keeps it is committed. A file that cannot be deleted is logged and left for the next sweep.
The sweep refuses to run when a stored path points outside the data folder (a database restored
onto a machine with another data folder would otherwise match no file and lose them all).

Customer data (name, address) is never deleted: it is kept for good, decided 2026-11-25, so the
management reports can break sales down by customer and province.
"""

from __future__ import annotations

import logging
import re
import shutil
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from shoponline.accounting import runs
from shoponline.config import Settings
from shoponline.db.models import (
    AccountingRun,
    AccountingRunRead,
    AccountingRunSource,
    GeneratedFile,
    ImportBatch,
    SalesHistoryExported,
    SalesHistoryFileOrder,
    SalesReturn,
    SapJob,
)
from shoponline.domain import states
from shoponline.sapjobs import queue
from shoponline.saprobot import evidence

log = logging.getLogger(__name__)

GRACE = timedelta(hours=1)
JOB_DIR = re.compile(r"job-(\d+)")


class ForeignStoredPaths(RuntimeError):
    """Stored file paths lie outside the data folder, so the keep rules cannot be trusted."""


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
    accounting = select(GeneratedFile.stored_path).where(
        or_(
            GeneratedFile.kind == "accounting_file",
            GeneratedFile.id.in_(
                select(AccountingRun.generated_file_id).where(
                    AccountingRun.generated_file_id.is_not(None)
                )
            ),
        )
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
    # Return documents are kept by the rows that point at them, not by their kind: reverting the
    # code that made them, or a kind this code no longer knows, must not let the sweep delete them.
    returns = select(GeneratedFile.stored_path).where(
        or_(
            GeneratedFile.id.in_(select(SalesReturn.docx_file_id)),
            GeneratedFile.id.in_(select(SalesReturn.xlsx_file_id)),
        )
    )
    history = select(ImportBatch.stored_path).where(ImportBatch.kind == "history_sales")
    paths: set[Path] = set()
    for stmt in (attached, read, waiting, accounting, unconfirmed, returns, history):
        paths.update(Path(p).resolve() for p in session.scalars(stmt))
    return paths


def foreign_paths(session: Session, settings: Settings) -> list[str]:
    """Stored paths (uploads and generated files) that are not inside the data folder."""
    root = settings.data_dir.resolve()
    stored = [
        *session.scalars(select(ImportBatch.stored_path)),
        *session.scalars(select(GeneratedFile.stored_path)),
    ]
    return sorted({p for p in stored if p and not Path(p).resolve().is_relative_to(root)})


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
    """Delete every stored file no keep rule holds and log the count. The caller commits.
    Raises ForeignStoredPaths, deleting nothing, when a stored path is outside the data folder."""
    now = now or datetime.now(UTC)
    foreign = foreign_paths(session, settings)
    if foreign:
        raise ForeignStoredPaths(
            f"{len(foreign)} đường dẫn lưu trong CSDL nằm ngoài thư mục dữ liệu "
            f"{settings.data_dir} (ví dụ {foreign[0]}); không xóa file nào"
        )
    fresh = (now - GRACE).timestamp()
    kept = kept_files(session, settings, now)
    result = SweepResult()
    for root in (settings.upload_dir, settings.export_dir):
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                try:
                    old = path.is_file() and path.stat().st_mtime < fresh
                except OSError:  # gone between the listing and the stat
                    continue
                if old and path.resolve() not in kept and remove(path):
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
        try:
            mtime = path.stat().st_mtime
        except OSError:  # gone since the listing
            continue
        if mtime >= fresh:
            continue
        match = JOB_DIR.fullmatch(path.name) if path.is_dir() else None
        unfinished = match is not None and status.get(int(match[1])) not in (None, queue.DONE)
        if unfinished and mtime >= expired:
            continue
        if remove(path):
            removed.append(path)
    return removed
