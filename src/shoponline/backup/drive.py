"""Google Drive as a backup place: OAuth device flow, upload with checksum, list, download,
delete, revoke. Plain HTTP with httpx; scope drive.file, so the app only sees what it created.

Secrets (client secret, refresh token) live in the Windows Credential Manager (secrets_store);
the database keeps only non-secret state (ops.drive_connection). No message, log line or
exception in this module carries a token, a secret or a response body.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from shoponline import secrets_store
from shoponline.backup import naming
from shoponline.db.models import DriveConnection

log = logging.getLogger(__name__)

SCOPE = "https://www.googleapis.com/auth/drive.file"
DEVICE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER_NAME = "shoponline-backup"
FOLDER_MIME = "application/vnd.google-apps.folder"
SECRET_TARGET = "shoponline/google-drive/client-secret"
TOKEN_TARGET = "shoponline/google-drive/refresh-token"
CHUNK = 8 * 1024 * 1024  # a multiple of 256 KiB, as the resumable protocol requires
RETRIES = 3

MSG_REVOKED = (
    "Google đã thu hồi quyền truy cập: kết nối lại Drive. Nếu OAuth client còn ở chế độ "
    "Testing thì quyền hết hạn sau 7 ngày; hãy Publish to production"
)
MSG_FOLDER = f"Thư mục {FOLDER_NAME} trên Drive đã bị xóa"
MSG_QUOTA = "Hết dung lượng Drive"
MSG_NETWORK = "Không có mạng tới Google"
MSG_CLIENT = "Client ID hoặc Client Secret không đúng"
MSG_NOT_SET = "Chưa nhập Client ID và Client Secret"
MSG_NOT_CONNECTED = "Chưa kết nối Google Drive"


class DriveError(Exception):
    """A failure with a message safe to show on the web (Vietnamese, no token, no body)."""

    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.code = code


def friendly_error(exc: Exception) -> str:
    if isinstance(exc, DriveError):
        return str(exc)
    if isinstance(exc, httpx.TransportError):
        return MSG_NETWORK
    return "Google Drive gặp lỗi không rõ; xem log để biết chi tiết"


def _reason(response: httpx.Response) -> str:
    """The error reason Google sent ('invalid_grant', 'storageQuotaExceeded', ...), or ''."""
    try:
        body = response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, str):
        return error
    if isinstance(error, dict):
        errors = error.get("errors") or []
        if errors and isinstance(errors[0], dict):
            return str(errors[0].get("reason", ""))
    return ""


def _fail(response: httpx.Response) -> DriveError:
    reason, status = _reason(response), response.status_code
    if reason == "invalid_grant":
        return DriveError(MSG_REVOKED, "invalid_grant")
    if reason in ("invalid_client", "unauthorized_client"):
        return DriveError(MSG_CLIENT, "invalid_client")
    if reason in ("storageQuotaExceeded", "quotaExceeded"):
        return DriveError(MSG_QUOTA, "quota")
    if status == 404:
        return DriveError(MSG_FOLDER, "not_found")
    return DriveError(f"Google Drive trả lỗi HTTP {status}", f"http_{status}")


def _md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DriveClient:
    """Implements the runner's DrivePlace on top of Google Drive."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        transport: httpx.BaseTransport | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._sessions = session_factory
        self._http = httpx.Client(transport=transport, timeout=60.0)
        self._now = now
        self._sleep = sleep
        self._token: tuple[str, datetime] | None = None

    # --- connection row ---------------------------------------------------------------

    def _row(self, db: Session) -> DriveConnection:
        row = db.get(DriveConnection, 1)
        if row is None:
            row = DriveConnection(id=1, status="disconnected")
            db.add(row)
            db.flush()
        return row

    def state(self) -> dict:
        """Non-secret state for the web and the CLI."""
        with self._sessions() as db:
            row = self._row(db)
            db.commit()
            return {
                "client_id": row.client_id,
                "has_secret": secrets_store.read(SECRET_TARGET) is not None,
                "has_token": secrets_store.read(TOKEN_TARGET) is not None,
                "folder_id": row.folder_id,
                "email": row.account_email,
                "status": row.status,
                "error": row.last_error,
                "checked_at": row.checked_at,
                "device": self._device_of(row),
            }

    def _device_of(self, row: DriveConnection) -> dict | None:
        if not row.device_code or not row.device_expires_at:
            return None
        if row.device_expires_at <= self._now():
            return None
        return {
            "user_code": row.user_code,
            "url": row.verification_url,
            "expires_at": row.device_expires_at,
            "interval": row.poll_interval or 5,
        }

    def connected(self) -> bool:
        with self._sessions() as db:
            status = self._row(db).status
            db.commit()
        return status == "connected" and secrets_store.read(TOKEN_TARGET) is not None

    def _record_error(self, message: str) -> None:
        with self._sessions() as db:
            row = self._row(db)
            row.status, row.last_error, row.checked_at = "error", message, self._now()
            db.commit()

    # --- credentials ------------------------------------------------------------------

    def set_client(self, client_id: str, secret: str, actor: str) -> None:
        """Save the OAuth client. An empty secret keeps the stored one. A different client
        or secret drops the old connection: drive.file ties files to the project."""
        client_id = client_id.strip()
        with self._sessions() as db:
            row = self._row(db)
            changed = bool(client_id) and client_id != (row.client_id or "")
            if secret:
                changed = changed or secret != secrets_store.read(SECRET_TARGET)
                secrets_store.write(SECRET_TARGET, secret, "client-secret", "shoponline Drive")
            if client_id:
                row.client_id = client_id
            if changed:
                secrets_store.delete(TOKEN_TARGET)
                row.status, row.folder_id, row.account_email = "disconnected", None, None
                row.last_error = None
                row.device_code = row.user_code = row.verification_url = None
                row.device_expires_at = row.poll_interval = None
                self._token = None
            row.changed_by, row.changed_at = actor[:50], self._now()
            db.commit()

    def _client_pair(self) -> tuple[str, str]:
        with self._sessions() as db:
            client_id = self._row(db).client_id
            db.commit()
        secret = secrets_store.read(SECRET_TARGET)
        if not client_id or not secret:
            raise DriveError(MSG_NOT_SET, "no_client")
        return client_id, secret

    def _post_token(self, data: dict) -> httpx.Response:
        client_id, secret = self._client_pair()
        return self._http.post(
            TOKEN_URL, data={**data, "client_id": client_id, "client_secret": secret}
        )

    def _access_token(self) -> str:
        if self._token and self._token[1] > self._now() + timedelta(seconds=60):
            return self._token[0]
        refresh = secrets_store.read(TOKEN_TARGET)
        if not refresh:
            raise DriveError(MSG_NOT_CONNECTED, "not_connected")
        response = self._post_token({"grant_type": "refresh_token", "refresh_token": refresh})
        if response.status_code != 200:
            error = _fail(response)
            if error.code == "invalid_grant":
                self._record_error(str(error))
            raise error
        body = response.json()
        self._token = (body["access_token"], self._now() + timedelta(seconds=body["expires_in"]))
        return self._token[0]

    # --- device flow ------------------------------------------------------------------

    def start_device_flow(self, actor: str) -> dict:
        """The code to show the person. A flow still waiting is returned again, not restarted."""
        with self._sessions() as db:
            existing = self._device_of(self._row(db))
            db.commit()
        if existing:
            return existing
        client_id, _ = self._client_pair()
        response = self._http.post(DEVICE_URL, data={"client_id": client_id, "scope": SCOPE})
        if response.status_code != 200:
            raise _fail(response)
        body = response.json()
        with self._sessions() as db:
            row = self._row(db)
            row.device_code = body["device_code"]
            row.user_code = body["user_code"]
            row.verification_url = body.get("verification_url") or "https://www.google.com/device"
            row.device_expires_at = self._now() + timedelta(seconds=int(body["expires_in"]))
            row.poll_interval = int(body.get("interval", 5))
            row.changed_by, row.changed_at = actor[:50], self._now()
            db.commit()
        return self.state()["device"]

    def poll_device_flow(self) -> dict:
        """Ask Google once. Returns {"status": pending|slow_down|denied|expired|connected|none,
        "message": ..., "interval": seconds}."""
        with self._sessions() as db:
            row = self._row(db)
            code, expires = row.device_code, row.device_expires_at
            interval = row.poll_interval or 5
            db.commit()
        if not code:
            return {"status": "none", "message": "Không có phiên kết nối đang chờ", "interval": 5}
        if expires and expires <= self._now():
            self._clear_device()
            return {"status": "expired", "message": "Mã đã hết hạn, hãy tạo mã mới", "interval": 5}
        response = self._post_token(
            {"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": code}
        )
        if response.status_code == 200:
            return self._finish_connect(response.json())
        reason = _reason(response)
        if reason == "authorization_pending":
            return {"status": "pending", "message": "Đang chờ bạn xác nhận", "interval": interval}
        if reason == "slow_down":
            interval += 5
            with self._sessions() as db:
                self._row(db).poll_interval = interval
                db.commit()
            return {
                "status": "slow_down",
                "message": "Google yêu cầu chậm lại",
                "interval": interval,
            }
        if reason == "access_denied":
            self._clear_device()
            return {"status": "denied", "message": "Bạn đã từ chối cấp quyền", "interval": 5}
        if reason == "expired_token":
            self._clear_device()
            return {"status": "expired", "message": "Mã đã hết hạn, hãy tạo mã mới", "interval": 5}
        raise _fail(response)

    def _clear_device(self) -> None:
        with self._sessions() as db:
            row = self._row(db)
            row.device_code = row.user_code = row.verification_url = None
            row.device_expires_at = row.poll_interval = None
            db.commit()

    def _finish_connect(self, body: dict) -> dict:
        refresh = body.get("refresh_token")
        if not refresh:
            raise DriveError(
                "Google không trả quyền truy cập lâu dài; thử kết nối lại", "no_refresh"
            )
        secrets_store.write(TOKEN_TARGET, refresh, "refresh-token", "shoponline Drive")
        self._token = (body["access_token"], self._now() + timedelta(seconds=body["expires_in"]))
        email = self._about()
        folder = self.ensure_folder()
        with self._sessions() as db:
            row = self._row(db)
            row.status, row.last_error, row.checked_at = "connected", None, self._now()
            row.account_email, row.folder_id = email, folder
            row.device_code = row.user_code = row.verification_url = None
            row.device_expires_at = row.poll_interval = None
            db.commit()
        return {"status": "connected", "message": f"Đã kết nối: {email}", "interval": 5}

    # --- Drive calls ------------------------------------------------------------------

    def _call(self, method: str, url: str, **kwargs) -> httpx.Response:
        extra = kwargs.pop("headers", {})
        for attempt in range(2):
            headers = {"Authorization": f"Bearer {self._access_token()}", **extra}
            response = self._http.request(method, url, headers=headers, **kwargs)
            if response.status_code == 401 and attempt == 0:
                self._token = None
                continue
            return response
        return response

    def _check(self, response: httpx.Response) -> httpx.Response:
        if response.status_code >= 400:
            raise _fail(response)
        return response

    def _about(self) -> str:
        response = self._check(
            self._call("GET", f"{API}/about", params={"fields": "user(emailAddress)"})
        )
        return response.json()["user"]["emailAddress"]

    def ensure_folder(self) -> str:
        """The backup folder: the stored one when still there, else one this app created
        earlier, else a new one."""
        with self._sessions() as db:
            stored = self._row(db).folder_id
            db.commit()
        if stored:
            response = self._call("GET", f"{API}/files/{stored}", params={"fields": "id,trashed"})
            if response.status_code == 200 and not response.json().get("trashed"):
                return stored
            if response.status_code not in (200, 404):
                raise _fail(response)
        query = f"name = '{FOLDER_NAME}' and mimeType = '{FOLDER_MIME}' and trashed = false"
        found = self._check(
            self._call("GET", f"{API}/files", params={"q": query, "fields": "files(id)"})
        ).json()["files"]
        if found:
            return found[0]["id"]
        created = self._check(
            self._call(
                "POST",
                f"{API}/files",
                params={"fields": "id"},
                json={"name": FOLDER_NAME, "mimeType": FOLDER_MIME},
            )
        )
        return created.json()["id"]

    def _folder(self) -> str:
        with self._sessions() as db:
            folder = self._row(db).folder_id
            db.commit()
        if not folder:
            raise DriveError(MSG_NOT_CONNECTED, "not_connected")
        return folder

    def check(self) -> dict:
        """Refresh the token, read the account and the folder; record the result."""
        try:
            email = self._about()
            folder = self._folder()
            response = self._call("GET", f"{API}/files/{folder}", params={"fields": "id,trashed"})
            if response.status_code == 404 or (
                response.status_code == 200 and response.json().get("trashed")
            ):
                raise DriveError(MSG_FOLDER, "not_found")
            self._check(response)
        except DriveError as exc:
            self._record_error(str(exc))
            raise
        except httpx.TransportError as exc:
            self._record_error(MSG_NETWORK)
            raise DriveError(MSG_NETWORK, "network") from exc
        with self._sessions() as db:
            row = self._row(db)
            row.status, row.last_error, row.checked_at = "connected", None, self._now()
            row.account_email = email
            db.commit()
        return {"email": email, "folder_id": folder}

    def list_backups(self) -> list[dict]:
        folder = self._folder()
        found, token = [], None
        while True:
            params = {
                "q": f"'{folder}' in parents and trashed = false",
                "fields": "nextPageToken,files(id,name,size,md5Checksum,createdTime)",
                "pageSize": 100,
            }
            if token:
                params["pageToken"] = token
            body = self._check(self._call("GET", f"{API}/files", params=params)).json()
            found += [f for f in body["files"] if naming.parse(f["name"]) is not None]
            token = body.get("nextPageToken")
            if not token:
                return found

    def names(self) -> dict[str, str]:
        return {f["name"]: f["id"] for f in self.list_backups()}

    def upload(self, path: Path, name: str) -> str:
        """Upload in 8 MB pieces, retrying each; the file counts only when Drive's MD5 equals
        the local one. Returns the Drive file id."""
        folder = self._folder()
        total = path.stat().st_size
        start = self._check(
            self._call(
                "POST",
                UPLOAD,
                params={"uploadType": "resumable", "fields": "id,md5Checksum"},
                json={"name": name, "parents": [folder]},
                headers={
                    "X-Upload-Content-Type": "application/octet-stream",
                    "X-Upload-Content-Length": str(total),
                },
            )
        )
        session_url = start.headers["Location"]
        offset, final = 0, None
        with path.open("rb") as handle:
            while final is None:
                handle.seek(offset)
                piece = handle.read(CHUNK)
                end = offset + len(piece) - 1
                response = self._put_piece(session_url, piece, offset, end, total)
                if response.status_code in (200, 201):
                    final = response.json()
                elif response.status_code == 308:
                    offset = _next_offset(response, end)
                else:
                    raise _fail(response)
        if (final.get("md5Checksum") or "") != _md5(path):
            self.delete(final["id"])
            raise DriveError("Drive nhận file nhưng checksum MD5 không khớp; thử lại", "md5")
        return final["id"]

    def _put_piece(self, url, piece, offset, end, total) -> httpx.Response:
        """One piece, sent again after a network or 5xx failure (Drive answers 308 with the
        range it already has when part of it arrived)."""
        last: Exception | None = None
        for attempt in range(RETRIES):
            try:
                response = self._http.put(
                    url,
                    content=piece,
                    headers={
                        "Content-Range": f"bytes {offset}-{end}/{total}",
                        "Authorization": f"Bearer {self._access_token()}",
                    },
                )
                if response.status_code < 500:
                    return response
                last = DriveError(f"Google Drive trả lỗi HTTP {response.status_code}")
            except httpx.TransportError as exc:
                last = exc
            self._sleep(2**attempt)
        if isinstance(last, httpx.TransportError):
            raise DriveError(MSG_NETWORK, "network") from last
        raise last  # type: ignore[misc]

    def download(self, file_id: str, dest: Path) -> None:
        """Stream a Drive file to dest and check its MD5; dest is removed on a mismatch."""
        meta = self._check(
            self._call("GET", f"{API}/files/{file_id}", params={"fields": "md5Checksum"})
        ).json()
        digest = hashlib.md5(usedforsecurity=False)
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        with self._http.stream(
            "GET", f"{API}/files/{file_id}", params={"alt": "media"}, headers=headers
        ) as response:
            if response.status_code >= 400:
                response.read()
                raise _fail(response)
            with dest.open("wb") as out:
                for chunk in response.iter_bytes(1 << 20):
                    digest.update(chunk)
                    out.write(chunk)
        if meta.get("md5Checksum") and digest.hexdigest() != meta["md5Checksum"]:
            dest.unlink(missing_ok=True)
            raise DriveError("Tải từ Drive về bị lỗi (MD5 không khớp); thử lại", "md5")

    def delete(self, file_id: str) -> None:
        response = self._call("DELETE", f"{API}/files/{file_id}")
        if response.status_code not in (200, 204, 404):
            raise _fail(response)

    def disconnect(self, actor: str) -> None:
        """Revoke the token at Google, forget it here. Files on Drive stay."""
        refresh = secrets_store.read(TOKEN_TARGET)
        if refresh:
            try:
                self._http.post(REVOKE_URL, data={"token": refresh})
            except httpx.TransportError:
                log.warning("Không thu hồi được token ở Google (không có mạng); vẫn xóa ở máy này")
        secrets_store.delete(TOKEN_TARGET)
        self._token = None
        with self._sessions() as db:
            row = self._row(db)
            row.status, row.account_email, row.last_error = "disconnected", None, None
            row.device_code = row.user_code = row.verification_url = None
            row.device_expires_at = row.poll_interval = None
            row.changed_by, row.changed_at = actor[:50], self._now()
            db.commit()

    def friendly(self, exc: Exception) -> str:
        return friendly_error(exc)


def _next_offset(response: httpx.Response, sent_end: int) -> int:
    """Where to continue after a 308: one past the last byte Drive reports (Range: bytes=0-N)."""
    header = response.headers.get("Range")
    if header and "-" in header:
        return int(header.rsplit("-", 1)[1]) + 1
    return sent_end + 1
