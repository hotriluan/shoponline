"""Loading a migration bundle into a new, empty installation, and fetching it from Drive."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from shoponline.backup import naming, pgtools, restore, runner
from shoponline.web.auth import authenticate, set_user


def _sql(ctx, sql: str, **params):
    with ctx.engine.begin() as conn:
        return conn.execute(text(sql), params)


def _scalar(ctx, sql: str, **params):
    with ctx.engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


@pytest.fixture
def bundle(backup_ctx):
    """A full backup of this installation with one web account, then the installation is
    turned into a 'new machine': no accounts, a different schedule, edited .env, empty data."""
    with Session(backup_ctx.engine) as db:
        set_user(db, "bundle-admin", "bundle-password", "admin")
        db.commit()
    _sql(backup_ctx, "UPDATE ops.backup_settings SET keep_db = 15")
    outcome = runner.run_now(backup_ctx, "full", "migration", "admin")
    assert outcome.exit_code == runner.EXIT_OK

    settings = backup_ctx.settings
    _sql(backup_ctx, "DELETE FROM ops.app_user WHERE username = 'bundle-admin'")
    _sql(backup_ctx, "UPDATE ops.backup_settings SET keep_db = 77")
    _sql(
        backup_ctx,
        "INSERT INTO ops.drive_connection (id, client_id) VALUES (1, 'this-machines-client') "
        "ON CONFLICT (id) DO UPDATE SET client_id = EXCLUDED.client_id",
    )
    (settings.data_dir / "uploads" / "orders.xlsx").unlink()
    env = backup_ctx.repo_root / ".env"
    env.write_text(
        "SHOPONLINE_BACKUP_PASSWORD=this-machine-password\n"
        "SHOPONLINE_WEB_HOST=127.0.0.1\n"
        "SHOPONLINE_OWN_LINE=keep-me\n",
        encoding="utf-8",
    )
    yield outcome
    _sql(backup_ctx, "DELETE FROM ops.app_user WHERE username = 'bundle-admin'")
    _sql(backup_ctx, "UPDATE ops.drive_connection SET client_id = NULL")


def test_new_machine_takes_accounts_schedule_data_and_env(backup_ctx, bundle):
    report = restore.new_machine(backup_ctx, bundle.file_name, web_host="10.0.0.5")
    assert report["kind"] == "full"
    assert sorted(report["ops_copied"]) == ["app_user", "backup_settings"]

    with Session(backup_ctx.engine) as db:
        assert authenticate(db, "bundle-admin", "bundle-password") is not None
        # The account's id sequence moved past the restored rows: a new account can be added.
        set_user(db, "second-admin", "second-password", "viewer")
        db.commit()
    _sql(backup_ctx, "DELETE FROM ops.app_user WHERE username = 'second-admin'")
    assert _scalar(backup_ctx, "SELECT keep_db FROM ops.backup_settings") == 15
    assert _scalar(backup_ctx, "SELECT client_id FROM ops.drive_connection") == (
        "this-machines-client"
    )  # the Drive connection of the new machine is its own
    assert (backup_ctx.settings.data_dir / "uploads" / "orders.xlsx").read_bytes() == b"workbook"
    assert _scalar(backup_ctx, "SELECT version_num FROM alembic_version") == "0011_drive_connection"

    lines = (backup_ctx.repo_root / ".env").read_text(encoding="utf-8").splitlines()
    assert "SHOPONLINE_OWN_LINE=keep-me" in lines  # a line the machine has is never overwritten
    assert "SHOPONLINE_BACKUP_PASSWORD=this-machine-password" in lines
    assert "SHOPONLINE_WEB_HOST=10.0.0.5" in lines and "SHOPONLINE_WEB_HOST=127.0.0.1" not in lines
    assert any(line.startswith("SHOPONLINE_SECRET_KEY=") for line in lines)  # filled from bundle
    assert set(report["env_set"]) >= {"SHOPONLINE_SECRET_KEY", "SHOPONLINE_WEB_HOST"}


def test_a_database_with_orders_is_refused_unless_forced(backup_ctx, bundle, monkeypatch):
    monkeypatch.setattr(restore, "business_rows", lambda url: 5)
    with pytest.raises(restore.RestoreRefused, match="đã có đơn hàng"):
        restore.new_machine(backup_ctx, bundle.file_name)
    assert (
        _scalar(backup_ctx, "SELECT count(*) FROM ops.app_user WHERE username = 'bundle-admin'")
        == 0
    )
    assert restore.new_machine(backup_ctx, bundle.file_name, force=True)["kind"] == "full"


def test_business_rows_is_zero_on_an_empty_database(backup_ctx):
    assert restore.business_rows(backup_ctx.settings.database_url) == 0


def test_an_application_backup_is_not_a_bundle(backup_ctx):
    outcome = runner.run_now(backup_ctx, "app", "manual", "admin")
    with pytest.raises(restore.RestoreRefused, match="Ứng dụng"):
        restore.new_machine(backup_ctx, outcome.file_name)


def test_newer_bundle_is_refused(backup_ctx, bundle, monkeypatch):
    monkeypatch.setattr(restore, "known_revisions", lambda: {"0001_initial"})
    with pytest.raises(restore.RestoreRefused, match="phiên bản mới hơn"):
        restore.new_machine(backup_ctx, bundle.file_name)


def test_wrong_password_bundle_is_refused(backup_ctx, bundle):
    ctx = restore.runner.Context(
        **{**backup_ctx.__dict__, "settings": _with_password(backup_ctx.settings, "wrong-password")}
    )
    with pytest.raises(restore.RestoreRefused):
        restore.new_machine(ctx, bundle.file_name)


def _with_password(settings, password: str):
    import dataclasses

    return dataclasses.replace(settings, backup_password=password)


# --- .env merge -------------------------------------------------------------------------------


def test_merge_env_never_overwrites_and_skips_the_backup_password(tmp_path):
    own = tmp_path / ".env"
    bundle = tmp_path / "bundle-env"
    own.write_text("A=own\n# C=commented\n", encoding="utf-8")
    bundle.write_text(
        "A=from-bundle\nB=from-bundle\nC=from-bundle\nSHOPONLINE_BACKUP_PASSWORD=secret\n",
        encoding="utf-8",
    )
    changed = restore.merge_env(own, bundle, None)
    assert sorted(changed) == ["B", "C"]
    text_ = own.read_text(encoding="utf-8")
    assert "A=own" in text_ and "A=from-bundle" not in text_
    assert "B=from-bundle" in text_ and "secret" not in text_


def test_merge_env_creates_the_file_and_sets_the_host(tmp_path):
    own = tmp_path / ".env"
    assert restore.merge_env(own, tmp_path / "absent", "192.168.1.9") == ["SHOPONLINE_WEB_HOST"]
    assert own.read_text(encoding="utf-8") == "SHOPONLINE_WEB_HOST=192.168.1.9\n"


# --- fetching the latest bundle from Drive ----------------------------------------------------


class FakeDrive:
    def __init__(self, files: dict[str, bytes], connected: bool = True):
        self.files, self._connected = files, connected

    def connected(self):
        return self._connected

    def list_backups(self):
        return [{"name": n, "id": f"id-{n}"} for n in self.files]

    def download(self, file_id, dest):
        dest.write_bytes(self.files[file_id.removeprefix("id-")])


def test_fetch_latest_picks_the_newest_of_the_kind(backup_ctx, tmp_path):
    now = datetime.now(UTC)
    database = pgtools.database_name(backup_ctx.settings.database_url)
    old_full = naming.make("full", database, now - timedelta(days=9))
    new_full = naming.make("full", database, now - timedelta(days=2))
    newer_db = naming.make("db", database, now - timedelta(hours=1))
    backup_ctx.drive = FakeDrive({old_full: b"old", new_full: b"new", newer_db: b"db"})
    got = restore.fetch_latest(backup_ctx, "full", tmp_path / "incoming")
    assert got.name == new_full and got.read_bytes() == b"new"
    assert not list((tmp_path / "incoming").glob("*.partial"))


def test_fetch_latest_needs_drive_and_a_file(backup_ctx, tmp_path):
    backup_ctx.drive = FakeDrive({}, connected=False)
    with pytest.raises(restore.RestoreRefused, match="Chưa kết nối"):
        restore.fetch_latest(backup_ctx, "full", tmp_path)
    backup_ctx.drive = FakeDrive({})
    with pytest.raises(restore.RestoreRefused, match="Không có bản sao lưu loại full"):
        restore.fetch_latest(backup_ctx, "full", tmp_path)
