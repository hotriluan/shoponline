"""Secrets kept in the Windows Credential Manager of the account that runs the system.

The Credential Manager belongs to a Windows account, so the web, the backup and restore tasks and
the command line that sets a secret must all run as the same account. Nothing here logs a value.
"""

from __future__ import annotations

import contextlib


class CredentialStoreUnavailable(RuntimeError):
    """pywin32 is missing, so the Windows Credential Manager cannot be used."""


def _win32cred():
    try:
        import win32cred
    except ImportError as exc:
        raise CredentialStoreUnavailable("Thiếu pywin32: chạy 'uv sync --extra robot'") from exc
    return win32cred


def read(target: str) -> str | None:
    """The secret stored under target, or None when absent or the store is unavailable."""
    try:
        cred = _win32cred()
    except CredentialStoreUnavailable:
        return None
    try:
        record = cred.CredRead(target, cred.CRED_TYPE_GENERIC, 0)
    except Exception:  # not found, or the store refused: treated as "nothing stored"
        return None
    blob = record.get("CredentialBlob")
    if isinstance(blob, bytes | bytearray):
        blob = bytes(blob).decode("utf-16-le")
    return blob or None


def write(target: str, value: str, user_name: str = "shoponline", comment: str = "") -> None:
    cred = _win32cred()
    cred.CredWrite(
        {
            "Type": cred.CRED_TYPE_GENERIC,
            "TargetName": target,
            "UserName": user_name,
            "CredentialBlob": value,
            "Persist": cred.CRED_PERSIST_LOCAL_MACHINE,
            "Comment": comment,
        },
        0,
    )


def delete(target: str) -> None:
    """Remove target; absent is fine."""
    cred = _win32cred()
    with contextlib.suppress(Exception):
        cred.CredDelete(target, cred.CRED_TYPE_GENERIC, 0)
