"""The Drive client against a stand-in for Google: device flow, folder, upload, errors, secrets."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from shoponline import secrets_store
from shoponline.backup import drive, runner
from shoponline.db.models import BackupRequest, BackupRun

SECRET = "client-secret-XYZ"
REFRESH = "refresh-token-ABC"
ACCESS = "access-token-123"


class FakeWin32Cred:
    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2

    def __init__(self):
        self.records: dict[str, dict] = {}

    def CredWrite(self, record, flags):  # noqa: N802
        self.records[record["TargetName"]] = record

    def CredRead(self, name, kind, flags):  # noqa: N802
        if name not in self.records:
            raise RuntimeError("not found")
        return {"CredentialBlob": self.records[name]["CredentialBlob"]}

    def CredDelete(self, name, kind, flags):  # noqa: N802
        self.records.pop(name, None)


class FakeGoogle:
    """Just enough of oauth2.googleapis.com and Drive v3 for the client."""

    def __init__(self):
        self.token_replies: list[tuple[int, dict]] = []  # device-code polls, in order
        self.refresh_reply: tuple[int, dict] | None = None
        self.folders: dict[str, dict] = {}
        self.files: dict[str, bytes] = {}
        self.names: dict[str, str] = {}
        self.folder_creations = 0
        self.revoked: list[str] = []
        self.break_md5 = False
        self.fail_puts = 0
        self.about_error: int | None = None
        self.seen_bodies: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url, method = str(request.url), request.method
        body = request.content.decode("utf-8", "ignore") if request.content else ""
        self.seen_bodies.append(body)
        path = request.url.path
        if url.startswith("https://oauth2.googleapis.com/device/code"):
            return httpx.Response(
                200,
                json={
                    "device_code": "dev-code-1",
                    "user_code": "ABCD-EFGH",
                    "verification_url": "https://www.google.com/device",
                    "expires_in": 1800,
                    "interval": 5,
                },
            )
        if url.startswith("https://oauth2.googleapis.com/token"):
            form = parse_qs(body)
            if form["grant_type"] == ["refresh_token"]:
                code, data = self.refresh_reply or (
                    200,
                    {"access_token": ACCESS, "expires_in": 3600},
                )
                return httpx.Response(code, json=data)
            code, data = self.token_replies.pop(0)
            return httpx.Response(code, json=data)
        if url.startswith("https://oauth2.googleapis.com/revoke"):
            self.revoked.append(parse_qs(body)["token"][0])
            return httpx.Response(200, json={})
        if path == "/drive/v3/about":
            if self.about_error:
                return httpx.Response(self.about_error, json={"error": {"errors": []}})
            return httpx.Response(200, json={"user": {"emailAddress": "boss@gmail.com"}})
        if path == "/upload/drive/v3/files" and method == "POST":
            meta = json.loads(body)
            self.names["pending"] = meta["name"]
            return httpx.Response(200, headers={"Location": "https://up.example/session/1"})
        if url.startswith("https://up.example/session/1") and method == "PUT":
            if self.fail_puts:
                self.fail_puts -= 1
                return httpx.Response(503)
            rng = re.match(r"bytes (\d+)-(\d+)/(\d+)", request.headers["Content-Range"])
            start, end, total = map(int, rng.groups())
            data = self.files.setdefault("pending", b"") + request.content
            self.files["pending"] = data
            if end + 1 < total:
                return httpx.Response(308, headers={"Range": f"bytes=0-{end}"})
            file_id = "file-1"
            self.files[file_id] = self.files.pop("pending")
            self.names[file_id] = self.names.pop("pending")
            md5 = hashlib.md5(self.files[file_id]).hexdigest()
            if self.break_md5:
                md5 = "0" * 32
            return httpx.Response(200, json={"id": file_id, "md5Checksum": md5})
        if path == "/drive/v3/files" and method == "POST":
            self.folder_creations += 1
            fid = f"folder-{self.folder_creations}"
            self.folders[fid] = {"id": fid, "trashed": False}
            return httpx.Response(200, json={"id": fid})
        if path == "/drive/v3/files" and method == "GET":
            q = request.url.params.get("q", "")
            if "mimeType" in q:
                live = [{"id": f["id"]} for f in self.folders.values() if not f["trashed"]]
                return httpx.Response(200, json={"files": live})
            listing = [
                {"id": i, "name": self.names[i], "size": str(len(d)), "md5Checksum": "m"}
                for i, d in self.files.items()
                if i in self.names
            ]
            return httpx.Response(200, json={"files": listing})
        match = re.match(r"/drive/v3/files/([^/]+)$", path)
        if match:
            fid = match.group(1)
            if method == "DELETE":
                self.files.pop(fid, None)
                self.names.pop(fid, None)
                return httpx.Response(204)
            if fid in self.folders:
                return httpx.Response(200, json=self.folders[fid])
            if fid in self.files:
                if request.url.params.get("alt") == "media":
                    return httpx.Response(200, content=self.files[fid])
                return httpx.Response(
                    200, json={"md5Checksum": hashlib.md5(self.files[fid]).hexdigest()}
                )
            return httpx.Response(404, json={"error": {"errors": [{"reason": "notFound"}]}})
        raise AssertionError(f"unexpected request {method} {url}")


@pytest.fixture
def store(monkeypatch):
    fake = FakeWin32Cred()
    monkeypatch.setattr(secrets_store, "_win32cred", lambda: fake)
    return fake


@pytest.fixture
def google():
    return FakeGoogle()


@pytest.fixture
def client(db_engine, store, google, monkeypatch):
    monkeypatch.setattr(drive, "CHUNK", 8)
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM ops.drive_connection"))
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    now = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)
    c = drive.DriveClient(factory, httpx.MockTransport(google), now=lambda: now, sleep=lambda _s: 0)
    c.set_client("client-id.apps.googleusercontent.com", SECRET, "admin")
    yield c
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM ops.drive_connection"))
        conn.execute(text("DELETE FROM ops.backup_request"))
        conn.execute(text("DELETE FROM ops.backup_run"))


def _connect(client, google):
    google.token_replies.append(
        (200, {"access_token": ACCESS, "refresh_token": REFRESH, "expires_in": 3600})
    )
    client.start_device_flow("admin")
    return client.poll_device_flow()


# --- device flow ----------------------------------------------------------------------------


def test_device_flow_all_branches(client, google):
    device = client.start_device_flow("admin")
    assert device["user_code"] == "ABCD-EFGH" and device["interval"] == 5
    assert client.start_device_flow("admin")["user_code"] == "ABCD-EFGH"  # not restarted

    google.token_replies.append((428, {"error": "authorization_pending"}))
    assert client.poll_device_flow()["status"] == "pending"
    google.token_replies.append((403, {"error": "slow_down"}))
    slow = client.poll_device_flow()
    assert slow["status"] == "slow_down" and slow["interval"] == 10
    google.token_replies.append((403, {"error": "access_denied"}))
    assert client.poll_device_flow()["status"] == "denied"
    assert client.state()["device"] is None

    client.start_device_flow("admin")
    google.token_replies.append((400, {"error": "expired_token"}))
    assert client.poll_device_flow()["status"] == "expired"

    client.start_device_flow("admin")
    google.token_replies.append(
        (200, {"access_token": ACCESS, "refresh_token": REFRESH, "expires_in": 3600})
    )
    done = client.poll_device_flow()
    assert done["status"] == "connected" and "boss@gmail.com" in done["message"]
    state = client.state()
    assert state["status"] == "connected" and state["email"] == "boss@gmail.com"
    assert state["device"] is None and client.connected()


def test_poll_without_a_flow(client):
    assert client.poll_device_flow()["status"] == "none"


def test_device_code_past_its_time_is_expired(client, db_engine):
    client.start_device_flow("admin")
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE ops.drive_connection SET device_expires_at = now() - '1 min'::interval")
        )
    later = drive.DriveClient(
        client._sessions,
        httpx.MockTransport(lambda r: httpx.Response(500)),
        now=lambda: datetime.now(UTC) + timedelta(minutes=1),
    )
    assert later.poll_device_flow()["status"] == "expired"


def test_folder_is_created_once_across_reconnects(client, google):
    _connect(client, google)
    first = client.state()["folder_id"]
    client.disconnect("admin")
    assert google.revoked == [REFRESH]
    assert not client.connected()
    _connect(client, google)
    assert client.state()["folder_id"] == first and google.folder_creations == 1


def test_changed_client_drops_the_connection(client, google, store):
    _connect(client, google)
    client.set_client("", "", "admin")  # nothing changed: stays connected
    assert client.connected()
    client.set_client("other.apps.googleusercontent.com", "", "admin")
    state = client.state()
    assert state["status"] == "disconnected" and not state["has_token"] and state["has_secret"]
    assert state["folder_id"] is None


# --- check and errors -----------------------------------------------------------------------


def test_check_ok_revoked_and_folder_deleted(client, google):
    _connect(client, google)
    assert client.check()["email"] == "boss@gmail.com"

    google.folders[client.state()["folder_id"]]["trashed"] = True
    with pytest.raises(drive.DriveError, match="đã bị xóa"):
        client.check()
    assert client.state()["status"] == "error"
    google.folders[client.state()["folder_id"]]["trashed"] = False

    client._token = None
    google.refresh_reply = (400, {"error": "invalid_grant"})
    with pytest.raises(drive.DriveError) as err:
        client.check()
    assert "thu hồi" in str(err.value) and "Publish to production" in str(err.value)
    state = client.state()
    assert state["status"] == "error" and "thu hồi" in state["error"]
    assert not client.connected()


def test_network_failure_gives_a_plain_message(client, google, db_engine):
    _connect(client, google)

    def down(request):
        raise httpx.ConnectError("no route")

    client._http = httpx.Client(transport=httpx.MockTransport(down))
    client._token = None
    with pytest.raises(drive.DriveError, match="Không có mạng"):
        client.check()
    assert drive.friendly_error(httpx.ConnectError("x")) == drive.MSG_NETWORK


def test_unknown_error_shows_only_the_status_code(client, google):
    _connect(client, google)
    google.about_error = 418
    with pytest.raises(drive.DriveError, match="HTTP 418"):
        client.check()


def test_no_secret_or_token_in_state_errors_or_logs(client, google, caplog):
    caplog.set_level(logging.DEBUG)
    _connect(client, google)
    client.check()
    client.disconnect("admin")
    shown = json.dumps(client.state(), default=str)
    for secret in (SECRET, REFRESH, ACCESS):
        assert secret not in shown and secret not in caplog.text
    assert SECRET not in drive.friendly_error(drive.DriveError(drive.MSG_REVOKED))


# --- upload, list, download -----------------------------------------------------------------


def _backup_file(tmp_path, size=30):
    path = tmp_path / "shoponline-db-shoponline-20261123-163000.7z"
    path.write_bytes(bytes(range(size)))
    return path


def test_upload_in_pieces_list_download_delete(client, google, tmp_path):
    _connect(client, google)
    path = _backup_file(tmp_path)
    file_id = client.upload(path, path.name)
    assert google.files[file_id] == path.read_bytes()
    assert client.names() == {path.name: file_id}
    out = tmp_path / "back.7z"
    client.download(file_id, out)
    assert out.read_bytes() == path.read_bytes()
    client.delete(file_id)
    assert client.names() == {}


def test_upload_retries_a_failed_piece(client, google, tmp_path):
    _connect(client, google)
    google.fail_puts = 2
    path = _backup_file(tmp_path)
    assert client.upload(path, path.name) == "file-1"


def test_upload_with_wrong_md5_is_deleted_and_fails(client, google, tmp_path):
    _connect(client, google)
    google.break_md5 = True
    path = _backup_file(tmp_path)
    with pytest.raises(drive.DriveError, match="MD5"):
        client.upload(path, path.name)
    assert "file-1" not in google.files


def test_files_with_other_names_are_not_listed(client, google, tmp_path):
    _connect(client, google)
    path = tmp_path / "holiday-photos.zip"
    path.write_bytes(b"1234")
    client.upload(path, path.name)
    assert client.names() == {}


# --- runner integration ---------------------------------------------------------------------


def test_retry_drive_uploads_without_a_new_run(backup_ctx, client, google):
    _connect(client, google)
    backup_ctx.drive = client
    first = runner.run_now(backup_ctx, "db", "manual", "admin", to_drive=False)
    assert first.exit_code == runner.EXIT_OK
    with backup_ctx.session_factory() as db:
        run = db.scalars(select(BackupRun)).one()
        assert run.drive_status is None
        db.add(
            BackupRequest(
                action="retry_drive", target_run_id=run.id, requested_by="admin", to_drive=True
            )
        )
        db.commit()
    with runner.backup_lock(backup_ctx.engine) as lock:
        assert lock is not None
        assert runner.process_requests(backup_ctx) == [runner.EXIT_OK]
    with backup_ctx.session_factory() as db:
        run = db.scalars(select(BackupRun)).one()  # still one row
        assert (run.drive_status, run.drive_file_id) == ("ok", "file-1")
        assert db.scalar(select(BackupRequest.status)) == "done"


def test_scheduled_run_uploads_and_a_drive_failure_gives_exit_2(backup_ctx, client, google):
    _connect(client, google)
    backup_ctx.drive = client
    good = runner.run_now(backup_ctx, "db", "manual", "admin", to_drive=True)
    assert good.exit_code == runner.EXIT_OK
    google.fail_puts = 99
    bad = runner.run_now(backup_ctx, "db", "manual", "admin", to_drive=True)
    assert bad.exit_code == runner.EXIT_PARTIAL
    with backup_ctx.session_factory() as db:
        last = db.scalars(select(BackupRun).order_by(BackupRun.id.desc())).first()
        assert last.local_status == "ok" and last.drive_status == "failed"
        assert last.drive_error == drive.MSG_NETWORK or "HTTP 503" in last.drive_error
    for place in backup_ctx.settings.backup_dirs:
        assert (place / bad.file_name).is_file()


def test_not_connected_is_not_a_failure(backup_ctx, client):
    backup_ctx.drive = client
    outcome = runner.run_now(backup_ctx, "db", "manual", "admin", to_drive=True)
    assert outcome.exit_code == runner.EXIT_OK
    with backup_ctx.session_factory() as db:
        assert db.scalars(select(BackupRun)).one().drive_status == "not_connected"
