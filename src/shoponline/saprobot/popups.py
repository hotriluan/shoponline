"""Recognize dialog windows by title and text; only dialogs listed in config are answered."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from shoponline.saprobot.errors import UnknownPopup
from shoponline.saprobot.guard import GuardedSession

MAX_POPUPS_PER_STEP = 5


@dataclass(frozen=True)
class PopupRule:
    name: str
    title_contains: str
    text_contains: str
    button: str  # element ID relative to the dialog, e.g. "tbar[0]/btn[0]"
    outcome: str | None = None  # signal returned to the transaction, e.g. "no_data"

    def matches(self, title: str, text: str) -> bool:
        return (
            self.title_contains.casefold() in title.casefold()
            and self.text_contains.casefold() in text.casefold()
        )


@dataclass(frozen=True)
class SeenPopup:
    rule: str
    title: str
    text: str
    outcome: str | None


def load_rules(path: Path) -> list[PopupRule]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules = []
    for i, raw in enumerate(data.get("popups") or []):
        try:
            rules.append(
                PopupRule(
                    name=str(raw["name"]),
                    title_contains=str(raw.get("title_contains") or ""),
                    text_contains=str(raw.get("text_contains") or ""),
                    button=str(raw["button"]),
                    outcome=raw.get("outcome"),
                )
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"{path}: mục popup thứ {i + 1} thiếu name hoặc button") from exc
        if not (rules[-1].title_contains or rules[-1].text_contains):
            raise ValueError(
                f"{path}: popup {rules[-1].name} cần title_contains hoặc text_contains"
            )
    return rules


def handle_popups(session: GuardedSession, rules: list[PopupRule]) -> list[SeenPopup]:
    """Answer the known dialogs on top of the main window, newest first.

    An unknown dialog stays open (for the screenshot) and raises UnknownPopup. Pressing the
    answer goes through the guard, so a dialog that leads to another T-code trips it.
    """
    seen: list[SeenPopup] = []
    for _ in range(MAX_POPUPS_PER_STEP):
        count = session.window_count()
        if count <= 1:
            return seen
        title, text = session.window_text(count - 1)
        rule = next((r for r in rules if r.matches(title, text)), None)
        if rule is None:
            raise UnknownPopup(f"Cửa sổ lạ: '{title}' {text!r}".strip())
        session.find(f"wnd[{count - 1}]/{rule.button}").press()
        seen.append(SeenPopup(rule.name, title, text, rule.outcome))
    raise UnknownPopup(f"Quá {MAX_POPUPS_PER_STEP} cửa sổ phụ liên tiếp")
