"""Shared fixtures. Database tests run only against a database whose name ends with _test."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from shoponline.config import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def _test_database_url() -> str | None:
    return os.environ.get("SHOPONLINE_TEST_DATABASE_URL") or None


@pytest.fixture(scope="session")
def db_engine():
    url = _test_database_url()
    if not url:
        pytest.skip("SHOPONLINE_TEST_DATABASE_URL chưa đặt")
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        pytest.exit(f"Từ chối chạy test trên database '{name}': tên phải kết thúc bằng _test")

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["database_url"] = url
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    """A session whose work is rolled back after each test (commits become savepoints)."""
    connection = db_engine.connect()
    outer = connection.begin()
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()
