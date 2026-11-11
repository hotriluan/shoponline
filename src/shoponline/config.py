"""Settings read from environment variables (optionally seeded from a local .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REQUIRED_VARS = (
    "SHOPONLINE_DATABASE_URL",
    "SHOPONLINE_SECRET_KEY",
    "SHOPONLINE_DATA_DIR",
)


class ConfigError(RuntimeError):
    """Raised when required settings are missing or invalid."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str
    data_dir: Path
    web_host: str = "127.0.0.1"
    web_port: int = 8750

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def backup_marker(self) -> Path:
        return self.data_dir / "last-backup.txt"


def load_dotenv(path: Path) -> None:
    """Set variables from a KEY=VALUE file without overriding the real environment."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if value and key not in os.environ:
            os.environ[key] = value


def load_settings(env: dict[str, str] | None = None) -> Settings:
    if env is None:
        load_dotenv(Path.cwd() / ".env")
        env = dict(os.environ)
    missing = [name for name in REQUIRED_VARS if not env.get(name)]
    if missing:
        raise ConfigError("Thiếu biến môi trường: " + ", ".join(missing))
    secret = env["SHOPONLINE_SECRET_KEY"]
    if len(secret) < 32:
        raise ConfigError("SHOPONLINE_SECRET_KEY phải dài ít nhất 32 ký tự")
    port_text = env.get("SHOPONLINE_WEB_PORT") or "8750"
    if not port_text.isdigit():
        raise ConfigError("SHOPONLINE_WEB_PORT phải là số")
    return Settings(
        database_url=env["SHOPONLINE_DATABASE_URL"],
        secret_key=secret,
        data_dir=Path(env["SHOPONLINE_DATA_DIR"]),
        web_host=env.get("SHOPONLINE_WEB_HOST") or "127.0.0.1",
        web_port=int(port_text),
    )
