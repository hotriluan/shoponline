"""manifest.json inside every backup: what it is, from which code and schema, how many rows each
business table had, and the SHA-256 of every part.

The row counts are taken inside the same database snapshot pg_dump reads (see archive.py), so a
restore can be compared with them exactly.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sqlalchemy import Connection, text

FORMAT = 1
NAME = "manifest.json"


@dataclass
class Manifest:
    kind: str
    reason: str
    created_at: str  # ISO 8601, UTC
    database: str
    commit: str | None = None
    alembic_revision: str | None = None
    postgres_version: str | None = None
    tables: dict[str, int] = field(default_factory=dict)  # schema public only
    parts: dict[str, dict] = field(default_factory=dict)  # path -> {"sha256", "size"}
    warnings: list[str] = field(default_factory=list)
    format: int = FORMAT

    @property
    def row_total(self) -> int:
        return sum(self.tables.values())

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Manifest:
        known = {name for name in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def read(cls, path: Path) -> Manifest:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_parts(root: Path) -> dict[str, dict]:
    """SHA-256 and size of every file under root except the manifest itself."""
    parts = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel != NAME:
            parts[rel] = {"sha256": sha256_file(path), "size": path.stat().st_size}
    return parts


def check_parts(root: Path, manifest: Manifest) -> list[str]:
    """Parts whose content differs from the manifest (missing, changed or extra)."""
    found = hash_parts(root)
    problems = [
        rel
        for rel, want in manifest.parts.items()
        if rel not in found or found[rel]["sha256"] != want["sha256"]
    ]
    problems += [rel for rel in found if rel not in manifest.parts]
    return sorted(problems)


def count_public_rows(conn: Connection) -> dict[str, int]:
    names = conn.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
    ).scalars()
    counts = {}
    for name in list(names):
        quoted = '"' + name.replace('"', '""') + '"'
        counts[name] = conn.execute(text(f"SELECT count(*) FROM public.{quoted}")).scalar_one()
    return counts


def alembic_revision(conn: Connection) -> str | None:
    if conn.execute(text("SELECT to_regclass('public.alembic_version')")).scalar() is None:
        return None
    return conn.execute(text("SELECT version_num FROM public.alembic_version")).scalar()
