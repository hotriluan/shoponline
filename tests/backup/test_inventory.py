"""Reconciling the backup records with the files on this machine and on Drive."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text

from shoponline.backup import inventory, naming
from shoponline.db.models import BackupRequest, BackupRun

KNOWN = {"0009_platform_settlement", "0011_drive_connection"}


def _run(**fields) -> BackupRun:
    values = {
        "kind": "db",
        "source": "manual",
        "actor": "admin",
        "file_name": "shoponline-db-x-20261101-230000.7z",
        "local_status": "ok",
        "started_at": datetime(2026, 11, 1, tzinfo=UTC),
    }
    values.update(fields)
    return BackupRun(**values)


def _row(run, local=(), drive=None, connected=True):
    (view,) = inventory.build_rows([run], set(local), drive, connected, KNOWN)
    return view


def test_present_file_is_a_success_and_missing_is_explained():
    run = _run(drive_status="ok")
    present = _row(run, local={run.file_name}, drive={run.file_name: {}})
    assert (present.local_label, present.drive_label) == ("Thành công", "Đã lên Drive (MD5 khớp)")
    only_drive = _row(run, local=set(), drive={run.file_name: {}})
    assert only_drive.local_label == "Không có (chỉ trên Drive)" and only_drive.can_restore
    rotated = _row(_run(local_status="rotated", drive_status="rotated"), local=set(), drive={})
    assert rotated.local_label == "Đã xóa theo số bản giữ"
    assert rotated.drive_label == "Đã xóa theo số bản giữ" and not rotated.can_restore


def test_drive_unreadable_is_not_reported_as_deleted():
    run = _run(drive_status="ok")
    view = _row(run, local=set(), drive=None)
    assert "không kiểm tra được" in view.drive_label and view.on_drive is None
    assert view.can_restore  # the Drive copy is assumed until Drive can be read


def test_failure_states_and_retry_button():
    failed = _row(_run(local_status="failed"), local=set())
    assert failed.local_label == "Lỗi" and not failed.can_download
    drive_failed = _run(drive_status="failed", file_name="a.7z")
    assert _row(drive_failed, local={"a.7z"}).can_retry_drive
    assert not _row(drive_failed, local=set()).can_retry_drive  # nothing left to upload
    assert not _row(drive_failed, local={"a.7z"}, connected=False).can_retry_drive
    assert _row(_run(local_status="running"), local=set()).local_label == "Đang chạy"
    assert _row(_run(drive_status="uploading"), local=set()).drive_label == "Đang tải lên"
    assert _row(_run(drive_status="not_connected"), local=set()).drive_label == "Chưa kết nối"
    assert _row(_run(), local=set()).drive_label == "Không yêu cầu"


def test_restore_is_blocked_for_app_backups_and_newer_schemas():
    app = _row(_run(kind="app"), local={"shoponline-db-x-20261101-230000.7z"})
    assert not app.can_restore and app.can_download
    newer = _run(manifest={"alembic_revision": "9999_future"})
    view = _row(newer, local={newer.file_name})
    assert view.can_download and view.can_restore and "9999_future" in view.restore_block
    old = _run(manifest={"alembic_revision": "0009_platform_settlement"})
    assert _row(old, local={old.file_name}).restore_block is None


def test_deleted_rows_keep_who_deleted(db):
    run = _run(local_status="deleted", deleted_by="boss", deleted_at=datetime.now(UTC))
    view = _row(run, local=set())
    assert view.local_label == "Đã xóa bởi boss" and not view.can_restore


# --- Drive found ------------------------------------------------------------------------------


def test_drive_found_adds_each_file_once_and_ignores_other_names(db):
    db.execute(text("DELETE FROM ops.backup_run"))
    when = datetime.now(UTC) - timedelta(days=1)
    name = naming.make("full", "shoponline", when)
    known = _run(file_name="known.7z", drive_file_id="id-known")
    db.add(known)
    db.flush()
    files = {
        name: {"id": "id-new", "size": "99"},
        "holiday.zip": {"id": "id-other", "size": "1"},
        "shoponline-db-x-20261101-230000.7z": {"id": "id-known", "size": "5"},
    }
    assert inventory.add_drive_found(db, files) == 1
    assert inventory.add_drive_found(db, files) == 0
    row = db.scalars(select(BackupRun).where(BackupRun.file_name == name)).one()
    assert (row.source, row.kind, row.local_status, row.drive_status, row.size_bytes) == (
        "drive_found",
        "full",
        "missing",
        "ok",
        99,
    )
    assert db.scalar(text("SELECT count(*) FROM ops.backup_run")) == 2


# --- listing cache ----------------------------------------------------------------------------


class CountingDrive:
    def __init__(self):
        self.calls = 0
        self.fail = False

    def list_backups(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("down")
        return [{"name": "a.7z", "id": "1"}]


def test_listing_is_cached_for_five_minutes_and_dropped_by_news():
    cache, drive = inventory.DriveListing(), CountingDrive()
    now = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
    assert cache.get(drive, None, now)[0] == {"a.7z": {"name": "a.7z", "id": "1"}}
    cache.get(drive, None, now + timedelta(minutes=4))
    assert drive.calls == 1
    cache.get(drive, None, now + timedelta(minutes=6))
    assert drive.calls == 2
    cache.get(drive, now + timedelta(minutes=7), now + timedelta(minutes=7, seconds=1))
    assert drive.calls == 3  # a backup finished after the list was read
    cache.invalidate()
    cache.get(drive, None, now + timedelta(minutes=7, seconds=2))
    assert drive.calls == 4


def test_listing_failure_gives_no_files_and_a_message():
    cache, drive = inventory.DriveListing(), CountingDrive()
    drive.fail = True
    files, error = cache.get(drive, None, datetime(2026, 11, 23, tzinfo=UTC))
    assert files is None and error


# --- delete rules -----------------------------------------------------------------------------


def test_delete_refusals(db):
    db.execute(text("DELETE FROM ops.backup_request"))
    db.execute(text("DELETE FROM ops.backup_run"))
    now = datetime.now(UTC)
    old = _run(file_name="old.7z", started_at=now - timedelta(days=2))
    new = _run(file_name="new.7z", started_at=now - timedelta(days=1))
    other_kind = _run(file_name="app.7z", kind="app", started_at=now - timedelta(days=5))
    running = _run(file_name="run.7z", local_status="running", started_at=now - timedelta(days=3))
    db.add_all([old, new, other_kind, running])
    db.flush()
    assert inventory.delete_refusal(db, old) is None
    assert "mới nhất" in inventory.delete_refusal(db, new)
    assert "mới nhất" in inventory.delete_refusal(db, other_kind)  # the only app backup
    assert "đang được tạo" in inventory.delete_refusal(db, running)
    db.add(BackupRequest(action="restore", requested_by="a", status="done", safety_run_id=old.id))
    db.flush()
    assert "bản an toàn" in inventory.delete_refusal(db, old)
