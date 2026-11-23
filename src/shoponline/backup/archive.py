"""Build the contents of a backup in a work folder, then the manifest describing them.

    db    database.dump            pg_dump -Fc of schemas public and ops
          accounting-files/        the accounting files sent to accounting (they exist only in
                                   the data folder, and the full backup is weekly)
    app   source.bundle            git bundle of the running commit
          env                      the env file without SHOPONLINE_BACKUP_PASSWORD
          config/                  the repo's config folder
          data/                    the data folder without robot-work, backup-work, logs
    full  both of the above

A broken or missing git only adds a warning to the manifest; the database part still counts.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from shoponline.backup import manifest as mf
from shoponline.backup import pgtools
from shoponline.config import Settings

DUMP = "database.dump"
BUNDLE = "source.bundle"
ENV = "env"
CONFIG = "config"
DATA = "data"
ACCOUNTING = "accounting-files"
ACCOUNTING_KIND = "accounting_file"
PASSWORD_VARIABLE = "SHOPONLINE_BACKUP_PASSWORD"
# Never copied from the data folder: rebuilt, being written, or this machine's own state.
DATA_SKIP = {
    "robot-work",
    "backup-work",
    "logs",
    "last-backup.txt",
    "maintenance.json",
    "restore-status.json",
    "released.json",
}


@dataclass(frozen=True)
class Sources:
    settings: Settings
    repo_root: Path
    pg_bin: Path | None = None  # only needed for kinds with a database part

    @property
    def env_file(self) -> Path:
        return self.repo_root / ".env"


def top_level_members(kind: str) -> list[str]:
    members = [mf.NAME]
    if kind in ("db", "full"):
        members.append(DUMP)
    if kind == "db":
        members.append(ACCOUNTING)
    if kind in ("app", "full"):
        members += [BUNDLE, ENV, CONFIG, DATA]
    return members


def allowed_member(path: str) -> bool:
    """Member names a backup of this system may contain (old backups hold one *.dump)."""
    top = path.split("/", 1)[0]
    if top in (mf.NAME, DUMP, BUNDLE, ENV, CONFIG, DATA, ACCOUNTING):
        return True
    return "/" not in path and path.endswith(".dump")


def build(kind: str, reason: str, src: Sources, dest: Path) -> mf.Manifest:
    """Write the parts of a `kind` backup into dest and return its manifest (also written)."""
    settings = src.settings
    manifest = mf.Manifest(
        kind=kind,
        reason=reason,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        database=pgtools.database_name(settings.database_url),
    )
    manifest.commit = _git(src.repo_root, ["rev-parse", "HEAD"], manifest.warnings)
    if kind in ("db", "full"):
        _dump_database(src, dest / DUMP, manifest)
    if kind == "db":
        _copy_accounting_files(src, dest / ACCOUNTING, manifest)
    if kind in ("app", "full"):
        if _git(src.repo_root, ["bundle", "create", str(dest / BUNDLE), "HEAD"], []) is None:
            manifest.warnings.append("Không tạo được git bundle; bản này không có mã nguồn")
            (dest / BUNDLE).unlink(missing_ok=True)
        _write_env(src.env_file, dest / ENV, manifest)
        if (src.repo_root / CONFIG).is_dir():
            shutil.copytree(src.repo_root / CONFIG, dest / CONFIG)
        _copy_data(settings, dest / DATA)
        if reason in ("schedule", "manual"):
            manifest.warnings.append(
                "Thư mục dữ liệu được chép khi web vẫn chạy, có thể lệch vài giây với database"
            )
    manifest.parts = mf.hash_parts(dest)
    (dest / mf.NAME).write_text(manifest.to_json(), encoding="utf-8")
    return manifest


def _dump_database(src: Sources, target: Path, manifest: mf.Manifest) -> None:
    """Count rows and dump inside one exported snapshot, so the counts match the dump."""
    if src.pg_bin is None:
        raise pgtools.PgToolError("Thiếu thư mục PostgreSQL bin")
    engine = create_engine(src.settings.database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            conn = conn.execution_options(isolation_level="REPEATABLE READ")
            with conn.begin():
                snapshot = conn.execute(text("SELECT pg_export_snapshot()")).scalar_one()
                manifest.tables = mf.count_public_rows(conn)
                manifest.alembic_revision = mf.alembic_revision(conn)
                manifest.postgres_version = conn.execute(text("SHOW server_version")).scalar()
                # pg_dump reads the snapshot while this transaction keeps it alive.
                pgtools.run(
                    src.pg_bin,
                    "pg_dump",
                    src.settings.database_url,
                    ["-Fc", f"--snapshot={snapshot}", "-f", str(target)],
                )
    finally:
        engine.dispose()


def _copy_accounting_files(src: Sources, target: Path, manifest: mf.Manifest) -> None:
    """Copy every accounting file the database knows into target. A missing file is a warning,
    not a failure: the database part of the backup still counts."""
    engine = create_engine(src.settings.database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            paths = conn.execute(
                text("SELECT stored_path FROM generated_file WHERE kind = :kind ORDER BY id"),
                {"kind": ACCOUNTING_KIND},
            ).scalars()
            paths = [Path(p) for p in paths]
    finally:
        engine.dispose()
    target.mkdir()
    for path in paths:
        try:
            shutil.copy2(path, target / path.name)
        except OSError as exc:
            manifest.warnings.append(f"Không chép được file kế toán {path.name}: {exc.strerror}")


def _git(repo: Path, args: list[str], warnings: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
        )
    except OSError:
        warnings.append("Không thấy git")
        return None
    if result.returncode != 0:
        warnings.append(f"git {args[0]} lỗi: {result.stderr.strip()[-200:]}")
        return None
    return result.stdout.strip()


def _write_env(env_file: Path, target: Path, manifest: mf.Manifest) -> None:
    if not env_file.is_file():
        manifest.warnings.append("Không có file .env")
        return
    kept = [
        line
        for line in env_file.read_text(encoding="utf-8").splitlines()
        if line.split("=", 1)[0].strip() != PASSWORD_VARIABLE
    ]
    target.write_text("\n".join(kept) + "\n", encoding="utf-8")


def _copy_data(settings: Settings, target: Path) -> None:
    source = settings.data_dir
    target.mkdir()
    if not source.is_dir():
        return
    # A backup folder inside the data folder would put every earlier backup into this one.
    inside = {d.resolve() for d in settings.backup_dirs}
    for child in source.iterdir():
        if child.name in DATA_SKIP or child.resolve() in inside:
            continue
        if child.is_dir():
            shutil.copytree(child, target / child.name, ignore=_skip_backup_dirs(inside))
        else:
            shutil.copy2(child, target / child.name)


def _skip_backup_dirs(inside: set[Path]):
    def ignore(folder: str, names: list[str]) -> list[str]:
        return [n for n in names if (Path(folder) / n).resolve() in inside]

    return ignore
