"""A backup context on the test database. The backup code commits on its own connections, so
these tests clean the ops backup tables afterwards instead of rolling back."""

from __future__ import annotations

import shutil
import subprocess

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from shoponline.backup import pgtools
from shoponline.backup.runner import Context
from shoponline.backup.sevenzip import SevenZipError, find_exe
from shoponline.config import Settings

PASSWORD = "test-backup-pass-71"


def _tools():
    try:
        return find_exe(), pgtools.find_bin()
    except (SevenZipError, pgtools.PgToolError):
        return None


TOOLS = _tools()
needs_tools = pytest.mark.skipif(TOOLS is None, reason="cần 7-Zip và pg_dump")


@pytest.fixture
def seven_zip():
    if TOOLS is None:
        pytest.skip("cần 7-Zip")
    return TOOLS[0]


def _clean(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM ops.backup_request"))
        conn.execute(text("DELETE FROM ops.backup_run"))
        conn.execute(
            text(
                "UPDATE ops.backup_settings SET db_time = '16:30', full_weekday = 4, "
                "full_time = '16:30', keep_db = 15, keep_app = 15, full_max_days = 30, "
                "drive_on_schedule = true"
            )
        )


@pytest.fixture
def backup_ctx(db_engine, tmp_path):
    if TOOLS is None:
        pytest.skip("cần 7-Zip và pg_dump")
    _clean(db_engine)
    data = tmp_path / "data"
    (data / "uploads").mkdir(parents=True)
    (data / "uploads" / "orders.xlsx").write_bytes(b"workbook")
    (data / "logs").mkdir()
    (data / "logs" / "web.log").write_text("log line", encoding="utf-8")
    (data / "robot-work").mkdir()
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    (repo / "config" / "sap_screens.yaml").write_text("screens: {}\n", encoding="utf-8")
    (repo / ".env").write_text(
        f"SHOPONLINE_SECRET_KEY={'k' * 40}\nSHOPONLINE_BACKUP_PASSWORD={PASSWORD}\n",
        encoding="utf-8",
    )
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "config"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "init"], check=True)
    settings = Settings(
        database_url=db_engine.url.render_as_string(hide_password=False),
        secret_key="s" * 40,
        data_dir=data,
        backup_password=PASSWORD,
        backup_dirs=(tmp_path / "place-a", tmp_path / "place-b"),
    )
    ctx = Context(
        settings=settings,
        session_factory=sessionmaker(bind=db_engine, expire_on_commit=False),
        engine=db_engine,
        repo_root=repo,
        pg_bin=TOOLS[1],
        seven_zip=TOOLS[0],
    )
    yield ctx
    _clean(db_engine)
    shutil.rmtree(data / "backup-work", ignore_errors=True)
