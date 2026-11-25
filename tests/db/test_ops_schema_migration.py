"""Migration 0010 moves the web accounts into schema ops and can run again after a restore."""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from tests.conftest import ROOT


@pytest.fixture
def alembic_cfg(db_engine):
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["database_url"] = db_engine.url.render_as_string(hide_password=False)
    yield cfg
    command.upgrade(cfg, "head")
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM ops.app_user WHERE username LIKE 'mig-%'"))


def _regclass(conn, name: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:n)"), {"n": name}).scalar() is not None


def test_upgrade_moves_accounts_with_their_data(db_engine, alembic_cfg):
    command.downgrade(alembic_cfg, "0009_platform_settlement")
    with db_engine.begin() as conn:
        assert _regclass(conn, "public.app_user")
        assert not _regclass(conn, "ops.app_user")
        conn.execute(
            text(
                "INSERT INTO public.app_user (username, password_hash, role) "
                "VALUES ('mig-kept', 'x', 'admin')"
            )
        )
    command.upgrade(alembic_cfg, "0010_backup")
    with db_engine.begin() as conn:
        assert not _regclass(conn, "public.app_user")
        names = conn.execute(text("SELECT username FROM ops.app_user")).scalars().all()
        assert "mig-kept" in names
        assert conn.execute(text("SELECT session_epoch FROM ops.system_state")).scalar() == 0
        row = conn.execute(text("SELECT keep_db, full_weekday FROM ops.backup_settings")).one()
        assert tuple(row) == (15, 4)


def test_rerun_after_restore_keeps_live_accounts(db_engine, alembic_cfg):
    """A restored old dump brings back public.app_user and alembic_version 0009."""
    # The dump predates later public tables, so they are gone after a restore (ops stays live).
    command.downgrade(alembic_cfg, "0011_drive_connection")
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ops.app_user (username, password_hash, role) "
                "VALUES ('mig-live', 'x', 'admin')"
            )
        )
        conn.execute(text("CREATE TABLE public.app_user (LIKE ops.app_user)"))
        conn.execute(
            text(
                "INSERT INTO public.app_user (id, username, password_hash, role, active, "
                "created_at) VALUES (999, 'mig-restored', 'x', 'viewer', true, now())"
            )
        )
        conn.execute(text("UPDATE alembic_version SET version_num = '0009_platform_settlement'"))
    command.upgrade(alembic_cfg, "head")
    with db_engine.begin() as conn:
        assert not _regclass(conn, "public.app_user")
        names = conn.execute(text("SELECT username FROM ops.app_user")).scalars().all()
        assert "mig-live" in names
        assert "mig-restored" not in names
        assert conn.execute(text("SELECT count(*) FROM ops.backup_settings")).scalar() == 1
