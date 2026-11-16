import argparse
import logging

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
