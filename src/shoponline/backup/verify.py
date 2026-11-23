"""Check a backup file: encrypted throughout, 7-Zip test passes, SHA-256 equals the recorded one."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from shoponline.backup.manifest import sha256_file
from shoponline.backup.runner import Context
from shoponline.db.models import BackupRun


class BackupNotFound(ValueError):
    pass


@dataclass
class Located:
    path: Path
    run_id: int | None


def locate(ctx: Context, target: str) -> Located:
    """A run id, a file name in the backup folders, or a path."""
    with ctx.session_factory() as db:
        if target.isdigit():
            run = db.get(BackupRun, int(target))
            if run is None:
                raise BackupNotFound(f"Không có bản sao lưu #{target}")
            name, run_id = run.file_name, run.id
        else:
            path = Path(target)
            if path.is_file():
                run_id = db.scalar(select(BackupRun.id).where(BackupRun.file_name == path.name))
                return Located(path, run_id)
            name = path.name
            run_id = db.scalar(select(BackupRun.id).where(BackupRun.file_name == name))
    for folder in ctx.settings.backup_dirs:
        if (folder / name).is_file():
            return Located(folder / name, run_id)
    raise BackupNotFound(f"Không thấy file {name} ở thư mục sao lưu nào trên máy chủ")


def verify(ctx: Context, located: Located) -> tuple[bool, str]:
    """Returns (ok, message) and records the result on the run when there is one."""
    try:
        sevenzip = ctx.sevenzip()
        sevenzip.require_encrypted(located.path)
        sevenzip.test(located.path)
        ok, message = True, "Mở được bằng mật khẩu sao lưu, 7-Zip kiểm tra không lỗi"
    except Exception as exc:
        ok, message = False, str(exc)
    if ok and located.run_id is not None:
        with ctx.session_factory() as db:
            recorded = db.get(BackupRun, located.run_id).sha256
        if recorded and sha256_file(located.path) != recorded:
            ok, message = False, "SHA-256 khác lúc tạo: file đã bị sửa hoặc hỏng"
        elif recorded:
            message += ", SHA-256 khớp"
    if located.run_id is not None:
        with ctx.session_factory() as db:
            run = db.get(BackupRun, located.run_id)
            run.verified_at = datetime.now(UTC)
            run.verify_result = ("OK: " if ok else "Lỗi: ") + message[:500]
            db.commit()
    return ok, message
