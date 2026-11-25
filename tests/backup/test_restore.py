"""Restore: unpacking checks, version refusal, replacing schema public while ops survives, the way
back when a step fails, stale requests. Real pg_dump, pg_restore, 7-Zip and Alembic."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text

from shoponline.backup import archive, maintenance, naming, pgtools, restore, runner, staging
from shoponline.backup.sevenzip import SevenZip
from shoponline.db.models import BackupRequest, BackupRun
from tests.backup.conftest import PASSWORD
from tests.conftest import ROOT


@pytest.fixture
def services(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(restore, "service_control", lambda ctx, action: calls.append(action))
    return calls


@pytest.fixture
def alembic_cfg(backup_ctx):
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["database_url"] = backup_ctx.settings.database_url
    return cfg


def _count(ctx, sql: str, **params) -> int:
    with ctx.engine.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _make_backup(ctx, kind="db") -> runner.Outcome:
    outcome = runner.run_now(ctx, kind, "manual", "admin")
    assert outcome.exit_code == runner.EXIT_OK
    return outcome


def _production(ctx, target, **kwargs):
    with runner.backup_lock(ctx.engine) as lock:
        assert lock is not None
        return restore.production(ctx, target, "admin", **kwargs)


def _legacy_archive(ctx, tmp_path, alembic_cfg):
    """A backup made the old way: one <db>-<stamp>.dump, taken when the schema was at 0009."""
    command.downgrade(alembic_cfg, "0009_platform_settlement")
    database = pgtools.database_name(ctx.settings.database_url)
    dump = tmp_path / f"{database}-20261101-230000.dump"
    pgtools.run(ctx.pg_bin, "pg_dump", ctx.settings.database_url, ["-Fc", "-f", str(dump)])
    command.upgrade(alembic_cfg, "head")
    folder = ctx.settings.backup_dirs[0]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"shoponline-{database}-20261101-230000.7z"
    SevenZip(ctx.seven_zip, PASSWORD).create(path, [dump.name], cwd=tmp_path)
    return path


# --- refusals before anything is touched ------------------------------------------------------


def test_newer_backup_is_refused_before_services_stop(backup_ctx, services, monkeypatch):
    outcome = _make_backup(backup_ctx)
    monkeypatch.setattr(restore, "known_revisions", lambda: {"0001_initial"})
    with pytest.raises(restore.RestoreRefused, match="phiên bản mới hơn"):
        _production(backup_ctx, outcome.file_name)
    assert services == []
    assert maintenance.read(backup_ctx.settings) is None


def test_check_version_accepts_old_and_head(backup_ctx):
    known = restore._known_revisions(ROOT)
    assert "0009_platform_settlement" in known
    for revision in ("0009_platform_settlement", "0011_drive_connection", "0012_sales_return"):
        restore.check_version(
            backup_ctx,
            restore.mf.Manifest("db", "t", "now", "x", alembic_revision=revision),
        )
    with pytest.raises(restore.RestoreRefused):
        restore.check_version(
            backup_ctx, restore.mf.Manifest("db", "t", "now", "x", alembic_revision="9999_future")
        )


def test_deploy_in_progress_blocks_a_restore(backup_ctx, services):
    outcome = _make_backup(backup_ctx)
    maintenance.write(backup_ctx.settings, "deploy")
    with pytest.raises(restore.RestoreRefused, match="triển khai"):
        _production(backup_ctx, outcome.file_name)
    assert services == []


def test_unencrypted_archive_is_refused(backup_ctx, services, tmp_path, seven_zip):
    import subprocess

    (tmp_path / "plain.dump").write_bytes(b"not encrypted")
    folder = backup_ctx.settings.backup_dirs[0]
    folder.mkdir(parents=True)
    name = naming.make("db", pgtools.database_name(backup_ctx.settings.database_url))
    subprocess.run(
        [str(seven_zip), "a", str(folder / name), "plain.dump"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    with pytest.raises(restore.RestoreRefused, match="không mã hóa"):
        _production(backup_ctx, name, force=True)
    assert services == []


def test_archive_with_one_changed_byte_is_refused(backup_ctx, services):
    outcome = _make_backup(backup_ctx, "full")
    data = bytearray(outcome.archive_path.read_bytes())
    data[len(data) // 3] ^= 0xFF
    outcome.archive_path.write_bytes(bytes(data))
    with pytest.raises(restore.RestoreRefused):
        _production(backup_ctx, str(outcome.archive_path))
    assert services == []


def test_other_active_users_need_force(backup_ctx, services):
    outcome = _make_backup(backup_ctx)
    with backup_ctx.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ops.app_user (username, password_hash, role, last_seen_at) "
                "VALUES ('restore-test-colleague', 'x', 'viewer', now())"
            )
        )
    try:
        with pytest.raises(restore.RestoreRefused, match="người dùng khác"):
            _production(backup_ctx, outcome.file_name)
        assert services == []
        assert _production(backup_ctx, outcome.file_name, force=True).status == "done"
    finally:
        with backup_ctx.engine.begin() as conn:
            conn.execute(text("DELETE FROM ops.app_user WHERE username = 'restore-test-colleague'"))


def test_app_backup_cannot_be_restored(backup_ctx, services):
    outcome = _make_backup(backup_ctx, "app")
    with pytest.raises(restore.RestoreRefused, match="Ứng dụng"):
        _production(backup_ctx, outcome.file_name)


# --- a restore that works ---------------------------------------------------------------------


def test_old_backup_without_manifest_restores_then_migrates(
    backup_ctx, services, tmp_path, alembic_cfg
):
    legacy = _legacy_archive(backup_ctx, tmp_path, alembic_cfg)
    # Made after the old backup, so only the live ops tables hold them.
    with backup_ctx.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ops.app_user (username, password_hash, role) "
                "VALUES ('restore-test-keeper', 'x', 'admin')"
            )
        )
    with backup_ctx.session_factory() as db:
        db.add(BackupRun(kind="db", source="manual", actor="old", file_name="kept-row.7z"))
        db.commit()
    try:
        with pytest.raises(restore.RestoreRefused, match="manifest"):
            _production(backup_ctx, legacy.name)  # needs --force
        epoch = _count(backup_ctx, "SELECT session_epoch FROM ops.system_state")
        result = _production(backup_ctx, legacy.name, force=True)
        assert result.status == "done"
        assert services == ["stop", "start"]
        assert (
            _count(backup_ctx, "SELECT version_num = '0012_sales_return' FROM alembic_version")
            is True
        )
        assert (
            _count(
                backup_ctx,
                "SELECT count(*) FROM ops.app_user WHERE username = 'restore-test-keeper'",
            )
            == 1
        )
        assert (
            _count(
                backup_ctx, "SELECT count(*) FROM ops.backup_run WHERE file_name = 'kept-row.7z'"
            )
            == 1
        )
        assert _count(backup_ctx, "SELECT to_regclass('public.app_user') IS NULL") is True
        assert _count(backup_ctx, "SELECT session_epoch FROM ops.system_state") == epoch + 1
        assert maintenance.read(backup_ctx.settings) is None
        with backup_ctx.engine.begin() as conn:  # the application role still owns public
            conn.execute(text("CREATE TABLE public.restore_probe (id int)"))
            conn.execute(text("DROP TABLE public.restore_probe"))
        # A new backup right after a restore inserts into ops.backup_run without key clashes.
        assert runner.run_now(backup_ctx, "db", "manual", "admin").exit_code == runner.EXIT_OK
        status = restore.read_status(backup_ctx.settings)
        assert status["state"] == "done" and status["safety_run_id"]
    finally:
        with backup_ctx.engine.begin() as conn:
            conn.execute(text("DELETE FROM ops.app_user WHERE username = 'restore-test-keeper'"))


def test_full_backup_swaps_data_and_keeps_the_old_aside(backup_ctx, services):
    settings = backup_ctx.settings
    outcome = _make_backup(backup_ctx, "full")
    (settings.data_dir / "uploads" / "orders.xlsx").write_bytes(b"changed after the backup")
    (settings.data_dir / "uploads" / "newer.xlsx").write_bytes(b"made after the backup")
    result = _production(backup_ctx, outcome.file_name)
    assert result.status == "done"
    assert (settings.data_dir / "uploads" / "orders.xlsx").read_bytes() == b"workbook"
    assert not (settings.data_dir / "uploads" / "newer.xlsx").exists()
    aside = next((settings.backup_work_dir).glob("before-restore-*"))
    assert (aside / "uploads" / "newer.xlsx").is_file()
    assert (settings.data_dir / "logs" / "web.log").read_text(encoding="utf-8") == "log line"


# --- the way back -----------------------------------------------------------------------------


def test_failed_migrate_rolls_back_to_the_safety_backup(backup_ctx, services, monkeypatch):
    outcome = _make_backup(backup_ctx)
    with backup_ctx.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO platform_setting (platform, display_name, sap_customer, mode) "
                "VALUES ('ROLLBACK', 'rollback probe', '999', 'manual')"
            )
        )
    seen = {}
    real_restore = restore.restore_public_schema

    def spy(ctx, dump, url, work):
        folder = ctx.settings.backup_dirs[0]
        seen.setdefault("safety_before_restore", list(folder.glob("shoponline-full-*")))
        return real_restore(ctx, dump, url, work)

    calls = {"n": 0}

    def flaky_migrate(url):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("migration blew up")

    monkeypatch.setattr(restore, "restore_public_schema", spy)
    monkeypatch.setattr(restore, "run_migrate", flaky_migrate)
    try:
        result = _production(backup_ctx, outcome.file_name)
        assert result.status == "rolled_back" and "migration blew up" in result.message
        assert seen["safety_before_restore"], "the safety backup must exist before pg_restore"
        assert result.safety_run_id
        assert (
            _count(backup_ctx, "SELECT count(*) FROM platform_setting WHERE platform = 'ROLLBACK'")
            == 1
        ), "public must be what it was before the restore"
        assert services == ["stop", "start"]
        assert maintenance.read(backup_ctx.settings) is None
        with backup_ctx.session_factory() as db:
            run = db.get(BackupRun, result.safety_run_id)
            assert (run.kind, run.source, run.local_status) == ("full", "safety", "ok")
        assert restore.read_status(backup_ctx.settings)["state"] == "rolled_back"
    finally:
        with backup_ctx.engine.begin() as conn:
            conn.execute(text("DELETE FROM platform_setting WHERE platform = 'ROLLBACK'"))


def test_no_safety_backup_means_nothing_is_restored(backup_ctx, services, monkeypatch):
    outcome = _make_backup(backup_ctx)
    monkeypatch.setattr(
        runner, "run_backup", lambda *a, **k: runner.Outcome(runner.EXIT_NONE, message="disk full")
    )
    called = []
    monkeypatch.setattr(restore, "restore_public_schema", lambda *a, **k: called.append(1))
    with pytest.raises(restore.RestoreError, match="an toàn"):
        _production(backup_ctx, outcome.file_name)
    assert called == [] and services == ["stop", "start"]
    assert maintenance.read(backup_ctx.settings) is None


def test_rollback_failure_keeps_the_marker_and_prints_the_command(
    backup_ctx, services, monkeypatch
):
    outcome = _make_backup(backup_ctx)

    def always_fails(url):
        raise RuntimeError("migrate broken")

    monkeypatch.setattr(restore, "run_migrate", always_fails)
    result = _production(backup_ctx, outcome.file_name)
    assert result.status == "failed"
    assert "backup restore" in result.message and "--production" in result.message
    assert maintenance.active(backup_ctx.settings, "restore")
    maintenance.clear(backup_ctx.settings, "restore")


# --- queue ------------------------------------------------------------------------------------


def test_restore_request_older_than_ten_minutes_expires(backup_ctx, services):
    with backup_ctx.session_factory() as db:
        db.add(
            BackupRequest(
                action="restore",
                target_run_id=None,
                requested_by="admin",
                requested_at=datetime.now(UTC) - timedelta(minutes=11),
            )
        )
        db.commit()
    with runner.backup_lock(backup_ctx.engine):
        assert runner.process_requests(backup_ctx, runner.RESTORE_ACTIONS) == []
    with backup_ctx.session_factory() as db:
        assert db.scalar(select(BackupRequest.status)) == "expired"
    assert services == []


def test_queued_restore_runs_through_the_task_path(backup_ctx, services):
    outcome = _make_backup(backup_ctx)
    with backup_ctx.session_factory() as db:
        run = db.scalars(select(BackupRun)).first()
        db.add(BackupRequest(action="restore", target_run_id=run.id, requested_by="admin"))
        db.commit()
    with runner.backup_lock(backup_ctx.engine):
        codes = runner.process_requests(backup_ctx, runner.RESTORE_ACTIONS)
    assert codes == [runner.EXIT_OK]
    with backup_ctx.session_factory() as db:
        req = db.scalar(select(BackupRequest))
        assert req.status == "done" and req.safety_run_id and outcome.file_name in req.message


def test_verify_request_records_the_result(backup_ctx):
    _make_backup(backup_ctx)
    with backup_ctx.session_factory() as db:
        run = db.scalars(select(BackupRun)).first()
        db.add(BackupRequest(action="verify", target_run_id=run.id, requested_by="admin"))
        db.commit()
    with runner.backup_lock(backup_ctx.engine):
        assert runner.process_requests(backup_ctx) == [runner.EXIT_OK]
    with backup_ctx.session_factory() as db:
        run = db.scalars(select(BackupRun)).first()
        assert run.verified_at and run.verify_result.startswith("OK")


# --- drill ------------------------------------------------------------------------------------


def test_drill_compares_rows_and_refuses_the_running_database(backup_ctx):
    outcome = _make_backup(backup_ctx, "full")
    settings = backup_ctx.settings
    same = dataclasses.replace(settings, restore_database_url=settings.database_url)
    drill_ctx = dataclasses.replace(backup_ctx, settings=same)
    with (
        staging.staging_dir(settings.backup_work_dir) as work,
        pytest.raises(restore.RestoreRefused, match="trùng"),
    ):
        restore.drill(drill_ctx, restore.prepare(backup_ctx, outcome.archive_path, work))

    # The test role cannot create a scratch database, so the drill target is the test database
    # itself while the "running" database named in settings is another one.
    other = settings.database_url.rsplit("/", 1)[0] + "/not_the_running_one"
    drill_settings = dataclasses.replace(
        settings, database_url=other, restore_database_url=settings.database_url
    )
    ctx = dataclasses.replace(backup_ctx, settings=drill_settings)
    with staging.staging_dir(settings.backup_work_dir) as work:
        prep = restore.prepare(ctx, outcome.archive_path, work)
        result = restore.drill(ctx, prep)
    assert result["ok"] and result["diff"] == {}
    assert result["revision"] == "0012_sales_return"
    assert archive.DUMP in prep.manifest.parts

    # A manifest that disagrees with what was restored shows up as a difference.
    prep.manifest.tables["platform_setting"] += 1
    assert restore.compare_counts(settings.database_url, prep.manifest.tables) == {
        "platform_setting": (4, 3)
    }


def test_db_backup_carries_the_accounting_files_and_a_restore_puts_back_the_missing_ones(
    backup_ctx, services, tmp_path
):
    settings = backup_ctx.settings
    settings.export_dir.mkdir(parents=True, exist_ok=True)
    lost = settings.export_dir / "20261120-101010-accounting_file-aaaa1111.xlsx"
    kept = settings.export_dir / "20261121-101010-accounting_file-bbbb2222.xlsx"
    other = settings.export_dir / "20261121-111111-order_file-cccc3333.xlsx"
    word = settings.export_dir / "20261122-101010-invoice_adjustment-dddd4444.docx"
    request = settings.export_dir / "20261122-101010-return_request-eeee5555.xlsx"
    for path, body in (
        (lost, b"lost"),
        (kept, b"kept"),
        (other, b"order"),
        (word, b"word"),
        (request, b"request"),
    ):
        path.write_bytes(body)
    kinds = {
        lost: "accounting_file",
        kept: "accounting_file",
        other: "order_file",
        word: "invoice_adjustment",
        request: "return_request",
    }
    with backup_ctx.engine.begin() as conn:
        for path, kind in kinds.items():
            conn.execute(
                text(
                    "INSERT INTO generated_file (kind, file_name, stored_path, sha256, created_by)"
                    " VALUES (:kind, :name, :path, :sha, 't')"
                ),
                {"kind": kind, "name": path.name, "path": str(path), "sha": "0" * 64},
            )
    try:
        outcome = _make_backup(backup_ctx, "db")
        out = tmp_path / "out"
        SevenZip(backup_ctx.seven_zip, PASSWORD).extract(outcome.archive_path, out)
        packed = {p.name for p in (out / archive.ACCOUNTING).iterdir()}
        assert packed == {lost.name, kept.name, word.name, request.name}

        lost.unlink()
        word.unlink()
        kept.write_bytes(b"kept, edited after the backup")
        result = _production(backup_ctx, outcome.file_name)

        assert result.status == "done"
        assert lost.read_bytes() == b"lost"
        assert word.read_bytes() == b"word"
        assert kept.read_bytes() == b"kept, edited after the backup"
    finally:
        with backup_ctx.engine.begin() as conn:
            conn.execute(text("DELETE FROM generated_file WHERE created_by = 't'"))
