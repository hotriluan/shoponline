"""Which backups a place (a folder on this machine, or Google Drive) deletes.

Database and application backups: keep the newest keep_db / keep_app of that kind. Full
backups (every source, safety and migration included): delete those older than full_max_days,
however few are left; there is no limit on how many a place keeps inside that window. Nothing
else is exempt. Only names of this database are considered; other files are never touched.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from shoponline.backup import naming


@dataclass(frozen=True)
class KeepRules:
    keep_db: int = 15
    keep_app: int = 15
    full_max_days: int = 30

    @classmethod
    def from_settings(cls, row) -> KeepRules:
        return cls(row.keep_db, row.keep_app, row.full_max_days)


def to_delete(names: Iterable[str], database: str, rules: KeepRules, now: datetime) -> list[str]:
    parsed = [p for p in map(naming.parse, names) if p is not None and p.database == database]
    doomed: list[str] = []
    for kind, keep in (("db", rules.keep_db), ("app", rules.keep_app)):
        of_kind = sorted((p for p in parsed if p.kind == kind), key=lambda p: p.taken_at)
        doomed += [p.name for p in of_kind[: max(len(of_kind) - keep, 0)]]
    oldest = now - timedelta(days=rules.full_max_days)
    doomed += [p.name for p in parsed if p.kind == "full" and p.taken_at < oldest]
    return sorted(doomed)
