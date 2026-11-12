"""Screen element IDs by logical name, read from config/sap_screens.yaml (taken from recordings).

Elements are reached only through the guarded session; keys and T-codes live in guard.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from shoponline.saprobot.errors import ScreenConfigMissing
from shoponline.saprobot.guard import GuardedElement, GuardedSession


@dataclass(frozen=True)
class Screens:
    elements: dict[str, dict[str, str]]

    @classmethod
    def load(cls, path: Path) -> Screens:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        screens = data.get("screens") or {}
        if not isinstance(screens, dict) or not all(isinstance(v, dict) for v in screens.values()):
            raise ValueError(f"{path}: 'screens' phải là bảng tên màn hình → tên phần tử → ID")
        return cls({name: {k: str(v) for k, v in els.items()} for name, els in screens.items()})

    def id(self, screen: str, element: str) -> str:
        try:
            return self.elements[screen][element]
        except KeyError as exc:
            raise ScreenConfigMissing(
                f"Thiếu ID '{screen}.{element}' trong config/sap_screens.yaml"
            ) from exc

    def find(self, session: GuardedSession, screen: str, element: str) -> GuardedElement:
        return session.find(self.id(screen, element))

    def set_text(self, session: GuardedSession, screen: str, element: str, value: str) -> None:
        self.find(session, screen, element).set_text(value)

    def press(self, session: GuardedSession, screen: str, element: str) -> None:
        self.find(session, screen, element).press()
