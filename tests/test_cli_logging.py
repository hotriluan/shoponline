import argparse
import logging
import os
from datetime import datetime, timedelta

import pytest
import uvicorn

import shoponline.web.app
from shoponline import cli
from shoponline.config import load_settings


@pytest.fixture
def settings(tmp_path):
    return load_settings(
        {
            "SHOPONLINE_DATABASE_URL": "postgresql+psycopg://u:p@localhost/x",
            "SHOPONLINE_SECRET_KEY": "k" * 32,
            "SHOPONLINE_DATA_DIR": str(tmp_path),
        }
    )


@pytest.fixture
def clean_root_logger():
    """Remove the handlers and levels a test sets up, so later tests log as before."""
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    access_level = logging.getLogger("uvicorn.access").level
    yield root
    for handler in root.handlers[:]:
        if handler not in saved_handlers:
            handler.close()
            root.removeHandler(handler)
    root.setLevel(saved_level)
    logging.getLogger("uvicorn.access").setLevel(access_level)


def test_setup_logging_writes_to_the_data_log_folder(settings, clean_root_logger):
    cli._setup_logging(settings, "web.log")
    logging.getLogger("shoponline.test").info("dòng thử")
    for handler in clean_root_logger.handlers:
        handler.flush()

    text = (settings.data_dir / "logs" / "web.log").read_text(encoding="utf-8")
    assert "INFO shoponline.test: dòng thử" in text


def test_web_hands_uvicorn_logging_to_the_root_logger(settings, clean_root_logger, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(shoponline.web.app, "create_app", lambda s: "app")
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.update(app=app, **kwargs))

    assert cli._cmd_web(argparse.Namespace()) == 0

    assert calls["app"] == "app"
    assert calls["log_config"] is None
    assert calls["port"] == settings.web_port
    assert logging.getLogger("uvicorn.access").level == logging.WARNING
    logging.getLogger("uvicorn.error").info("Application startup complete.")
    logging.getLogger("uvicorn.access").info("GET /login 200")
    for handler in clean_root_logger.handlers:
        handler.flush()
    text = (settings.data_dir / "logs" / "web.log").read_text(encoding="utf-8")
    assert "uvicorn.error: Application startup complete." in text
    assert "GET /login" not in text


def test_retention_sweeps_files_keeps_customer_data_and_logs_to_a_rotating_file(
    db, settings, clean_root_logger, monkeypatch
):
    from contextlib import contextmanager
    from logging.handlers import RotatingFileHandler

    from sqlalchemy import select

    import shoponline.db.session
    from shoponline.db.models import CustomerInfo

    @contextmanager
    def test_session(_url):
        yield db

    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(shoponline.db.session, "session_scope", test_session)
    old = datetime.now() - timedelta(days=200)
    db.add(CustomerInfo(platform="SHOPEE", platform_order_id="R-OLD", customer_name="Khách"))
    db.flush()
    db.scalars(select(CustomerInfo)).one().updated_at = old
    db.flush()
    orphan = settings.upload_dir / "orphan.xlsx"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"x")
    os.utime(orphan, (old.timestamp(), old.timestamp()))

    assert cli.main(["retention", "--apply"]) == 0  # --apply is accepted and changes nothing more

    assert not orphan.exists()
    assert db.scalars(select(CustomerInfo)).one().customer_name == "Khách"
    assert any(isinstance(h, RotatingFileHandler) for h in clean_root_logger.handlers)
    for handler in clean_root_logger.handlers:
        handler.flush()
    text = (settings.data_dir / "logs" / "retention.log").read_text(encoding="utf-8")
    assert "--apply không còn tác dụng" in text and "Sẽ xóa" not in text
    assert "Đã xóa 1 file hết dùng" in text and str(orphan) in text


def test_retention_does_nothing_while_a_restore_or_deploy_is_running(
    db, settings, clean_root_logger, monkeypatch
):
    from contextlib import contextmanager

    import shoponline.db.session
    from shoponline.backup import maintenance

    @contextmanager
    def test_session(_url):
        yield db

    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(shoponline.db.session, "session_scope", test_session)
    old = datetime.now() - timedelta(days=200)
    orphan = settings.upload_dir / "orphan.xlsx"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"x")
    os.utime(orphan, (old.timestamp(), old.timestamp()))
    maintenance.write(settings, "restore")

    assert cli.main(["retention", "--apply"]) == 0

    assert orphan.exists()
    for handler in clean_root_logger.handlers:
        handler.flush()
    text = (settings.data_dir / "logs" / "retention.log").read_text(encoding="utf-8")
    assert "đang bảo trì (restore)" in text
