"""7-Zip: create, test, list and extract AES-256 archives with hidden file names.

The password never goes on the command line: 7-Zip reads it from standard input (creating with
an empty -p switch, reading with no -p at all, which makes 7-Zip ask for it). Error messages
carry 7-Zip's own last lines, never the password, and RedactFilter scrubs any "-p<value>" or the
password itself from log records as a second guard.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

DEFAULT_EXE = Path(r"C:\Program Files\7-Zip\7z.exe")


class SevenZipError(RuntimeError):
    pass


def find_exe(explicit: str | Path | None = None) -> Path:
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return path
        raise SevenZipError(f"Không thấy 7-Zip tại {path}")
    if DEFAULT_EXE.is_file():
        return DEFAULT_EXE
    for name in ("7z", "7za", "7zz"):
        found = shutil.which(name)
        if found:
            return Path(found)
    raise SevenZipError("Không thấy 7-Zip; cài 7-Zip hoặc truyền --seven-zip")


@dataclass(frozen=True)
class Entry:
    path: str
    is_dir: bool
    size: int
    encrypted: bool


def safe_member(path: str) -> bool:
    """False for absolute paths, drive letters and any '..' part."""
    if not path or path.startswith(("/", "\\")):
        return False
    win = PureWindowsPath(path)
    if win.drive or win.root:
        return False
    parts = PurePosixPath(path.replace("\\", "/")).parts
    return ".." not in parts


class SevenZip:
    def __init__(self, exe: Path, password: str):
        if not password:
            raise SevenZipError("Thiếu SHOPONLINE_BACKUP_PASSWORD")
        self.exe = exe
        self._password = password

    def __repr__(self) -> str:  # never show the password
        return f"SevenZip({self.exe})"

    def _run(
        self, args: list[str], *, cwd: Path | None = None, password: bool = True
    ) -> subprocess.CompletedProcess:
        data = (self._password + "\n").encode() if password else None
        return subprocess.run(
            [str(self.exe), *args],
            input=data,
            stdin=None if password else subprocess.DEVNULL,
            capture_output=True,
            cwd=cwd,
            check=False,
        )

    @staticmethod
    def _fail(what: str, result: subprocess.CompletedProcess) -> SevenZipError:
        text = (result.stderr or result.stdout or b"").decode("utf-8", "replace")
        tail = " | ".join(line.strip() for line in text.splitlines() if line.strip())[-300:]
        return SevenZipError(f"{what} (7-Zip mã {result.returncode}): {tail}")

    def create(self, archive: Path, members: Iterable[str], cwd: Path) -> None:
        """Add `members` (paths relative to cwd) to a new encrypted archive."""
        result = self._run(
            ["a", "-t7z", "-mhe=on", "-mx=5", "-p", "-y", str(archive), *members], cwd=cwd
        )
        if result.returncode != 0:
            raise self._fail("7-Zip lỗi khi tạo bản mã hóa", result)

    def test(self, archive: Path) -> None:
        result = self._run(["t", str(archive)])
        if result.returncode != 0:
            raise self._fail("Kiểm tra bản sao lưu thất bại (sai mật khẩu hoặc file hỏng)", result)

    def list(self, archive: Path) -> list[Entry]:
        result = self._run(["l", "-slt", str(archive)])
        if result.returncode != 0:
            raise self._fail("Không mở được bản sao lưu (sai mật khẩu hoặc file hỏng)", result)
        return _parse_listing(result.stdout.decode("utf-8", "replace"))

    def require_encrypted(self, archive: Path) -> list[Entry]:
        """Refuse an archive anyone could read: listing without a password must fail (hidden
        names) and every member must be encrypted. Returns the members."""
        bare = self._run(["l", "-slt", str(archive)], password=False)
        if bare.returncode == 0:
            raise SevenZipError("Bản sao lưu không mã hóa tên file: không nhận")
        entries = self.list(archive)
        if not entries or any(not e.encrypted for e in entries if not e.is_dir):
            raise SevenZipError("Bản sao lưu có phần không mã hóa: không nhận")
        return entries

    def extract(
        self, archive: Path, dest: Path, allowed: Callable[[str], bool] = lambda _p: True
    ) -> list[Entry]:
        """Extract after checking every member name and that the contents fit on the disk."""
        entries = self.require_encrypted(archive)
        for entry in entries:
            if not safe_member(entry.path):
                raise SevenZipError(f"Bản sao lưu có đường dẫn không an toàn: {entry.path}")
            if not allowed(entry.path.replace("\\", "/")):
                raise SevenZipError(f"Bản sao lưu có phần lạ: {entry.path}")
        total = sum(e.size for e in entries)
        dest.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(dest).free
        if total > free:
            raise SevenZipError(
                f"Không đủ chỗ trống để giải nén ({total // 2**20} MB cần, {free // 2**20} MB còn)"
            )
        result = self._run(["x", "-y", f"-o{dest}", str(archive)])
        if result.returncode != 0:
            raise self._fail("Giải nén bản sao lưu thất bại", result)
        return entries


def _parse_listing(text: str) -> list[Entry]:
    _, _, body = text.partition("\n----------")
    entries = []
    for block in re.split(r"\r?\n\s*\r?\n", body):
        fields = {}
        for line in block.splitlines():
            key, sep, value = line.partition(" = ")
            if sep:
                fields[key.strip()] = value.strip()
        if "Path" not in fields:
            continue
        entries.append(
            Entry(
                path=fields["Path"],
                is_dir=fields.get("Folder") == "+" or "D" in fields.get("Attributes", "")[:1],
                size=int(fields.get("Size") or 0),
                encrypted=fields.get("Encrypted") == "+",
            )
        )
    return entries


class RedactFilter(logging.Filter):
    """Scrub "-p<value>" and the backup password itself from every log record."""

    _SWITCH = re.compile(r"(?<!\S)-p\S+")

    def __init__(self, secret: str = ""):
        super().__init__()
        self.secret = secret

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        cleaned = self._SWITCH.sub("-p***", message)
        if self.secret:
            cleaned = cleaned.replace(self.secret, "***")
        if cleaned != message:
            record.msg, record.args = cleaned, None
        return True
