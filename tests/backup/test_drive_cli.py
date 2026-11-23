"""The `shoponline drive ...` commands run the same module as the web buttons."""

from __future__ import annotations

import argparse

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from shoponline import cli, secrets_store
from shoponline.backup import drive
from tests.backup.test_drive import ACCESS, REFRESH, SECRET, FakeGoogle, FakeWin32Cred


@pytest.fixture
def client(db_engine, monkeypatch):
    fake_store = FakeWin32Cred()
    monkeypatch.setattr(secrets_store, "_win32cred", lambda: fake_store)
    google = FakeGoogle()
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM ops.drive_connection"))
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    c = drive.DriveClient(factory, httpx.MockTransport(google), sleep=lambda _s: 0)
    c.google = google
    yield c
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM ops.drive_connection"))


def _args(action: str, **extra) -> argparse.Namespace:
    return argparse.Namespace(action=action, **extra)


def test_set_client_connect_status_and_disconnect(client, monkeypatch, capsys):
    monkeypatch.setattr("getpass.getpass", lambda prompt="": SECRET)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    assert cli._drive_action(_args("set-client", client_id="cid"), client, "admin", drive) == 0

    client.google.token_replies.append((428, {"error": "authorization_pending"}))
    client.google.token_replies.append(
        (200, {"access_token": ACCESS, "refresh_token": REFRESH, "expires_in": 3600})
    )
    assert cli._drive_action(_args("connect"), client, "admin", drive) == 0
    out = capsys.readouterr().out
    assert "ABCD-EFGH" in out and "google.com/device" in out and "boss@gmail.com" in out
    assert client.connected() and client.state()["folder_id"] == "folder-1"

    assert cli._drive_action(_args("status", check=True), client, "admin", drive) == 0
    shown = capsys.readouterr().out
    assert "connected" in shown and "boss@gmail.com" in shown
    for secret in (SECRET, REFRESH, ACCESS):
        assert secret not in out and secret not in shown

    assert cli._drive_action(_args("disconnect"), client, "admin", drive) == 0
    assert not client.connected() and client.google.revoked == [REFRESH]


def test_connect_reports_a_denied_request(client, monkeypatch, capsys):
    monkeypatch.setattr("getpass.getpass", lambda prompt="": SECRET)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    cli._drive_action(_args("set-client", client_id="cid"), client, "admin", drive)
    client.google.token_replies.append((403, {"error": "access_denied"}))
    assert cli._drive_action(_args("connect"), client, "admin", drive) == 1
    assert "từ chối" in capsys.readouterr().out
