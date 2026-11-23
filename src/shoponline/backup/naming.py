"""Backup file names: shoponline-<kind>-<db>-yyyyMMdd-HHmmss.7z.

The time in the name is Vietnam time and is what rotation goes by, so a copied folder rotates
the same way. Names from before the backup kinds (shoponline-<db>-yyyyMMdd-HHmmss.7z) are
database backups.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from shoponline.clock import VIETNAM

_NEW = re.compile(r"^shoponline-(db|app|full)-([A-Za-z0-9_]+)-(\d{8}-\d{6})\.7z$")
# The database part has no hyphen, so a new name never matches the old pattern.
_OLD = re.compile(r"^shoponline-([A-Za-z0-9_]+)-(\d{8}-\d{6})\.7z$")
_STAMP = "%Y%m%d-%H%M%S"


@dataclass(frozen=True)
class BackupName:
    name: str
    kind: str
    database: str
    taken_at: datetime  # aware, Vietnam time
    legacy: bool = False


def parse(name: str) -> BackupName | None:
    """The parts of a backup file name, or None for any other file."""
    match = _NEW.match(name)
    legacy = match is None
    if legacy:
        match = _OLD.match(name)
        if match is None:
            return None
        kind, database, stamp = "db", match.group(1), match.group(2)
    else:
        kind, database, stamp = match.groups()
    try:
        taken = datetime.strptime(stamp, _STAMP).replace(tzinfo=VIETNAM)
    except ValueError:
        return None
    return BackupName(name, kind, database, taken, legacy)


def make(kind: str, database: str, now: datetime | None = None) -> str:
    moment = (now or datetime.now(UTC)).astimezone(VIETNAM)
    return f"shoponline-{kind}-{database}-{moment.strftime(_STAMP)}.7z"
