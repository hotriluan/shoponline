"""Changes an administrator makes to the backup list from the web: delete files, accept an
uploaded backup. The web handlers stay thin and call these."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from shoponline.backup import naming, restore
from shoponline.backup.manifest import sha256_file
from shoponline.backup.runner import Context
from shoponline.backup.staging import staging_dir
from shoponline.db.models import BackupRun, EventLog

MAX_UPLOAD = 1 << 30  # 1 GB


class ManageError(RuntimeError):
    """A refusal with a message the administrator can act on."""


def delete_files(ctx: Context, run_id: int, where: str, actor: str) -> str:
    """Delete a backup's file on this machine, on Drive, or both. The row stays with who and when.
    `where` is local, drive or both. Returns a sentence for the administrator."""
    from shoponline.backup import inventory

    with ctx.session_factory() as db:
        run = db.get(BackupRun, run_id)
        if run is None:
            raise ManageError("Không có bản sao lưu này")
        refusal = inventory.delete_refusal(db, run)
        if refusal:
            raise ManageError(refusal)
        name, drive_id = run.file_name, run.drive_file_id
    done = []
    if where in ("local", "both"):
        removed = 0
        for folder in ctx.settings.backup_dirs:
            target = folder / name
            if target.is_file():
                target.unlink()
                removed += 1
        done.append(f"máy chủ ({removed} nơi)")
    if where in ("drive", "both"):
        if ctx.drive is None or not ctx.drive.connected():
            raise ManageError("Chưa kết nối Google Drive nên không xóa được trên Drive")
        if drive_id is None:
            drive_id = ctx.drive.names().get(name)
        if drive_id:
            ctx.drive.delete(drive_id)
        done.append("Google Drive")
    with ctx.session_factory() as db:
        run = db.get(BackupRun, run_id)
        now = datetime.now(UTC)
        if where in ("local", "both"):
            run.local_status = "deleted"
        if where in ("drive", "both"):
            run.drive_status = "deleted"
        run.deleted_by, run.deleted_at = actor[:50], now
        db.add(
            EventLog(actor=actor[:50], kind="backup_delete", detail=f"{name}: {', '.join(done)}")
        )
        db.commit()
    return f"Đã xóa {name} ở: {', '.join(done)}."


def ingest_upload(ctx: Context, part: Path, claimed_name: str, actor: str) -> BackupRun:
    """Check an uploaded backup and, when it is good, store it in the first backup folder.

    Good means: encrypted throughout, opens with the backup password, every part matches the
    manifest (or it is an old single-dump backup with a proper name), and nothing with that name
    exists yet. A bad file raises ManageError; the caller removes it."""
    if not ctx.settings.backup_dirs:
        raise ManageError("Máy chủ chưa đặt thư mục sao lưu (SHOPONLINE_BACKUP_DIRS)")
    with staging_dir(ctx.settings.backup_work_dir, "upload") as work:
        try:
            prep = restore.prepare(ctx, part, work)
        except restore.RestoreRefused as exc:
            raise ManageError(f"File bị từ chối: {exc}") from exc
        parsed = naming.parse(Path(claimed_name).name)
        if prep.manifest is not None:
            kind = prep.manifest.kind
            database = prep.manifest.database
            if parsed is None or parsed.kind != kind:
                taken = datetime.fromisoformat(prep.manifest.created_at)
                final = naming.make(kind, database, taken)
            else:
                final = parsed.name
        elif parsed is not None:
            kind, final = parsed.kind, parsed.name
        else:
            raise ManageError(
                "Bản sao lưu cũ cần tên file đúng dạng shoponline-<database>-<ngày>.7z"
            )
    folder = ctx.settings.backup_dirs[0]
    folder.mkdir(parents=True, exist_ok=True)
    with ctx.session_factory() as db:
        clash = db.scalar(select(BackupRun.id).where(BackupRun.file_name == final))
    if clash is not None or any((f / final).exists() for f in ctx.settings.backup_dirs):
        raise ManageError(f"Đã có bản sao lưu tên {final}")
    partial = folder / (final + ".partial")
    shutil.copyfile(part, partial)
    partial.replace(folder / final)
    stored = folder / final
    with ctx.session_factory() as db:
        run = BackupRun(
            kind=kind,
            source="upload",
            actor=actor[:50],
            file_name=final,
            size_bytes=stored.stat().st_size,
            sha256=sha256_file(stored),
            manifest=prep.manifest.to_dict() if prep.manifest else None,
            finished_at=datetime.now(UTC),
            local_status="ok",
            drive_requested=False,
        )
        db.add(run)
        db.add(EventLog(actor=actor[:50], kind="backup_upload", detail=final))
        db.commit()
        db.refresh(run)
        return run
