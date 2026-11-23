"""7-Zip wrapper (refuses unencrypted archives and unsafe names, never leaks the password) and
the work folders that hold decrypted contents."""

from __future__ import annotations

import logging
import os
import subprocess
import time

import pytest

from shoponline.backup import staging
from shoponline.backup.sevenzip import RedactFilter, SevenZip, SevenZipError, safe_member

PASSWORD = "zip-secret-42"


def test_safe_member_names():
    assert safe_member("data/uploads/a.xlsx")
    for bad in ("../x", "data/../../x", "..\\x", "C:\\x", "/etc/passwd", "\\\\host\\share"):
        assert not safe_member(bad), bad


def test_round_trip_and_hidden_names(seven_zip, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("hello", encoding="utf-8")
    archive = tmp_path / "x.7z"
    zipper = SevenZip(seven_zip, PASSWORD)
    zipper.create(archive, ["a.txt"], cwd=src)
    zipper.test(archive)
    entries = zipper.require_encrypted(archive)
    assert [e.path for e in entries] == ["a.txt"] and entries[0].encrypted
    zipper.extract(archive, tmp_path / "out")
    assert (tmp_path / "out" / "a.txt").read_text(encoding="utf-8") == "hello"
    with pytest.raises(SevenZipError):
        SevenZip(seven_zip, "wrong-password").test(archive)


def test_unencrypted_archive_is_refused(seven_zip, tmp_path):
    (tmp_path / "a.txt").write_text("plain", encoding="utf-8")
    archive = tmp_path / "plain.7z"
    subprocess.run(
        [str(seven_zip), "a", str(archive), "a.txt"], cwd=tmp_path, check=True, capture_output=True
    )
    with pytest.raises(SevenZipError, match="không mã hóa"):
        SevenZip(seven_zip, PASSWORD).require_encrypted(archive)


def test_names_visible_without_password_are_refused(seven_zip, tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    archive = tmp_path / "visible.7z"
    subprocess.run(
        [str(seven_zip), "a", "-p", str(archive), "a.txt"],
        cwd=tmp_path,
        input=(PASSWORD + "\n").encode(),
        check=True,
        capture_output=True,
    )
    with pytest.raises(SevenZipError, match="không mã hóa"):
        SevenZip(seven_zip, PASSWORD).require_encrypted(archive)


def test_member_outside_the_allowed_list_is_refused(seven_zip, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "evil.exe").write_bytes(b"MZ")
    archive = tmp_path / "x.7z"
    zipper = SevenZip(seven_zip, PASSWORD)
    zipper.create(archive, ["evil.exe"], cwd=src)
    with pytest.raises(SevenZipError, match="phần lạ"):
        zipper.extract(archive, tmp_path / "out", allowed=lambda p: p.endswith(".dump"))
    assert not (tmp_path / "out" / "evil.exe").exists()


def test_password_never_in_errors_or_logs(seven_zip, tmp_path, caplog):
    broken = tmp_path / "broken.7z"
    broken.write_bytes(b"7z\xbc\xaf\x27\x1c" + os.urandom(64))
    logger = logging.getLogger("shoponline.backup.test")
    caplog.handler.addFilter(RedactFilter(PASSWORD))
    with caplog.at_level(logging.INFO), pytest.raises(SevenZipError) as err:
        try:
            SevenZip(seven_zip, PASSWORD).test(broken)
        except SevenZipError as exc:
            logger.error("7z lỗi: %s, đã chạy với -p%s", exc, PASSWORD)
            raise
    assert PASSWORD not in str(err.value)
    assert PASSWORD not in caplog.text and "-p***" in caplog.text
    assert PASSWORD not in repr(SevenZip(seven_zip, PASSWORD))


def test_staging_dir_is_removed_even_on_error(tmp_path):
    root = tmp_path / "backup-work"
    with pytest.raises(RuntimeError), staging.staging_dir(root) as work:
        (work / "secret.dump").write_bytes(b"x")
        raise RuntimeError("boom")
    assert list(root.iterdir()) == []


def test_sweep_stale_keeps_recent_and_week_old_restore_folders(tmp_path):
    root = tmp_path / "backup-work"
    for name in ("old-work", "fresh-work", "before-restore-1", "before-restore-2"):
        (root / name).mkdir(parents=True)
    now = time.time()
    day = 24 * 3600
    os.utime(root / "old-work", (now - 2 * day, now - 2 * day))
    os.utime(root / "before-restore-1", (now - 3 * day, now - 3 * day))
    os.utime(root / "before-restore-2", (now - 8 * day, now - 8 * day))
    removed = {p.name for p in staging.sweep_stale(root, now)}
    assert removed == {"old-work", "before-restore-2"}
    assert sorted(p.name for p in root.iterdir()) == ["before-restore-1", "fresh-work"]
