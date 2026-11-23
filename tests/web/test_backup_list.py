# ruff: noqa: F811  (fixtures imported from the backup and backup-page tests)
"""The backup list and its actions on the web: reconcile, download, verify, retry, delete,
restore requests, upload, restore outcome banner."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from shoponline.backup import naming, pgtools, restore, runner, trigger
from shoponline.backup.sevenzip import SevenZip
from shoponline.db.models import BackupRequest, BackupRun, EventLog
from shoponline.web.app import create_app
from shoponline.web.auth import set_user
from tests.backup.conftest import PASSWORD, backup_ctx, seven_zip  # noqa: F401
from tests.sap_setup import NO_ENV
from tests.web.test_backup_page import _connect, google, started  # noqa: F401


@pytest.fixture
def app(db, backup_ctx):  # noqa: F811
    """The web app on the same settings, folders and password as the backup context."""
    set_user(db, "admin", "admin-password", "admin")
    set_user(db, "viewer", "viewer-password", "viewer")
    return create_app(
        backup_ctx.settings,
        session_factory=lambda: Session(
            bind=db.bind, join_transaction_mode="create_savepoint", expire_on_commit=False
        ),
        env=NO_ENV,
    )


def _database(ctx) -> str:
    return pgtools.database_name(ctx.settings.database_url)


def _add_run(db, ctx, kind="db", hours_ago=1, **fields) -> BackupRun:
    when = datetime.now(UTC) - timedelta(hours=hours_ago)
    name = fields.pop("file_name", naming.make(kind, _database(ctx), when))
    run = BackupRun(
        kind=kind,
        source=fields.pop("source", "manual"),
        actor=fields.pop("actor", "admin"),
        file_name=name,
        started_at=when,
        finished_at=when,
        local_status=fields.pop("local_status", "ok"),
        size_bytes=fields.pop("size_bytes", 1234),
        **fields,
    )
    db.add(run)
    db.flush()
    return run


def _place_file(ctx, run, data=b"backup-bytes", place=0):
    folder = ctx.settings.backup_dirs[place]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / run.file_name).write_bytes(data)


def _flashes(text_: str) -> str:
    import re

    return " ".join(re.findall(r'class="flash[^"]*">([^<]*)', text_))


# --- the table --------------------------------------------------------------------------------


def test_failed_runs_show_their_reason_and_drive_retry_makes_no_new_run(
    login, google, started, db, backup_ctx
):
    admin = login("admin")
    _connect(admin, google)
    failed = _add_run(db, backup_ctx, local_status="failed", local_error="Hết chỗ trống trên ổ")
    drive_failed = _add_run(
        db, backup_ctx, hours_ago=2, drive_status="failed", drive_error="Hết dung lượng Drive"
    )
    _place_file(backup_ctx, drive_failed)
    page = admin.get("/backup").text
    assert "Hết chỗ trống trên ổ" in page and "Lỗi Drive" in page and "Hết dung lượng Drive" in page
    assert f'action="/backup/runs/{drive_failed.id}/retry-drive"' in page
    assert f'action="/backup/runs/{failed.id}/retry-drive"' not in page

    runs_before = db.scalar(text("SELECT count(*) FROM ops.backup_run"))
    admin.post(f"/backup/runs/{drive_failed.id}/retry-drive")
    assert db.scalar(text("SELECT count(*) FROM ops.backup_run")) == runs_before
    request = db.scalars(select(BackupRequest)).one()
    assert (request.action, request.target_run_id, request.to_drive) == (
        "retry_drive",
        drive_failed.id,
        True,
    )
    assert started == [trigger.BACKUP_TASK]


def test_filters_search_and_total(login, google, db, backup_ctx):
    for hours in range(1, 31):
        _add_run(db, backup_ctx, kind="db" if hours % 3 else "app", hours_ago=hours)
    _add_run(db, backup_ctx, kind="full", hours_ago=40, source="deploy", actor="someone")
    admin = login("admin")
    assert "(31)" in admin.get("/backup?size=10").text
    assert "(10)" in admin.get("/backup?kind=app&size=100").text
    assert "(1)" in admin.get("/backup?source=deploy").text
    assert "(1)" in admin.get("/backup?q=someone").text
    assert "Hiển thị 11–20" in admin.get("/backup?size=10&page=2").text


def test_a_backup_only_on_drive_is_listed_once_and_downloads_and_restores(
    login, google, started, db, backup_ctx, tmp_path
):
    admin = login("admin")
    _connect(admin, google)
    payload = b"encrypted-bytes-of-the-backup"
    name = naming.make("full", _database(backup_ctx), datetime.now(UTC) - timedelta(days=3))
    source = tmp_path / name
    source.write_bytes(payload)
    file_id = admin.app.state.drive.upload(source, name)
    admin.app.state.drive_listing.invalidate()  # the page cached the empty list before this
    # Rotated away on this machine, still on Drive (criterion: shown as not on the server).
    run = _add_run(
        db,
        backup_ctx,
        kind="full",
        hours_ago=72,
        file_name=name,
        local_status="rotated",
        drive_status="ok",
        drive_file_id=file_id,
    )
    page = admin.get("/backup").text
    assert "Không có (chỉ trên Drive)" in page and "Đã lên Drive (MD5 khớp)" in page
    assert f'data-restore="{run.id}"' in page
    admin.get("/backup")
    assert (
        db.scalar(text("SELECT count(*) FROM ops.backup_run WHERE file_name = :n"), {"n": name})
        == 1
    )

    resp = admin.get(f"/backup/runs/{run.id}/download")
    assert resp.status_code == 200 and resp.content == payload
    assert (backup_ctx.settings.backup_dirs[0] / name).read_bytes() == payload
    log = db.scalars(select(EventLog).where(EventLog.kind == "backup_download")).one()
    assert (log.actor, log.detail) == ("admin", name)


def test_unknown_drive_files_become_rows_once(login, google, db, backup_ctx, tmp_path):
    admin = login("admin")
    _connect(admin, google)
    name = naming.make("db", _database(backup_ctx), datetime.now(UTC) - timedelta(days=2))
    source = tmp_path / name
    source.write_bytes(b"x" * 40)
    admin.app.state.drive.upload(source, name)
    admin.app.state.drive_listing.invalidate()
    page = admin.get("/backup").text
    assert "Tìm thấy trên Drive" in page and name in page
    admin.app.state.drive_listing.invalidate()
    admin.get("/backup")
    rows = db.scalars(select(BackupRun).where(BackupRun.file_name == name)).all()
    assert len(rows) == 1 and rows[0].source == "drive_found" and rows[0].local_status == "missing"


def test_drive_down_does_not_break_the_page(login, google, db, backup_ctx):
    admin = login("admin")
    _connect(admin, google)
    google.about_error = None

    def broken(request):
        import httpx

        raise httpx.ConnectError("offline")

    import httpx

    admin.app.state.drive._http = httpx.Client(transport=httpx.MockTransport(broken))
    admin.app.state.drive._token = None
    admin.app.state.drive_listing.invalidate()
    run = _add_run(db, backup_ctx, drive_status="ok")
    page = admin.get("/backup")
    assert page.status_code == 200 and "Không có mạng tới Google" in page.text
    assert "không kiểm tra được" in page.text and run.file_name in page.text


# --- roles ------------------------------------------------------------------------------------


def test_viewer_sees_rows_but_no_buttons(login, google, db, backup_ctx):
    run = _add_run(db, backup_ctx)
    _place_file(backup_ctx, run)
    page = login("viewer").get("/backup").text
    assert run.file_name in page
    for marker in ("data-restore", "data-delete", "/download", "upload-file", "retry-drive"):
        assert marker not in page


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/backup/runs/{id}/download"),
        ("get", "/backup/runs/{id}/status"),
        ("post", "/backup/runs/{id}/verify"),
        ("post", "/backup/runs/{id}/retry-drive"),
        ("post", "/backup/runs/{id}/delete"),
        ("post", "/backup/runs/{id}/restore"),
        ("get", "/backup/restoring/1"),
        ("get", "/backup/restoring/1/status"),
    ],
)
def test_viewer_is_blocked_everywhere_else(login, google, started, db, backup_ctx, method, path):
    run = _add_run(db, backup_ctx)
    _place_file(backup_ctx, run)
    client = login("viewer")
    kwargs = {"headers": {"x-autosave": "1"}}
    resp = getattr(client, method)(path.format(id=run.id), **kwargs)
    assert resp.status_code in (303, 403) and started == []
    assert (backup_ctx.settings.backup_dirs[0] / run.file_name).exists()
    assert db.scalars(select(BackupRequest)).all() == []


def test_viewer_cannot_upload(login, backup_ctx):
    resp = login("viewer").post("/backup/upload", content=b"abc", headers={"x-autosave": "1"})
    assert resp.status_code == 403


# --- verify, status ---------------------------------------------------------------------------


def test_verify_queues_a_request(login, google, started, db, backup_ctx):
    run = _add_run(db, backup_ctx)
    _place_file(backup_ctx, run)
    login("admin").post(f"/backup/runs/{run.id}/verify")
    request = db.scalars(select(BackupRequest)).one()
    assert (request.action, request.target_run_id) == ("verify", run.id)
    assert started == [trigger.BACKUP_TASK]


def test_run_status_json_has_labels_and_no_error_text(login, db, backup_ctx):
    run = _add_run(db, backup_ctx, local_status="failed", local_error="SECRET-DETAIL c:\\path")
    body = login("admin").get(f"/backup/runs/{run.id}/status", headers={"x-autosave": "1"})
    assert body.json()["local"] == "Lỗi" and body.json()["finished"] is True
    assert "SECRET-DETAIL" not in body.text
    running = _add_run(db, backup_ctx, hours_ago=2, local_status="running")
    got = login("admin").get(f"/backup/runs/{running.id}/status", headers={"x-autosave": "1"})
    assert got.json() == {
        "ok": True,
        "local": "Đang chạy",
        "drive": "Không yêu cầu",
        "finished": False,
    }


# --- delete -----------------------------------------------------------------------------------


def test_delete_rules_and_log(login, google, db, backup_ctx):
    admin = login("admin")
    newest = _add_run(db, backup_ctx, hours_ago=1)
    older = _add_run(db, backup_ctx, hours_ago=5)
    for run in (newest, older):
        _place_file(backup_ctx, run)
        _place_file(backup_ctx, run, place=1)
    refused = admin.post(
        f"/backup/runs/{newest.id}/delete", data={"where": "local"}, follow_redirects=True
    )
    assert "mới nhất" in _flashes(refused.text)
    assert (backup_ctx.settings.backup_dirs[0] / newest.file_name).exists()

    done = admin.post(
        f"/backup/runs/{older.id}/delete", data={"where": "local"}, follow_redirects=True
    )
    assert "Đã xóa" in _flashes(done.text)
    for folder in backup_ctx.settings.backup_dirs:
        assert not (folder / older.file_name).exists()
    db.refresh(older)
    assert (older.local_status, older.deleted_by) == ("deleted", "admin")
    assert (
        db.scalars(select(EventLog).where(EventLog.kind == "backup_delete")).one().actor == "admin"
    )
    assert older.file_name in admin.get("/backup").text  # the row stays as a log


def test_the_safety_backup_of_the_latest_restore_is_kept(login, google, db, backup_ctx):
    admin = login("admin")
    _add_run(db, backup_ctx, hours_ago=1)
    safety = _add_run(db, backup_ctx, hours_ago=3, source="safety")
    _add_run(db, backup_ctx, hours_ago=2)
    db.add(
        BackupRequest(
            action="restore", requested_by="admin", status="done", safety_run_id=safety.id
        )
    )
    db.flush()
    resp = admin.post(
        f"/backup/runs/{safety.id}/delete", data={"where": "local"}, follow_redirects=True
    )
    assert "bản an toàn" in _flashes(resp.text)
    db.refresh(safety)
    assert safety.deleted_at is None


def test_delete_on_drive_needs_a_connection(login, google, db, backup_ctx):
    admin = login("admin")
    _add_run(db, backup_ctx, hours_ago=1)
    older = _add_run(db, backup_ctx, hours_ago=5)
    resp = admin.post(
        f"/backup/runs/{older.id}/delete", data={"where": "drive"}, follow_redirects=True
    )
    assert "Chưa kết nối Google Drive" in _flashes(resp.text)


# --- restore dialog server side ---------------------------------------------------------------


def _production(client, run, **fields):
    data = {"mode": "production", "password": "admin-password", "confirm_name": run.file_name}
    data.update(fields)
    return client.post(f"/backup/runs/{run.id}/restore", data=data, follow_redirects=False)


def test_drill_request_from_the_dialog(login, google, started, db, backup_ctx):
    run = _add_run(db, backup_ctx)
    _place_file(backup_ctx, run)
    resp = login("admin").post(f"/backup/runs/{run.id}/restore", data={"mode": "drill"})
    assert resp.status_code == 200
    assert db.scalars(select(BackupRequest)).one().action == "drill"
    assert started == [trigger.BACKUP_TASK]


def test_production_restore_needs_password_and_name(login, google, started, db, backup_ctx):
    admin = login("admin")
    run = _add_run(db, backup_ctx, manifest={"alembic_revision": "0009_platform_settlement"})
    _place_file(backup_ctx, run)
    wrong_password = _production(admin, run, password="nope")
    assert "Sai mật khẩu" in _flashes(admin.get("/backup").text)
    assert wrong_password.status_code == 303
    _production(admin, run, confirm_name="other-file.7z")
    assert "Tên file gõ lại không khớp" in _flashes(admin.get("/backup").text)
    assert started == [] and db.scalars(select(BackupRequest)).all() == []


def test_production_restore_queues_and_starts_the_restore_task(
    login, google, started, db, backup_ctx
):
    run = _add_run(db, backup_ctx, manifest={"alembic_revision": "0009_platform_settlement"})
    admin = login("admin")
    resp = _production(admin, run)
    request = db.scalars(select(BackupRequest)).one()
    assert resp.headers["location"] == f"/backup/restoring/{request.id}"
    assert (request.action, request.target_run_id, request.result) == (
        "restore",
        run.id,
        {"force": False},
    )
    assert started == [trigger.RESTORE_TASK]
    assert "Đang phục hồi" in admin.get(resp.headers["location"]).text
    status = admin.get(f"/backup/restoring/{request.id}/status", headers={"x-autosave": "1"})
    assert status.json()["status"] == "pending"
    _production(admin, run)  # a second request while one waits is refused
    assert "Đang có yêu cầu phục hồi khác" in _flashes(admin.get("/backup").text)
    assert len(db.scalars(select(BackupRequest)).all()) == 1


def test_restore_task_that_cannot_start_fails_the_request_at_once(
    login, google, db, backup_ctx, monkeypatch
):
    monkeypatch.setattr(trigger, "start_task", lambda name: False)
    run = _add_run(db, backup_ctx, manifest={"alembic_revision": "0009_platform_settlement"})
    admin = login("admin")
    _production(admin, run)
    request = db.scalars(select(BackupRequest)).one()
    assert request.status == "failed" and "shoponline-restore" in request.message
    assert "Không chạy được tác vụ phục hồi" in _flashes(admin.get("/backup").text)


def test_newer_backup_cannot_be_restored(login, google, started, db, backup_ctx):
    run = _add_run(db, backup_ctx, manifest={"alembic_revision": "9999_from_the_future"})
    _place_file(backup_ctx, run)
    admin = login("admin")
    page = admin.get("/backup").text
    assert 'data-block="Bản từ phiên bản mới hơn' in page
    _production(admin, run)
    assert "phiên bản mới hơn" in _flashes(admin.get("/backup").text)
    assert db.scalars(select(BackupRequest)).all() == [] and started == []


def test_app_backup_has_no_restore_button(login, google, started, db, backup_ctx):
    run = _add_run(db, backup_ctx, kind="app")
    _place_file(backup_ctx, run)
    admin = login("admin")
    assert f'data-restore="{run.id}"' not in admin.get("/backup").text
    admin.post(f"/backup/runs/{run.id}/restore", data={"mode": "drill"})
    assert db.scalars(select(BackupRequest)).all() == []


def test_other_active_users_or_old_backups_need_the_confirmation_box(
    login, google, started, db, backup_ctx
):
    admin = login("admin")
    run = _add_run(db, backup_ctx, manifest=None)
    _production(admin, run)
    assert "không có manifest" in _flashes(admin.get("/backup").text)
    assert db.scalars(select(BackupRequest)).all() == []
    assert _production(admin, run, force="1").status_code == 303
    assert db.scalars(select(BackupRequest)).one().result == {"force": True}

    db.execute(text("DELETE FROM ops.backup_request"))
    modern = _add_run(
        db, backup_ctx, hours_ago=3, manifest={"alembic_revision": "0009_platform_settlement"}
    )
    db.execute(text("UPDATE ops.app_user SET last_seen_at = now() WHERE username = 'viewer'"))
    _production(admin, modern)
    assert "người dùng khác" in _flashes(admin.get("/backup").text)
    assert db.scalars(select(BackupRequest)).all() == []


# --- upload -----------------------------------------------------------------------------------


def _upload(client, data: bytes, name: str):
    return client.post(
        "/backup/upload",
        content=data,
        headers={"x-file-name": quote(name), "x-autosave": "1"},
    )


def _real_backup(ctx) -> runner.Outcome:
    outcome = runner.run_now(ctx, "db", "manual", "admin")
    assert outcome.exit_code == runner.EXIT_OK
    return outcome


def _forget(ctx, outcome):
    """Pretend the file came from elsewhere: no row and no file on this machine."""
    with ctx.session_factory() as db:
        db.execute(text("DELETE FROM ops.backup_run"))
        db.commit()
    data = outcome.archive_path.read_bytes()
    for folder in ctx.settings.backup_dirs:
        (folder / outcome.file_name).unlink(missing_ok=True)
    return data


def test_a_good_backup_can_be_uploaded(login, google, db, backup_ctx):
    outcome = _real_backup(backup_ctx)
    data = _forget(backup_ctx, outcome)
    admin = login("admin")
    resp = _upload(admin, data, outcome.file_name)
    assert resp.status_code == 200 and resp.json()["ok"], resp.text
    run = db.scalars(select(BackupRun)).one()
    assert (run.source, run.kind, run.local_status, run.actor) == ("upload", "db", "ok", "admin")
    assert (backup_ctx.settings.backup_dirs[0] / outcome.file_name).read_bytes() == data
    assert run.manifest["tables"] and run.sha256
    assert "Tải lên" in admin.get("/backup").text
    assert db.scalars(select(EventLog).where(EventLog.kind == "backup_upload")).one()
    again = _upload(admin, data, outcome.file_name)  # the same name is already there
    assert again.status_code == 422 and "Đã có" in again.json()["message"]


def _nothing_left_behind(ctx):
    assert (
        not any(ctx.settings.backup_dirs[0].glob("*"))
        if ctx.settings.backup_dirs[0].exists()
        else True
    )
    work = ctx.settings.backup_work_dir
    assert not work.exists() or not any(work.iterdir())


def test_wrong_password_file_is_refused_and_leaves_nothing(
    login, db, backup_ctx, seven_zip, tmp_path
):  # noqa: F811
    src = tmp_path / "src"
    src.mkdir()
    (src / "database.dump").write_bytes(b"x")
    foreign = tmp_path / "foreign.7z"
    SevenZip(seven_zip, "another-password").create(foreign, ["database.dump"], cwd=src)
    resp = _upload(login("admin"), foreign.read_bytes(), "shoponline-db-x-20261101-230000.7z")
    assert resp.status_code == 422
    _nothing_left_behind(backup_ctx)
    assert db.scalars(select(BackupRun)).all() == []


def test_changed_byte_is_refused(login, db, backup_ctx):
    outcome = _real_backup(backup_ctx)
    data = bytearray(_forget(backup_ctx, outcome))
    data[len(data) // 2] ^= 0xFF
    resp = _upload(login("admin"), bytes(data), outcome.file_name)
    assert resp.status_code == 422
    _nothing_left_behind(backup_ctx)
    assert db.scalars(select(BackupRun)).all() == []


def test_unencrypted_file_is_refused(login, db, backup_ctx, seven_zip, tmp_path):  # noqa: F811
    import subprocess

    (tmp_path / "a.dump").write_bytes(b"plain")
    plain = tmp_path / "plain.7z"
    subprocess.run(
        [str(seven_zip), "a", str(plain), "a.dump"], cwd=tmp_path, check=True, capture_output=True
    )
    resp = _upload(login("admin"), plain.read_bytes(), "shoponline-db-x-20261101-230000.7z")
    assert resp.status_code == 422 and "không mã hóa" in resp.json()["message"]
    _nothing_left_behind(backup_ctx)


def test_oversized_or_unsized_bodies_are_refused_before_writing(login, backup_ctx, monkeypatch):
    from shoponline.backup import manage

    monkeypatch.setattr(manage, "MAX_UPLOAD", 10)
    admin = login("admin")
    big = _upload(admin, b"x" * 11, "shoponline-db-x-20261101-230000.7z")
    assert big.status_code == 413
    empty = _upload(admin, b"", "shoponline-db-x-20261101-230000.7z")
    assert empty.status_code == 411
    _nothing_left_behind(backup_ctx)


def test_not_enough_disk_refuses_the_upload(login, backup_ctx, monkeypatch):
    import shutil
    from collections import namedtuple

    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda path: usage(100, 100, 1))
    resp = _upload(login("admin"), b"x" * 10, "shoponline-db-x-20261101-230000.7z")
    assert resp.status_code == 507
    _nothing_left_behind(backup_ctx)


# --- outcome banner ---------------------------------------------------------------------------


def test_restore_outcome_is_shown_once_to_the_first_admin(login, backup_ctx):
    settings = backup_ctx.settings
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / restore.STATUS_FILE).write_text(
        json.dumps(
            {"state": "rolled_back", "message": "Lý do: migration lỗi", "finished_at": "2026-11-23"}
        ),
        encoding="utf-8",
    )
    assert "Đã lùi lại" not in login("viewer").get("/backup").text
    first = login("admin").get("/backup").text
    assert "Đã lùi lại" in first and "migration lỗi" in first
    assert "Đã lùi lại" not in login("admin").get("/backup").text
    assert restore.read_status(settings)["banner_shown_by"] == "admin"
