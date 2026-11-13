"""SAP connection settings kept in the database, with the environment as the fallback.

The web edits them and the robot reads them for every job. The password is not here: it stays
on the robot machine (see shoponline.saprobot.credentials).

Callers own the transaction: every function flushes, none commits.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shoponline.config import ConfigError
from shoponline.db.models import RobotControl, SapSetting
from shoponline.domain import states
from shoponline.sapjobs.queue import SapTarget

HEARTBEAT_STALE = timedelta(seconds=30)
DEFAULT_MAX_FAILURES = 3
DEFAULT_EVIDENCE_KEEP_DAYS = 30
EDITABLE = (
    "system",
    "client",
    "connection",
    "sap_user",
    "language",
    "max_failures",
    "evidence_keep_days",
)


class SapSettingsError(ValueError):
    """The submitted settings are not valid; the message says which field and why."""


@dataclass(frozen=True)
class SapSettings:
    system: str
    client: str
    connection: str
    sap_user: str
    language: str
    max_failures: int
    evidence_keep_days: int
    verified_system: str | None
    verified_client: str | None

    @property
    def target(self) -> SapTarget | None:
        return SapTarget(self.system, self.client) if self.system and self.client else None

    @property
    def target_verified(self) -> bool:
        """A connection check succeeded for exactly the configured system and client."""
        target = self.target
        return (
            target is not None
            and self.verified_system == target.system
            and self.verified_client == target.client
        )


# ---------------------------------------------------------------- environment fallback


def _env_text(env: Mapping[str, str], name: str) -> str | None:
    value = (env.get(name) or "").strip()
    return value or None


def _env_positive_int(env: Mapping[str, str], name: str) -> int | None:
    text = _env_text(env, name)
    if text is None:
        return None
    if not text.isdigit() or int(text) < 1:
        raise ConfigError(f"{name} phải là số nguyên dương")
    return int(text)


def env_defaults(env: Mapping[str, str]) -> dict:
    system = (_env_text(env, "SHOPONLINE_SAP_SYSTEM") or "").upper() or None
    client = _env_text(env, "SHOPONLINE_SAP_CLIENT")
    if bool(system) != bool(client):
        raise ConfigError("Đặt cả SHOPONLINE_SAP_SYSTEM và SHOPONLINE_SAP_CLIENT, hoặc bỏ cả hai")
    return {
        "system": system,
        "client": client,
        "connection": _env_text(env, "SHOPONLINE_SAP_CONNECTION"),
        "sap_user": _env_text(env, "SHOPONLINE_SAP_USER"),
        "language": _env_text(env, "SHOPONLINE_SAP_LANGUAGE"),
        "max_failures": _env_positive_int(env, "SHOPONLINE_ROBOT_MAX_FAILURES"),
        "evidence_keep_days": _env_positive_int(env, "SHOPONLINE_ROBOT_EVIDENCE_KEEP_DAYS"),
    }


# ---------------------------------------------------------------- load / save


def _row(db: Session, env: Mapping[str, str]) -> SapSetting:
    """The single row; the first call creates it from the environment.

    A running installation that already has SYSTEM and CLIENT in its environment is treated as
    verified, so the robot is not locked out by the upgrade.
    """
    row = db.get(SapSetting, 1)
    if row is not None:
        return row
    values = env_defaults(env)
    row = SapSetting(id=1, changed_by="env", changed_at=datetime.now(UTC), **values)
    if values["system"]:
        row.verified_system, row.verified_client = values["system"], values["client"]
        row.verified_at = row.changed_at
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:  # the web and the robot started at the same moment
        db.expire_all()
        return db.get(SapSetting, 1)
    return row


def _effective(row: SapSetting, env: Mapping[str, str]) -> dict:
    fallback = env_defaults(env)
    return {name: _pick(getattr(row, name), fallback[name]) for name in EDITABLE}


def _pick(stored, fallback):
    return fallback if stored is None else stored


def load(db: Session, env: Mapping[str, str]) -> SapSettings:
    row = _row(db, env)
    values = _effective(row, env)
    return SapSettings(
        system=values["system"] or "",
        client=values["client"] or "",
        connection=values["connection"] or "",
        sap_user=values["sap_user"] or "",
        language=values["language"] or "",
        max_failures=values["max_failures"] or DEFAULT_MAX_FAILURES,
        evidence_keep_days=values["evidence_keep_days"] or DEFAULT_EVIDENCE_KEEP_DAYS,
        verified_system=row.verified_system,
        verified_client=row.verified_client,
    )


_SYSTEM = re.compile(r"[A-Z0-9]{3}")
_CLIENT = re.compile(r"\d{3}")
_LANGUAGE = re.compile(r"[A-Za-z]{2}")


def _positive(name: str, label: str, value) -> int:
    text = str(value).strip()
    if not text.isdigit() or int(text) < 1:
        raise SapSettingsError(f"{label} phải là số nguyên dương")
    return int(text)


def _clean(fields: dict) -> dict:
    unknown = set(fields) - set(EDITABLE)
    if unknown:
        raise SapSettingsError("Trường không có trong cấu hình: " + ", ".join(sorted(unknown)))
    clean: dict = {}
    for name, value in fields.items():
        if name in ("max_failures", "evidence_keep_days"):
            label = "Số lỗi tối đa" if name == "max_failures" else "Số ngày giữ ảnh"
            clean[name] = _positive(name, label, value)
        else:
            clean[name] = (value or "").strip()
    if "system" in clean:
        clean["system"] = clean["system"].upper()
    if "language" in clean:
        clean["language"] = clean["language"].upper()
    return clean


def _check_rules(merged: dict) -> None:
    system, client = merged["system"] or "", merged["client"] or ""
    if bool(system) != bool(client):
        raise SapSettingsError("Đặt cả hệ thống và client, hoặc bỏ trống cả hai")
    if system and not _SYSTEM.fullmatch(system):
        raise SapSettingsError("Hệ thống gồm đúng 3 ký tự chữ hoặc số, ví dụ AEP")
    if client and not _CLIENT.fullmatch(client):
        raise SapSettingsError("Client gồm đúng 3 chữ số, ví dụ 300")
    if system and not (merged["sap_user"] or "").strip():
        raise SapSettingsError("User SAP không được để trống")
    language = merged["language"] or ""
    if language and not _LANGUAGE.fullmatch(language):
        raise SapSettingsError("Ngôn ngữ để trống hoặc gồm 2 chữ cái, ví dụ EN")


def _normalized(values: dict) -> dict:
    """What the robot would use: empty text for unset text, the default for unset numbers."""
    defaults = {
        "max_failures": DEFAULT_MAX_FAILURES,
        "evidence_keep_days": DEFAULT_EVIDENCE_KEEP_DAYS,
    }
    return {
        name: value if value is not None else defaults.get(name, "")
        for name, value in values.items()
    }


def save(db: Session, actor: str, env: Mapping[str, str], **fields) -> dict:
    """Validate and store the given fields; returns {field: [old, new]} for what changed.

    Changing the system or the client drops the verification: the robot reads no report until a
    connection check succeeds for the new target.
    """
    clean = _clean(fields)
    row = _row(db, env)
    before = _normalized(_effective(row, env))
    merged = {**before, **clean}
    _check_rules(merged)
    changes = {name: [before[name], merged[name]] for name in clean if before[name] != merged[name]}
    for name in clean:
        setattr(row, name, merged[name])
    if "system" in changes or "client" in changes:
        row.verified_system = row.verified_client = row.verified_at = None
    if changes:
        row.changed_by, row.changed_at = actor, datetime.now(UTC)
        db.flush()
        states.log_event(db, actor, "sap_settings_changed", detail=changes)
    return changes


def mark_verified(db: Session, env: Mapping[str, str], system: str, client: str) -> bool:
    """Record a successful check, but only when it was for the target configured right now."""
    current = load(db, env)
    if current.target != SapTarget(system, client):
        return False
    row = _row(db, env)
    row.verified_system, row.verified_client = system, client
    row.verified_at = datetime.now(UTC)
    db.flush()
    return True


def robot_alive(
    control: RobotControl, now: datetime | None = None, stale: timedelta = HEARTBEAT_STALE
) -> bool:
    seen = control.last_seen_at
    if seen is None:
        return False
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=UTC)
    return (now or datetime.now(UTC)) - seen <= stale
