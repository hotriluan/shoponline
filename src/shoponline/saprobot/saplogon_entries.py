"""The entries of SAP Logon on this machine, read from its landscape file.

The web offers them as a list, so the person picks a name instead of typing it (the entry name
must match exactly). The file is parsed again only when its modification time changes.
"""

from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from pathlib import Path

log = logging.getLogger(__name__)


def default_path() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "SAP" / "Common" / "SAPUILandscape.xml"


def parse_entries(path: Path) -> list[str]:
    root = ET.parse(path).getroot()
    names = {
        (service.get("name") or "").strip()
        for service in root.iter("Service")
        if service.get("type") == "SAPGUI"
    }
    return sorted(name for name in names if name)


class EntriesReader:
    """read() returns the entry names; a missing or broken file gives an empty list."""

    def __init__(self, path: Path | None = None):
        self.path = path or default_path()
        self._stamp: float | None = None
        self._entries: list[str] = []

    def read(self) -> list[str]:
        try:
            stamp = self.path.stat().st_mtime
            if stamp != self._stamp:
                self._entries, self._stamp = parse_entries(self.path), stamp
        except Exception as exc:  # the heartbeat must not fail because of this file
            log.warning("Không đọc được danh sách mục SAP Logon (%s): %s", self.path, exc)
            self._entries, self._stamp = [], None
        return list(self._entries)
