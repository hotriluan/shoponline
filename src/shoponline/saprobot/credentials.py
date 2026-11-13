"""The SAP password of the robot user, kept in the Windows Credential Manager of the account
that runs the robot. The web and the database never see it.

SHOPONLINE_SAP_PASSWORD is still read as a fallback so an installation set up the old way keeps
working. Nothing here ever logs or returns the password except read_password.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

TARGET_PREFIX = "shoponline-sap:"
FALLBACK_VARIABLE = "SHOPONLINE_SAP_PASSWORD"


class CredentialStoreUnavailable(RuntimeError):
    """pywin32 is missing, so the Windows Credential Manager cannot be used."""


def _win32cred():
    try:
        import win32cred
    except ImportError as exc:
        raise CredentialStoreUnavailable("Thiếu pywin32: chạy 'uv sync --extra robot'") from exc
    return win32cred


def target_name(user: str) -> str:
    return TARGET_PREFIX + user.strip().upper()


def _stored(user: str) -> str | None:
    try:
        cred = _win32cred()
    except CredentialStoreUnavailable:
        return None
    try:
        record = cred.CredRead(target_name(user), cred.CRED_TYPE_GENERIC, 0)
    except Exception:  # not found, or the store refused: treated as "no password stored"
        return None
    blob = record.get("CredentialBlob")
    if isinstance(blob, bytes | bytearray):
        blob = bytes(blob).decode("utf-16-le")
    return blob or None


def read_password(user: str, env: Mapping[str, str] | None = None) -> str | None:
    """The stored password of user, else the environment fallback, else None."""
    if not user.strip():
        return None
    found = _stored(user)
    if found:
        return found
    return dict(os.environ if env is None else env).get(FALLBACK_VARIABLE) or None


def store_password(user: str, password: str) -> None:
    cred = _win32cred()
    cred.CredWrite(
        {
            "Type": cred.CRED_TYPE_GENERIC,
            "TargetName": target_name(user),
            "UserName": user.strip().upper(),
            "CredentialBlob": password,
            "Persist": cred.CRED_PERSIST_LOCAL_MACHINE,
            "Comment": "shoponline SAP robot",
        },
        0,
    )
