"""Take a backup, put it in every place it belongs, record it in ops.backup_run, rotate.

One function, run_backup, serves every path (schedule, the web's "back up now", deploy,
the safety backup before a restore, machine migration). Only one backup runs at a time: the
caller holds the backup advisory lock (see backup_lock) for as long as it works.

Exit codes of the command line:
    0  every place that was asked got the backup
    2  some places got it (still a usable backup)
    1  no place got it
    3  the lock could not be taken, so no backup was made
Google Drive "not connected" is not a failed place.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from sqlalchemy import Connection, Engine, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from shoponline.backup import archive, naming, pgtools, schedule, staging
from shoponline.backup.manifest import sha256_file
from shoponline.backup.retention import KeepRules, to_delete
from shoponline.backup.sevenzip import SevenZip, find_exe
from shoponline.config import Settings
from shoponline.db.models import BackupRequest, BackupRun, BackupSettings

log = logging.getLogger(__name__)

LOCK_KEY = 0x5A9_0B08  # any fixed number; only backups and restores take it
EXIT_OK, EXIT_NONE, EXIT_PARTIAL, EXIT_LOCKED = 0, 1, 2, 3
SYSTEM = "system"
# A failed scheduled run is tried again after this long, not on every 15-minute tick.
RETRY_AFTER = timedelta(hours=1)
QUEUE_ACTIONS = ("backup", "retry_drive", "drill", "verify")  # restore has its own task
RESTORE_ACTIONS = ("restore",)


class DrivePlace(Protocol):
    """Google Drive as a backup place (shoponline.backup.drive provides the real one)."""

    def connected(self) -> bool: ...

    def upload(self, path: Path, name: str) -> str: ...  # returns the Drive file id

    def names(self) -> dict[str, str]: ...  # backup file name -> Drive file id

    def delete(self, file_id: str) -> None: ...

    def friendly(self, exc: Exception) -> str: ...


@dataclass
class Context:
    settings: Settings
    session_factory: Callable[[], Session]
    engine: Engine
    repo_root: Path
    pg_bin: Path | None = None
    seven_zip: Path | None = None
    drive: DrivePlace | None = None
    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))

    def sevenzip(self) -> SevenZip:
        return SevenZip(self.seven_zip or find_exe(), self.settings.backup_password)


@dataclass
class Outcome:
    exit_code: int
    run_id: int | None = None
    file_name: str | None = None
    message: str = ""
    archive_path: Path | None = None


@contextmanager
def backup_lock(engine: Engine, wait: timedelta | None = None) -> Iterator[Connection | None]:
    """Yield a connection holding the backup lock, or None when another process holds it.

    Without `wait` the lock is only tried; with it, the call waits that long at most.
    Closing the connection releases the lock even if this process dies.
    """
    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        if wait is None:
            got = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar()
        else:
            conn.execute(text(f"SET lock_timeout = {int(wait.total_seconds() * 1000)}"))
            try:
                conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": LOCK_KEY})
                got = True
            except OperationalError:
                got = False
            conn.execute(text("SET lock_timeout = 0"))
        if not got:
            yield None
            return
        try:
            yield conn
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
    finally:
        conn.close()


def lock_is_held(db: Session) -> bool:
    """True while some process really holds the backup lock (the web uses this)."""
    return bool(
        db.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' "
                "AND granted AND classid = 0 AND objsubid = 1 AND objid = :k AND database = "
                "(SELECT oid FROM pg_database WHERE datname = current_database()))"
            ),
            {"k": LOCK_KEY & 0xFFFFFFFF},
        ).scalar()
    )


def mark_interrupted(db: Session) -> int:
    """Whoever holds the lock knows any row still 'running' belongs to a process that died."""
    now = datetime.now(UTC)
    runs = db.execute(
        update(BackupRun)
        .where(BackupRun.local_status == "running")
        .values(local_status="interrupted", finished_at=now, local_error="Tiến trình bị dừng")
    ).rowcount
    db.execute(
        update(BackupRun)
        .where(BackupRun.drive_status == "uploading")
        .values(drive_status="failed", drive_error="Tiến trình bị dừng")
    )
    requests = db.execute(
        update(BackupRequest)
        .where(BackupRequest.status == "running")
        .values(status="interrupted", finished_at=now, message="Tiến trình bị dừng giữa chừng")
    ).rowcount
    db.commit()
    return runs + requests


def keep_rules(db: Session) -> KeepRules:
    return KeepRules.from_settings(backup_settings(db))


def backup_settings(db: Session) -> BackupSettings:
    row = db.get(BackupSettings, 1)
    if row is None:  # the migration inserts it; a hand-cleared table gets the defaults back
        row = BackupSettings(id=1)
        db.add(row)
        db.flush()
    return row


def run_backup(
    ctx: Context, kind: str, source: str, actor: str = SYSTEM, to_drive: bool = False
) -> Outcome:
    """Make one backup. The caller holds the backup lock."""
    settings = ctx.settings
    database = pgtools.database_name(settings.database_url)
    name = naming.make(kind, database, ctx.now())
    with ctx.session_factory() as db:
        run = BackupRun(
            kind=kind,
            source=source,
            actor=actor,
            file_name=name,
            started_at=ctx.now(),
            local_status="running",
            drive_requested=to_drive,
        )
        db.add(run)
        db.commit()
        run_id = run.id
    log.info("Bắt đầu sao lưu %s (%s), bản #%d %s", kind, source, run_id, name)

    staging.sweep_stale(settings.backup_work_dir)
    try:
        with staging.staging_dir(settings.backup_work_dir, "backup") as work:
            outcome = _make_and_place(ctx, run_id, kind, source, name, work, to_drive)
    except Exception as exc:  # anything before a file existed: the run failed everywhere
        log.exception("Sao lưu #%d lỗi", run_id)
        with ctx.session_factory() as db:
            run = db.get(BackupRun, run_id)
            run.local_status = "failed"
            run.local_error = str(exc)[:1000]
            run.finished_at = datetime.now(UTC)
            if to_drive:
                run.drive_status = "failed"
                run.drive_error = "Không có bản sao lưu để tải lên"
            db.commit()
        return Outcome(EXIT_NONE, run_id, name, f"Sao lưu lỗi: {exc}")
    return outcome


def _make_and_place(
    ctx: Context, run_id: int, kind: str, source: str, name: str, work: Path, to_drive: bool
) -> Outcome:
    settings = ctx.settings
    if not settings.backup_dirs:
        raise RuntimeError("Thiếu SHOPONLINE_BACKUP_DIRS")
    sevenzip = ctx.sevenzip()
    content = work / "content"
    content.mkdir()
    src = archive.Sources(settings, ctx.repo_root, ctx.pg_bin)
    manifest = archive.build(kind, source, src, content)
    built = work / name
    members = [m for m in archive.top_level_members(kind) if (content / m).exists()]
    sevenzip.create(built, members, cwd=content)
    sevenzip.test(built)
    digest, size = sha256_file(built), built.stat().st_size

    reached, errors = [], []
    for folder in settings.backup_dirs:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            partial = folder / (name + ".partial")
            shutil.copyfile(built, partial)
            partial.replace(folder / name)
            reached.append(folder)
        except OSError as exc:
            errors.append(f"{folder}: {exc}")
            log.warning("Không chép được bản #%d tới %s: %s", run_id, folder, exc)
    local_status = "ok" if not errors else ("partial" if reached else "failed")

    drive_status, drive_id, drive_error = _upload(ctx, run_id, built, name, to_drive)

    with ctx.session_factory() as db:
        run = db.get(BackupRun, run_id)
        run.size_bytes = size
        run.sha256 = digest
        run.manifest = manifest.to_dict()
        run.local_status = local_status
        run.local_error = "; ".join(errors)[:1000] or None
        run.drive_status = drive_status
        run.drive_file_id = drive_id
        run.drive_error = drive_error
        run.finished_at = datetime.now(UTC)
        db.commit()
        rules = keep_rules(db)
        db.commit()

    local_ok, drive_failed = local_status == "ok", drive_status == "failed"
    if not reached and drive_status != "ok":
        exit_code = EXIT_NONE
    elif local_ok and not drive_failed:
        exit_code = EXIT_OK
    else:
        exit_code = EXIT_PARTIAL

    # A place only rotates after the new backup reached it.
    rotate_local(ctx, reached, rules)
    if drive_status == "ok":
        rotate_drive(ctx, rules)
    # The web banner is about the database, so only backups that contain it move the marker.
    if exit_code == EXIT_OK and kind in ("db", "full"):
        _write_marker(settings)

    parts = [f"Sao lưu {kind} xong: {name}"]
    if errors:
        parts.append("lỗi máy chủ: " + "; ".join(errors))
    if drive_status == "failed":
        parts.append(f"lỗi Google Drive: {drive_error}")
    elif drive_status == "not_connected":
        parts.append("Google Drive chưa kết nối")
    log.info("; ".join(parts))
    first = reached[0] / name if reached else None
    return Outcome(exit_code, run_id, name, "; ".join(parts), first)


def _upload(
    ctx: Context, run_id: int, path: Path, name: str, to_drive: bool
) -> tuple[str | None, str | None, str | None]:
    """(drive_status, drive_file_id, drive_error) for a new backup."""
    if not to_drive:
        return None, None, None
    drive = ctx.drive
    if drive is None or not drive.connected():
        return "not_connected", None, None
    with ctx.session_factory() as db:
        db.execute(update(BackupRun).where(BackupRun.id == run_id).values(drive_status="uploading"))
        db.commit()
    try:
        return "ok", drive.upload(path, name), None
    except Exception as exc:
        log.warning("Tải bản #%d lên Google Drive lỗi: %r", run_id, exc)
        return "failed", None, drive.friendly(exc)


def rotate_local(ctx: Context, folders: list[Path], rules: KeepRules) -> list[str]:
    database = pgtools.database_name(ctx.settings.database_url)
    removed: list[str] = []
    for folder in folders:
        names = [p.name for p in folder.iterdir() if p.is_file()]
        for name in to_delete(names, database, rules, ctx.now()):
            try:
                (folder / name).unlink()
                removed.append(name)
                log.info("Xoay vòng: xóa %s ở %s", name, folder)
            except OSError as exc:
                log.warning("Không xóa được %s ở %s: %s", name, folder, exc)
    gone = [n for n in set(removed) if not any((f / n).exists() for f in ctx.settings.backup_dirs)]
    if gone:
        with ctx.session_factory() as db:
            db.execute(
                update(BackupRun)
                .where(BackupRun.file_name.in_(gone), BackupRun.local_status.in_(("ok", "partial")))
                .values(local_status="rotated")
            )
            db.commit()
    return removed


def rotate_drive(ctx: Context, rules: KeepRules) -> list[str]:
    drive = ctx.drive
    if drive is None:
        return []
    database = pgtools.database_name(ctx.settings.database_url)
    try:
        on_drive = drive.names()
    except Exception as exc:
        log.warning("Không liệt kê được Google Drive để xoay vòng: %r", exc)
        return []
    removed = []
    for name in to_delete(on_drive, database, rules, ctx.now()):
        try:
            drive.delete(on_drive[name])
            removed.append(name)
            log.info("Xoay vòng: xóa %s trên Google Drive", name)
        except Exception as exc:
            log.warning("Không xóa được %s trên Google Drive: %r", name, exc)
    if removed:
        with ctx.session_factory() as db:
            db.execute(
                update(BackupRun)
                .where(BackupRun.file_name.in_(removed), BackupRun.drive_status == "ok")
                .values(drive_status="rotated")
            )
            db.commit()
    return removed


def _write_marker(settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.backup_marker.write_text(datetime.now(UTC).isoformat(), encoding="utf-8")


def worst(codes: list[int]) -> int:
    if not codes:
        return EXIT_OK
    for code in (EXIT_LOCKED, EXIT_NONE, EXIT_PARTIAL):
        if code in codes:
            return code
    return EXIT_OK


# --- queue and schedule ------------------------------------------------------------------


def process_requests(ctx: Context, actions: tuple[str, ...] = QUEUE_ACTIONS) -> list[int]:
    """Work through pending requests of `actions`, oldest first. The caller holds the lock."""
    from shoponline.backup import restore  # registers the drill, verify and restore handlers

    if "restore" in actions:
        restore.expire_stale_restores(ctx)
    codes = []
    while True:
        with ctx.session_factory() as db:
            req = db.scalar(
                select(BackupRequest)
                .where(BackupRequest.status == "pending", BackupRequest.action.in_(actions))
                .order_by(BackupRequest.id)
                .limit(1)
            )
            if req is None:
                return codes
            req.status, req.started_at = "running", datetime.now(UTC)
            db.commit()
            req_id, action = req.id, req.action
        handler = HANDLERS[action]
        try:
            status, message, result, code = handler(ctx, req_id)
        except Exception as exc:
            log.exception("Yêu cầu #%d (%s) lỗi", req_id, action)
            status, message, result, code = "failed", str(exc)[:500], None, EXIT_NONE
        with ctx.session_factory() as db:
            req = db.get(BackupRequest, req_id)
            req.status, req.message, req.finished_at = status, message, datetime.now(UTC)
            if result is not None:
                req.result = result
            db.commit()
        codes.append(code)


def _handle_backup(ctx: Context, req_id: int):
    with ctx.session_factory() as db:
        req = db.get(BackupRequest, req_id)
        kind, actor, to_drive = req.kind or "db", req.requested_by, req.to_drive
    outcome = run_backup(ctx, kind, "manual", actor, to_drive)
    status = "done" if outcome.exit_code in (EXIT_OK, EXIT_PARTIAL) else "failed"
    return status, outcome.message, {"run_id": outcome.run_id}, outcome.exit_code


def _handle_retry_drive(ctx: Context, req_id: int):
    """Upload again a backup that is on this machine; no new backup is made."""
    with ctx.session_factory() as db:
        req = db.get(BackupRequest, req_id)
        run = db.get(BackupRun, req.target_run_id) if req.target_run_id else None
        if run is None:
            return "failed", "Không có bản sao lưu này", None, EXIT_NONE
        name, run_id = run.file_name, run.id
    path = next((f / name for f in ctx.settings.backup_dirs if (f / name).is_file()), None)
    if path is None:
        return "failed", "File không còn ở máy chủ nên không tải lên lại được", None, EXIT_NONE
    status, file_id, error = _upload(ctx, run_id, path, name, True)
    with ctx.session_factory() as db:
        run = db.get(BackupRun, run_id)
        run.drive_requested, run.drive_status = True, status
        run.drive_file_id, run.drive_error = file_id, error
        db.commit()
        rules = keep_rules(db)
    if status == "ok":
        rotate_drive(ctx, rules)
        return "done", "Đã tải lên Google Drive", {"run_id": run_id}, EXIT_OK
    message = error or "Google Drive chưa kết nối"
    return "failed", message, {"run_id": run_id}, EXIT_NONE


HANDLERS: dict[str, Callable] = {"backup": _handle_backup, "retry_drive": _handle_retry_drive}


def last_scheduled_success(db: Session, now: datetime) -> dict[str, datetime | None]:
    """Per scheduled kind: the latest scheduled run that reached a place, or a failed one
    within RETRY_AFTER (so a failing schedule is retried hourly, not every tick)."""
    found: dict[str, datetime | None] = {}
    for kind in schedule.SCHEDULED_KINDS:
        ok = db.scalar(
            select(BackupRun.started_at)
            .where(
                BackupRun.kind == kind,
                BackupRun.source == "schedule",
                BackupRun.local_status.in_(("ok", "partial", "rotated")),
            )
            .order_by(BackupRun.started_at.desc())
            .limit(1)
        )
        failed = db.scalar(
            select(BackupRun.started_at)
            .where(
                BackupRun.kind == kind,
                BackupRun.source == "schedule",
                BackupRun.local_status.in_(("failed", "interrupted")),
                BackupRun.started_at > now - RETRY_AFTER,
            )
            .order_by(BackupRun.started_at.desc())
            .limit(1)
        )
        found[kind] = max((t for t in (ok, failed) if t is not None), default=None)
    return found


def run_due(ctx: Context) -> list[int]:
    """Scheduled backups that are due, database before full. The caller holds the lock."""
    now = ctx.now()
    with ctx.session_factory() as db:
        settings = backup_settings(db)
        due = schedule.due_kinds(now, settings, last_scheduled_success(db, now))
        to_drive = settings.drive_on_schedule
        db.commit()
    return [run_backup(ctx, kind, "schedule", SYSTEM, to_drive).exit_code for kind in due]


def if_due(ctx: Context) -> int:
    """The 15-minute task: pending requests first, then the schedule."""
    with backup_lock(ctx.engine) as lock:
        if lock is None:
            log.info("Đang có tiến trình sao lưu khác chạy; bỏ qua lần này")
            return EXIT_LOCKED
        with ctx.session_factory() as db:
            mark_interrupted(db)
        return worst(process_requests(ctx) + run_due(ctx))


def run_now(
    ctx: Context, kind: str, source: str, actor: str = SYSTEM, to_drive: bool = False
) -> Outcome:
    """A single backup asked for on the command line. Deploy and migration wait for a running
    backup to finish (20 minutes at most); anything else gives up at once."""
    wait = timedelta(minutes=20) if source in ("deploy", "migration") else None
    with backup_lock(ctx.engine, wait) as lock:
        if lock is None:
            return Outcome(EXIT_LOCKED, message="Đang có tiến trình sao lưu khác chạy")
        with ctx.session_factory() as db:
            mark_interrupted(db)
        return run_backup(ctx, kind, source, actor, to_drive)
