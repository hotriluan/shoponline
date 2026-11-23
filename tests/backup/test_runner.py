"""Real backups of the test database with 7-Zip and pg_dump: contents, places, lock, queue."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text

from shoponline.backup import naming, pgtools, runner
from shoponline.backup.sevenzip import SevenZip
from shoponline.clock import VIETNAM
from shoponline.db.models import BackupRequest, BackupRun
from tests.backup.conftest import PASSWORD


def _runs(ctx) -> list[BackupRun]:
    with ctx.session_factory() as db:
        return list(db.scalars(select(BackupRun).order_by(BackupRun.id)))


def _extract(ctx, path, dest):
    SevenZip(ctx.seven_zip, PASSWORD).extract(path, dest)
    return dest


def test_full_backup_contents_and_manifest(backup_ctx, tmp_path):
    outcome = runner.run_now(backup_ctx, "full", "manual", "admin")
    assert outcome.exit_code == runner.EXIT_OK
    for place in backup_ctx.settings.backup_dirs:
        assert (place / outcome.file_name).is_file()
    out = _extract(backup_ctx, outcome.archive_path, tmp_path / "out")
    names = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    assert {"manifest.json", "database.dump", "source.bundle", "env"} <= names
    assert "data/uploads/orders.xlsx" in names
    assert "config/sap_screens.yaml" in names
    assert not any(
        n.startswith(("data/logs", "data/robot-work", "data/backup-work")) for n in names
    )
    env_text = (out / "env").read_text(encoding="utf-8")
    assert "SHOPONLINE_BACKUP_PASSWORD" not in env_text
    assert "SHOPONLINE_SECRET_KEY" in env_text
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "full" and manifest["alembic_revision"]
    assert manifest["tables"]["platform_setting"] == 3
    assert set(manifest["parts"]) == names - {"manifest.json"}
    (run,) = _runs(backup_ctx)
    assert (run.kind, run.source, run.actor, run.local_status) == ("full", "manual", "admin", "ok")
    assert run.sha256 and run.size_bytes == outcome.archive_path.stat().st_size
    assert run.manifest["tables"] == manifest["tables"]


def test_app_backup_has_no_database(backup_ctx, tmp_path):
    outcome = runner.run_now(backup_ctx, "app", "manual")
    out = _extract(backup_ctx, outcome.archive_path, tmp_path / "out")
    assert not (out / "database.dump").exists()
    assert (out / "source.bundle").is_file()


def test_archive_needs_the_password_to_list(backup_ctx, seven_zip):
    outcome = runner.run_now(backup_ctx, "db", "manual")
    SevenZip(seven_zip, PASSWORD).require_encrypted(outcome.archive_path)
    assert outcome.file_name.startswith("shoponline-db-")


def test_one_broken_place_gives_exit_2_and_keeps_its_old_files(backup_ctx, tmp_path):
    broken = tmp_path / "broken"
    broken.write_text("a file where a folder should be", encoding="utf-8")
    settings = backup_ctx.settings
    good = settings.backup_dirs[0]
    good.mkdir(parents=True)
    now = datetime.now(UTC)
    database = pgtools.database_name(settings.database_url)
    old = [naming.make("db", database, now - timedelta(days=d)) for d in range(1, 17)]
    for name in old:
        (good / name).write_bytes(b"old")
    backup_ctx.settings = type(settings)(**{**settings.__dict__, "backup_dirs": (good, broken)})
    outcome = runner.run_now(backup_ctx, "db", "manual")
    assert outcome.exit_code == runner.EXIT_PARTIAL
    (run,) = _runs(backup_ctx)
    assert run.local_status == "partial" and "broken" in run.local_error
    kept = [p.name for p in good.iterdir() if p.name.startswith(f"shoponline-db-{database}")]
    assert len(kept) == 15 and outcome.file_name in kept


def test_lock_busy_gives_exit_3_and_no_backup(backup_ctx):
    with runner.backup_lock(backup_ctx.engine) as held:
        assert held is not None
        assert runner.run_now(backup_ctx, "db", "manual").exit_code == runner.EXIT_LOCKED
        assert runner.if_due(backup_ctx) == runner.EXIT_LOCKED
        with backup_ctx.session_factory() as db:
            assert runner.lock_is_held(db)
    assert _runs(backup_ctx) == []


def test_deploy_waits_only_so_long(backup_ctx):
    with runner.backup_lock(backup_ctx.engine) as held:
        assert held is not None
        with runner.backup_lock(backup_ctx.engine, timedelta(milliseconds=200)) as second:
            assert second is None


def test_missing_password_fails_and_is_recorded(backup_ctx):
    settings = backup_ctx.settings
    backup_ctx.settings = type(settings)(**{**settings.__dict__, "backup_password": ""})
    outcome = runner.run_now(backup_ctx, "db", "manual")
    assert outcome.exit_code == runner.EXIT_NONE
    (run,) = _runs(backup_ctx)
    assert run.local_status == "failed" and "SHOPONLINE_BACKUP_PASSWORD" in run.local_error


def test_orphan_running_rows_become_interrupted(backup_ctx):
    with backup_ctx.session_factory() as db:
        db.add(BackupRun(kind="db", source="manual", actor="x", file_name="f.7z"))
        db.add(BackupRequest(action="backup", kind="db", requested_by="x", status="running"))
        db.commit()
    runner.run_now(backup_ctx, "db", "manual")
    runs = _runs(backup_ctx)
    assert runs[0].local_status == "interrupted" and runs[1].local_status == "ok"
    with backup_ctx.session_factory() as db:
        assert db.scalar(select(BackupRequest.status)) == "interrupted"


def test_if_due_handles_requests_then_friday_schedule(backup_ctx):
    friday = datetime(2026, 11, 27, 16, 45, tzinfo=VIETNAM)
    backup_ctx.now = lambda: friday
    with backup_ctx.session_factory() as db:
        db.add(BackupRequest(action="backup", kind="app", requested_by="admin", to_drive=True))
        db.commit()
    assert runner.if_due(backup_ctx) == runner.EXIT_OK
    runs = _runs(backup_ctx)
    assert [(r.kind, r.source) for r in runs] == [
        ("app", "manual"),
        ("db", "schedule"),
        ("full", "schedule"),
    ]
    assert runs[0].actor == "admin" and runs[0].drive_status == "not_connected"
    with backup_ctx.session_factory() as db:
        req = db.scalar(select(BackupRequest))
        assert req.status == "done" and req.result == {"run_id": runs[0].id}
    # Nothing is due right after.
    assert runner.if_due(backup_ctx) == runner.EXIT_OK
    assert len(_runs(backup_ctx)) == 3


def test_failed_schedule_retries_after_an_hour(backup_ctx):
    now = datetime(2026, 11, 24, 17, 0, tzinfo=VIETNAM)
    backup_ctx.now = lambda: now
    with backup_ctx.session_factory() as db:
        db.execute(text("UPDATE ops.backup_settings SET full_weekday = 0"))  # full ran Monday
        for kind, status, at in (
            ("full", "ok", now - timedelta(minutes=10)),
            ("db", "failed", now - timedelta(minutes=20)),
        ):
            db.add(
                BackupRun(
                    kind=kind,
                    source="schedule",
                    actor="system",
                    file_name="x.7z",
                    local_status=status,
                    started_at=at,
                )
            )
        db.commit()
        last = runner.last_scheduled_success(db, now)
    assert last["db"] == now - timedelta(minutes=20)
    later = now + timedelta(hours=1)
    with backup_ctx.session_factory() as db:
        assert runner.last_scheduled_success(db, later)["db"] is None
