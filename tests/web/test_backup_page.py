"""The Sao lưu page: roles, back up now, Drive connection, schedule, banner."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker

from shoponline import secrets_store
from shoponline.backup import status, trigger
from shoponline.backup.drive import DriveClient
from shoponline.db.models import BackupRequest, BackupRun, DriveConnection
from tests.backup.test_drive import ACCESS, REFRESH, SECRET, FakeGoogle, FakeWin32Cred


def _reset_drive_row(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM ops.drive_connection"))
        conn.execute(text("INSERT INTO ops.drive_connection (id) VALUES (1)"))


@pytest.fixture
def google(app, db_engine, monkeypatch):
    """Google stand-in. The Drive client commits on connections of its own, as in production:
    the per-test rollback session used by the app would undo what the client saves."""
    fake_store = FakeWin32Cred()
    monkeypatch.setattr(secrets_store, "_win32cred", lambda: fake_store)
    fake = FakeGoogle()
    _reset_drive_row(db_engine)
    app.state.drive = DriveClient(
        sessionmaker(bind=db_engine, expire_on_commit=False),
        httpx.MockTransport(fake),
        sleep=lambda _s: 0,
    )
    yield fake
    _reset_drive_row(db_engine)


@pytest.fixture
def started(monkeypatch):
    """Record schtasks calls instead of making them; the task starts fine by default."""
    calls: list[str] = []
    monkeypatch.setattr(trigger, "start_task", lambda name: calls.append(name) or True)
    return calls


def _connect(client, google):
    client.post("/backup/drive/client", data={"client_id": "cid", "client_secret": SECRET})
    google.token_replies.append(
        (200, {"access_token": ACCESS, "refresh_token": REFRESH, "expires_in": 3600})
    )
    client.post("/backup/drive/connect")
    result = client.post("/backup/drive/poll", headers={"x-autosave": "1"}).json()
    client.get("/backup")  # the page reloads after a successful poll and shows the flash
    return result


def _requests(db) -> list[BackupRequest]:
    return list(db.scalars(select(BackupRequest).order_by(BackupRequest.id)))


# --- roles ------------------------------------------------------------------------------------


def test_viewer_sees_status_but_no_forms(login, google):
    page = login("viewer").get("/backup")
    assert page.status_code == 200
    assert "Sao lưu ngay" in page.text
    assert 'action="/backup/run"' not in page.text
    assert 'action="/backup/settings"' in page.text and "<fieldset disabled" in page.text
    assert "/backup/drive/connect" not in page.text and "/backup/drive/client" not in page.text


@pytest.mark.parametrize(
    ("method", "url", "data"),
    [
        ("post", "/backup/run", {"kind": "db"}),
        ("post", "/backup/drive/client", {"client_id": "x", "client_secret": "y"}),
        ("post", "/backup/drive/connect", {}),
        ("post", "/backup/drive/check", {}),
        ("post", "/backup/drive/disconnect", {}),
        ("post", "/backup/settings", {}),
        ("get", "/backup/drive/files", None),
    ],
)
def test_viewer_cannot_use_any_other_route(login, google, started, db, method, url, data):
    client = login("viewer")
    kwargs = {"data": data} if data is not None else {}
    resp = getattr(client, method)(url, follow_redirects=False, **kwargs)
    assert resp.status_code == 303
    assert started == [] and _requests(db) == []
    assert db.scalar(select(DriveConnection.client_id)) is None


def test_viewer_cannot_poll_the_device_flow(login, google):
    resp = login("viewer").post("/backup/drive/poll", headers={"x-autosave": "1"})
    assert resp.status_code == 403
    assert google.seen_bodies == []


def test_login_is_required(app, google):
    from fastapi.testclient import TestClient

    anonymous = TestClient(app)
    for url in ("/backup", "/backup/drive/files"):
        assert anonymous.get(url, follow_redirects=False).headers["location"] == "/login"
    resp = anonymous.post("/backup/run", data={"kind": "db"}, follow_redirects=False)
    assert resp.headers["location"] == "/login"


# --- back up now ------------------------------------------------------------------------------


def test_backup_now_queues_a_request_and_starts_the_task(login, google, started, db):
    resp = login("admin").post("/backup/run", data={"kind": "full"}, follow_redirects=True)
    assert "Đã bắt đầu sao lưu" in resp.text
    (request,) = _requests(db)
    assert (request.action, request.kind, request.requested_by) == ("backup", "full", "admin")
    assert request.to_drive is False and started == [trigger.BACKUP_TASK]


def test_a_second_click_while_one_waits_makes_no_second_request(login, google, started, db):
    admin = login("admin")
    admin.post("/backup/run", data={"kind": "db"})
    resp = admin.post("/backup/run", data={"kind": "app"}, follow_redirects=True)
    assert "Đang có bản sao lưu chạy" in resp.text
    assert len(_requests(db)) == 1 and len(started) == 1
    assert "disabled" in admin.get("/backup").text  # the buttons are locked


def test_when_the_task_cannot_start_the_request_waits_for_the_fifteen_minute_run(
    login, google, db, monkeypatch
):
    monkeypatch.setattr(trigger, "start_task", lambda name: False)
    resp = login("admin").post("/backup/run", data={"kind": "db"}, follow_redirects=True)
    assert "trong vòng 15 phút" in resp.text
    assert len(_requests(db)) == 1


def test_unknown_kind_is_refused(login, google, started, db):
    resp = login("admin").post("/backup/run", data={"kind": "evil"}, follow_redirects=True)
    assert "không hợp lệ" in resp.text and _requests(db) == []


def test_orphan_running_row_does_not_lock_the_buttons(login, google, db):
    db.add(
        BackupRun(kind="db", source="manual", actor="x", file_name="f.7z", local_status="running")
    )
    db.flush()
    assert status.is_busy(db) is False
    page = login("admin").get("/backup").text
    assert 'name="kind" value="db" >' in page or 'name="kind" value="db" disabled' not in page


def test_drive_checkbox_is_locked_until_connected(login, google, started, db):
    admin = login("admin")
    page = admin.get("/backup").text
    assert "Chưa kết nối Google Drive" in page
    assert 'name="to_drive" value="1" disabled' in page
    admin.post("/backup/run", data={"kind": "db", "to_drive": "1"})
    assert _requests(db)[0].to_drive is False  # forced off server side as well

    db.execute(text("DELETE FROM ops.backup_request"))
    _connect(admin, google)
    assert 'name="to_drive" value="1" checked' in admin.get("/backup").text
    admin.post("/backup/run", data={"kind": "db", "to_drive": "1"})
    assert _requests(db)[0].to_drive is True
    admin.post("/backup/run", data={"kind": "app"})  # blocked (busy): still one request
    assert len(_requests(db)) == 1


# --- Google Drive -----------------------------------------------------------------------------


def test_connect_flow_through_the_web(login, google, db):
    admin = login("admin")
    admin.post("/backup/drive/client", data={"client_id": "cid", "client_secret": SECRET})
    page = admin.get("/backup").text
    assert "Đã lưu (được mã hóa)" in page and SECRET not in page

    google.token_replies.append((428, {"error": "authorization_pending"}))
    admin.post("/backup/drive/connect")
    page = admin.get("/backup").text
    assert "ABCD-EFGH" in page and "https://www.google.com/device" in page
    assert admin.post("/backup/drive/poll", headers={"x-autosave": "1"}).json()["status"] == (
        "pending"
    )

    google.token_replies.append(
        (200, {"access_token": ACCESS, "refresh_token": REFRESH, "expires_in": 3600})
    )
    done = admin.post("/backup/drive/poll", headers={"x-autosave": "1"}).json()
    assert done["status"] == "connected"
    page = admin.get("/backup").text
    assert "Đã kết nối: boss@gmail.com" in page
    for secret in (SECRET, REFRESH, ACCESS):
        assert secret not in page
    assert google.folder_creations == 1


def test_check_and_disconnect(login, google):
    admin = login("admin")
    _connect(admin, google)
    assert (
        "Kết nối Google Drive tốt: boss@gmail.com"
        in admin.post("/backup/drive/check", follow_redirects=True).text
    )
    page = admin.post("/backup/drive/disconnect", follow_redirects=True).text
    assert "Đã ngắt kết nối" in page and "Chưa kết nối" in page
    assert google.revoked == [REFRESH]


def test_revoked_access_shows_a_plain_message(login, google):
    admin = login("admin")
    _connect(admin, google)
    google.refresh_reply = (400, {"error": "invalid_grant"})
    admin.app.state.drive._token = None
    page = admin.post("/backup/drive/check", follow_redirects=True).text
    assert "Google đã thu hồi quyền truy cập" in page


def test_drive_file_list_for_admin(login, google, tmp_path):
    admin = login("admin")
    _connect(admin, google)
    src = tmp_path / "shoponline-db-shoponline-20261123-163000.7z"
    src.write_bytes(b"x" * 20)
    admin.app.state.drive.upload(src, src.name)
    page = admin.get("/backup/drive/files").text
    assert src.name in page


# --- schedule ---------------------------------------------------------------------------------

SETTINGS = {
    "db_time": "09:15",
    "full_weekday": "2",
    "full_time": "10:00",
    "keep_db": "20",
    "keep_app": "5",
    "full_max_days": "45",
    "drive_on_schedule": "1",
}


def test_saving_the_schedule_changes_the_next_run(login, google, db):
    admin = login("admin")
    before = admin.get("/backup").text
    resp = admin.post("/backup/settings", data=SETTINGS, follow_redirects=True)
    assert "Đã lưu lịch" in resp.text
    row = db.execute(
        text(
            "SELECT db_time, full_weekday, keep_db, keep_app, full_max_days, changed_by "
            "FROM ops.backup_settings"
        )
    ).one()
    assert (str(row[0]), row[1], row[2], row[3], row[4], row[5]) == (
        "09:15:00",
        2,
        20,
        5,
        45,
        "admin",
    )
    assert 'value="09:15"' in resp.text and resp.text != before


def test_invalid_schedule_values_are_refused_and_nothing_changes(login, google, db):
    admin = login("admin")
    for bad in (
        {"db_time": "25:99"},
        {"keep_db": "0"},
        {"keep_app": "101"},
        {"full_max_days": "6"},
        {"full_max_days": "91"},
        {"full_weekday": "7"},
    ):
        resp = admin.post("/backup/settings", data={**SETTINGS, **bad}, follow_redirects=True)
        assert "phải" in resp.text, bad
    assert db.scalar(text("SELECT keep_db FROM ops.backup_settings")) == 15


# --- banner -----------------------------------------------------------------------------------

FRIDAY_EVENING = datetime(2026, 11, 27, 11, 0, tzinfo=UTC)  # 18:00 Vietnam


def _run(db, kind, hours_ago, local="ok", drive=None):
    db.add(
        BackupRun(
            kind=kind,
            source="schedule",
            actor="system",
            file_name=f"{kind}-{hours_ago}.7z",
            local_status=local,
            drive_status=drive,
            started_at=FRIDAY_EVENING - timedelta(hours=hours_ago),
        )
    )
    db.flush()


def test_banner_cases(db):
    db.execute(text("DELETE FROM ops.backup_run"))
    db.execute(text("UPDATE ops.drive_connection SET status = 'disconnected', last_error = NULL"))
    found = status.warnings(db, FRIDAY_EVENING)
    assert any("Chưa có bản sao lưu database nào" in m for m in found)

    _run(db, "db", 1)  # 17:00, after the 16:30 slot
    _run(db, "full", 24)
    assert status.warnings(db, FRIDAY_EVENING) == []

    db.execute(text("DELETE FROM ops.backup_run WHERE kind = 'db'"))
    _run(db, "db", 30)  # yesterday: this evening's slot (16:30 + 2 h grace = 18:30) not yet late
    assert status.warnings(db, FRIDAY_EVENING) == []
    late = status.warnings(db, FRIDAY_EVENING + timedelta(hours=2))
    assert any("Chưa có bản sao lưu database từ lịch" in m for m in late)

    db.execute(text("DELETE FROM ops.backup_run WHERE kind = 'full'"))
    _run(db, "full", 24 * 9)
    assert any("Toàn bộ trong 8 ngày" in m for m in status.warnings(db, FRIDAY_EVENING))


def test_banner_reports_drive_problems_from_the_database_only(db):
    db.execute(text("DELETE FROM ops.backup_run"))
    _run(db, "db", 1)
    _run(db, "full", 1)
    db.execute(
        text(
            "UPDATE ops.drive_connection SET status = 'error', last_error = 'Hết dung lượng Drive'"
        )
    )
    assert any("Hết dung lượng Drive" in m for m in status.warnings(db, FRIDAY_EVENING))
    db.execute(text("UPDATE ops.drive_connection SET status = 'connected', last_error = NULL"))
    assert any("chưa lên Google Drive" in m for m in status.warnings(db, FRIDAY_EVENING))
    _run(db, "db", 1, drive="ok")
    assert status.warnings(db, FRIDAY_EVENING) == []


def test_pages_render_without_calling_google(login, app, db):
    """The banner is read from the database; a transport that fails any call proves it."""

    def forbidden(request):
        raise AssertionError(f"unexpected call to {request.url}")

    app.state.drive = DriveClient(app.state.session_factory, httpx.MockTransport(forbidden))
    db.execute(text("UPDATE ops.drive_connection SET status = 'connected'"))
    client = login("admin")
    assert client.get("/batches").status_code == 200
    assert client.get("/backup").status_code == 200
    assert db.scalar(select(func.count()).select_from(BackupRun)) >= 0
