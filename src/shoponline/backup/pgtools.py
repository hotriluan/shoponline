"""PostgreSQL client programs (pg_dump, pg_restore) run against a SQLAlchemy database URL.

The database password goes to the child process through PGPASSWORD in its own environment only,
never on the command line and never into this process's environment.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from sqlalchemy.engine import make_url

DEFAULT_BIN = Path(r"C:\Program Files\PostgreSQL\16\bin")


class PgToolError(RuntimeError):
    pass


def find_bin(explicit: str | Path | None = None) -> Path:
    exe = "pg_dump.exe" if os.name == "nt" else "pg_dump"
    if explicit:
        folder = Path(explicit)
        if (folder / exe).is_file():
            return folder
        raise PgToolError(f"Không thấy {exe} trong {folder}")
    if (DEFAULT_BIN / exe).is_file():
        return DEFAULT_BIN
    found = shutil.which("pg_dump")
    if found:
        return Path(found).parent
    raise PgToolError("Không thấy pg_dump; cài PostgreSQL 16 client hoặc truyền --pg-bin")


def database_name(url: str) -> str:
    return make_url(url).database or ""


def run(bin_dir: Path, program: str, url: str, args: list[str]) -> subprocess.CompletedProcess:
    """Run a PostgreSQL client program connected to url; raises PgToolError on failure."""
    parsed = make_url(url)
    env = dict(os.environ)
    if parsed.password:
        env["PGPASSWORD"] = str(parsed.password)
    exe = bin_dir / (program + (".exe" if os.name == "nt" else ""))
    command = [
        str(exe),
        "-h",
        parsed.host or "localhost",
        "-p",
        str(parsed.port or 5432),
        "-U",
        parsed.username or "",
        "-d",
        parsed.database or "",
        *args,
    ]
    result = subprocess.run(command, env=env, capture_output=True, check=False)
    if result.returncode != 0:
        tail = result.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        raise PgToolError(f"{program} lỗi (mã {result.returncode}): {' | '.join(tail)}")
    return result
