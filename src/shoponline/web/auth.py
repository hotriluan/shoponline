"""Password hashing (stdlib scrypt) and user management helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.db.models import AppUser

ROLES = ("admin", "viewer")
_N, _R, _P = 2**14, 8, 1
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    b64 = base64.b64encode
    return f"scrypt${_N}${_R}${_P}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    expected = base64.b64decode(digest_b64)
    digest = hashlib.scrypt(
        password.encode(),
        salt=base64.b64decode(salt_b64),
        n=int(n),
        r=int(r),
        p=int(p),
        dklen=len(expected),
    )
    return hmac.compare_digest(digest, expected)


def set_user(session: Session, username: str, password: str, role: str) -> AppUser:
    """Create a user, or reset password and role of an existing one."""
    if role not in ROLES:
        raise ValueError(f"Vai trò phải là một trong {ROLES}")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Mật khẩu phải dài ít nhất {MIN_PASSWORD_LENGTH} ký tự")
    user = session.scalar(select(AppUser).where(AppUser.username == username))
    if user is None:
        user = AppUser(username=username, password_hash="", role=role, active=True)
        session.add(user)
    user.password_hash = hash_password(password)
    user.role = role
    user.active = True
    session.flush()
    return user


def authenticate(session: Session, username: str, password: str) -> AppUser | None:
    user = session.scalar(select(AppUser).where(AppUser.username == username))
    if user is None or not user.active:
        # Spend similar time as a real check to avoid revealing which usernames exist.
        verify_password(password, hash_password("timing-equalizer"))
        return None
    return user if verify_password(password, user.password_hash) else None
