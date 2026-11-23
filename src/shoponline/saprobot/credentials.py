"""The SAP password of the robot user, kept in the Windows Credential Manager of the account
that runs the robot. The web and the database never see it.

SHOPONLINE_SAP_PASSWORD is still read as a fallback so an installation set up the old way keeps
working. Nothing here ever logs or returns the password except read_password.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from shoponline import secrets_store
from shoponline.secrets_store import CredentialStoreUnavailable  # noqa: F401 - re-exported

TARGET_PREFIX = "shoponline-sap:"
FALLBACK_VARIABLE = "SHOPONLINE_SAP_PASSWORD"


def target_name(user: str) -> str:
    return TARGET_PREFIX + user.strip().upper()


def _stored(user: str) -> str | None:
    return secrets_store.read(target_name(user))


def read_password(user: str, env: Mapping[str, str] | None = None) -> str | None:
    """The stored password of user, else the environment fallback, else None."""
    if not user.strip():
        return None
    found = _stored(user)
    if found:
        return found
    return dict(os.environ if env is None else env).get(FALLBACK_VARIABLE) or None


def store_password(user: str, password: str) -> None:
    secrets_store.write(
        target_name(user), password, user.strip().upper(), "shoponline SAP robot"
    )
