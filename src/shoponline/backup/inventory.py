"""The backup list: reconcile ops.backup_run with the files on this machine and on Drive.

The database says what was made; the folders and Drive say what is still there. The page shows
both, and a file that exists on Drive but not in the database (a new machine, or a run lost) is
added as a row with source drive_found. The Drive listing is cached for a few minutes in the
web process so opening the page never waits on Google every time.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from shoponline.backup import naming, runner
from shoponline.backup.drive import friendly_error
from shoponline.config import Settings
from shoponline.db.models import BackupRequest, BackupRun

CACHE_TTL = timedelta(minutes=5)


def local_names(settings: Settings) -> set[str]:
    found: set[str] = set()
    for folder in settings.backup_dirs:
        try:
            found.update(p.name for p in folder.iterdir() if p.is_file())
        except OSError:
            continue
    return found


class DriveListing:
    """The Drive file list, cached. Dropped when a backup finished after it was read, and after
    every change an administrator makes."""

    def __init__(self, ttl: timedelta = CACHE_TTL):
        self._ttl = ttl
        self._lock = threading.Lock()
        self._at: datetime | None = None
        self._files: dict[str, dict] | None = None
        self._error: str | None = None

    def invalidate(self) -> None:
        with self._lock:
            self._at = None

    def get(
        self, drive, newest_finish: datetime | None, now: datetime | None = None
    ) -> tuple[dict[str, dict] | None, str | None]:
        """(files by name, error). files is None when Drive could not be read."""
        moment = now or datetime.now(UTC)
        with self._lock:
            fresh = (
                self._at is not None
                and moment - self._at < self._ttl
                and not (newest_finish and newest_finish > self._at)
            )
            if not fresh:
                try:
                    self._files = {f["name"]: f for f in drive.list_backups()}
                    self._error = None
                except Exception as exc:
                    self._files, self._error = None, friendly_error(exc)
                self._at = moment
            return self._files, self._error


def newest_finish(db: Session) -> datetime | None:
    return db.scalar(select(BackupRun.finished_at).order_by(BackupRun.finished_at.desc()).limit(1))


def add_drive_found(db: Session, files: dict[str, dict]) -> int:
    """A row for each backup file on Drive that no row knows (by name or Drive id). Two page
    loads at once cannot add the same file twice: the unique index on drive_file_id decides."""
    if not files:
        return 0
    names = list(files)
    ids = [f["id"] for f in files.values()]
    known = set(db.scalars(select(BackupRun.file_name).where(BackupRun.file_name.in_(names))))
    known_ids = set(
        db.scalars(select(BackupRun.drive_file_id).where(BackupRun.drive_file_id.in_(ids)))
    )
    added = 0
    for name, info in files.items():
        parsed = naming.parse(name)
        if parsed is None or name in known or info["id"] in known_ids:
            continue
        values = {
            "kind": parsed.kind,
            "source": "drive_found",
            "actor": runner.SYSTEM,
            "file_name": name,
            "size_bytes": int(info["size"]) if info.get("size") else None,
            "started_at": parsed.taken_at,
            "finished_at": parsed.taken_at,
            "local_status": "missing",
            "drive_requested": True,
            "drive_status": "ok",
            "drive_file_id": info["id"],
        }
        inserted = db.scalar(
            insert(BackupRun).values(**values).on_conflict_do_nothing().returning(BackupRun.id)
        )
        added += 1 if inserted is not None else 0
    db.commit()
    return added


@dataclass
class RowView:
    run: BackupRun
    local_label: str
    local_css: str
    drive_label: str
    drive_css: str
    on_local: bool
    on_drive: bool | None  # None: Drive could not be read
    can_download: bool
    can_restore: bool
    restore_block: str | None
    can_retry_drive: bool


def _local_state(run: BackupRun, present: bool, drive_has: bool) -> tuple[str, str]:
    status = run.local_status
    if status == "running":
        return "Đang chạy", "j-RUNNING"
    if status == "interrupted":
        return "Bị dừng giữa chừng", "j-FAILED"
    if status == "failed":
        return "Lỗi", "j-FAILED"
    if status == "deleted":
        return f"Đã xóa bởi {run.deleted_by or '?'}", ""
    if present:
        return ("Một phần" if status == "partial" else "Thành công"), "j-DONE"
    if drive_has:
        return "Không có (chỉ trên Drive)", ""
    return ("Đã xóa theo số bản giữ" if status == "rotated" else "Không có"), ""


def _drive_state(run: BackupRun, on_drive: bool | None, connected: bool) -> tuple[str, str]:
    status = run.drive_status
    if status == "uploading":
        return "Đang tải lên", "j-RUNNING"
    if status == "failed":
        return "Lỗi Drive", "j-FAILED"
    if status == "not_connected":
        return "Chưa kết nối", ""
    if status == "deleted":
        return f"Đã xóa bởi {run.deleted_by or '?'}", ""
    if status in ("ok", "rotated"):
        if on_drive is None:
            return "Đã lên Drive (không kiểm tra được lúc này)", "j-DONE"
        if on_drive:
            return "Đã lên Drive (MD5 khớp)", "j-DONE"
        return "Đã xóa theo số bản giữ", ""
    if run.drive_requested and not connected:
        return "Chưa kết nối", ""
    return "Không yêu cầu", ""


def build_rows(
    runs: list[BackupRun],
    local: set[str],
    drive_files: dict[str, dict] | None,
    connected: bool,
    known_revisions: set[str],
) -> list[RowView]:
    rows = []
    for run in runs:
        present = run.file_name in local
        on_drive = None if drive_files is None else run.file_name in drive_files
        drive_has = bool(on_drive) or (on_drive is None and run.drive_status == "ok")
        local_label, local_css = _local_state(run, present, drive_has)
        drive_label, drive_css = _drive_state(run, on_drive, connected)
        usable = (
            run.local_status in ("ok", "partial", "rotated", "missing")
            and (present or drive_has)
            and run.deleted_at is None
        )
        block = None
        if usable and run.kind == "app":
            block = "Bản Ứng dụng chỉ dùng khi chuyển máy, không phục hồi trên máy đang chạy"
        elif usable:
            revision = (run.manifest or {}).get("alembic_revision")
            if revision and revision not in known_revisions:
                block = f"Bản từ phiên bản mới hơn (revision {revision}); cập nhật mã trước"
        rows.append(
            RowView(
                run=run,
                local_label=local_label,
                local_css=local_css,
                drive_label=drive_label,
                drive_css=drive_css,
                on_local=present,
                on_drive=on_drive,
                can_download=usable,
                can_restore=usable and run.kind != "app",
                restore_block=block,
                can_retry_drive=(
                    present
                    and connected
                    and run.drive_status in ("failed", "not_connected", None)
                    and run.local_status in ("ok", "partial", "rotated")
                ),
            )
        )
    return rows


# --- delete rules -----------------------------------------------------------------------------


def delete_refusal(db: Session, run: BackupRun) -> str | None:
    """Why this backup may not be deleted, or None. The newest good backup of each kind and the
    safety backup of the latest restore are the ways back and are kept."""
    if run.local_status == "running" or run.drive_status == "uploading":
        return "Bản đang được tạo hoặc tải lên"
    newest = db.scalar(
        select(BackupRun.id)
        .where(
            BackupRun.kind == run.kind,
            BackupRun.deleted_at.is_(None),
            BackupRun.local_status.in_(("ok", "partial", "rotated", "missing")),
        )
        .order_by(BackupRun.started_at.desc(), BackupRun.id.desc())
        .limit(1)
    )
    if newest == run.id:
        return "Không xóa được bản thành công mới nhất của loại này"
    safety = db.scalar(
        select(BackupRequest.safety_run_id)
        .where(BackupRequest.action == "restore", BackupRequest.safety_run_id.is_not(None))
        .order_by(BackupRequest.id.desc())
        .limit(1)
    )
    if safety == run.id:
        return "Đây là bản an toàn của lần phục hồi gần nhất, giữ lại để lùi về khi cần"
    return None
