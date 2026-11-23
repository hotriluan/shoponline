"""What the web shows about backups, read from the database only: the warning banner, whether a
backup is running now, and when the next scheduled ones are due. Nothing here calls Google."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shoponline.backup import runner, schedule
from shoponline.clock import VIETNAM
from shoponline.db.models import BackupRequest, BackupRun, BackupSettings, DriveConnection

SLOT_GRACE = timedelta(hours=2)  # a scheduled backup may take this long past its time
FULL_MAX_AGE = timedelta(days=8)  # the weekly full backup is overdue after this
LOCAL_OK = ("ok", "partial", "rotated")
DRIVE_OK = ("ok", "rotated")
DB_KINDS = ("db", "full")  # a full backup contains the database


def _success(place: str):
    return (
        BackupRun.local_status.in_(LOCAL_OK)
        if place == "local"
        else (BackupRun.drive_status.in_(DRIVE_OK))
    )


def last_db_backup(db: Session, place: str) -> datetime | None:
    """Start of the latest successful backup holding the database in "local" or "drive"."""
    return db.scalar(
        select(func.max(BackupRun.started_at)).where(BackupRun.kind.in_(DB_KINDS), _success(place))
    )


def last_success(db: Session, kind: str, place: str) -> datetime | None:
    """Start of the latest successful backup of `kind` in "local" or "drive"."""
    return db.scalar(
        select(func.max(BackupRun.started_at)).where(BackupRun.kind == kind, _success(place))
    )


def _fmt(moment: datetime) -> str:
    return moment.astimezone(VIETNAM).strftime("%d/%m/%Y %H:%M")


def warnings(db: Session, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(UTC)
    settings = db.get(BackupSettings, 1) or BackupSettings(id=1)
    drive = db.get(DriveConnection, 1)
    problems = []
    slot = schedule.last_slot("db", now, settings)
    local = last_db_backup(db, "local")
    if local is None:
        problems.append("Chưa có bản sao lưu database nào được ghi nhận.")
    elif now > slot + SLOT_GRACE and local < slot:
        problems.append(
            f"Chưa có bản sao lưu database từ lịch lúc {_fmt(slot)} (bản gần nhất {_fmt(local)})."
        )
    if drive is not None and drive.status == "error":
        problems.append(f"Google Drive: {drive.last_error or 'lỗi kết nối'}")
    elif drive is not None and drive.status == "connected" and settings.drive_on_schedule:
        on_drive = last_db_backup(db, "drive")
        if on_drive is None or (now > slot + SLOT_GRACE and on_drive < slot):
            problems.append(
                "Bản sao lưu database gần nhất chưa lên Google Drive"
                + (f" (bản trên Drive lúc {_fmt(on_drive)})." if on_drive else ".")
            )
    elif settings.drive_on_schedule and _scheduled_run_missed_drive(db):
        problems.append(
            "Google Drive chưa kết nối: bản sao lưu theo lịch gần nhất chỉ ở máy chủ "
            "(kết nối ở trang Sao lưu, hoặc bỏ ô lên Drive trong lịch nếu không dùng Drive)."
        )
    full = last_success(db, "full", "local")
    if full is None or now - full > FULL_MAX_AGE:
        problems.append(
            "Chưa có bản sao lưu Toàn bộ trong 8 ngày qua; bản Toàn bộ chỉ giữ "
            f"{settings.full_max_days} ngày."
        )
    return problems


def _scheduled_run_missed_drive(db: Session) -> bool:
    """The latest scheduled database backup wanted Drive and found it not connected."""
    latest = db.scalar(
        select(BackupRun.drive_status)
        .where(BackupRun.source == "schedule", BackupRun.kind.in_(DB_KINDS))
        .order_by(BackupRun.started_at.desc())
        .limit(1)
    )
    return latest == "not_connected"


def banner(db: Session) -> str | None:
    found = warnings(db)
    return " ".join(found) if found else None


def is_busy(db: Session) -> bool:
    """A backup request waits, or some process really holds the backup lock. A run row that
    says running while nobody holds the lock is an orphan and does not count."""
    waiting = db.scalar(
        select(func.count())
        .select_from(BackupRequest)
        .where(BackupRequest.status == "pending", BackupRequest.action == "backup")
    )
    return bool(waiting) or runner.lock_is_held(db)


def next_runs(db: Session, now: datetime | None = None) -> dict[str, datetime | None]:
    now = now or datetime.now(UTC)
    settings = db.get(BackupSettings, 1) or BackupSettings(id=1)
    return {kind: schedule.next_slot(kind, now, settings) for kind in schedule.SCHEDULED_KINDS}
