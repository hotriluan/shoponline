"""Text that goes into an Office XML part: one line, no characters XML 1.0 forbids."""

from __future__ import annotations

import re

_INVALID_XML = re.compile("[^\t\n\r -퟿-�\U00010000-\U0010ffff]")
_LINE_BREAKS = re.compile(r"[\r\n\t]+")


def clean_text(value: str) -> str:
    """One line of text safe to put in a Word run or an Excel cell."""
    return _LINE_BREAKS.sub(" ", _INVALID_XML.sub("", value or "")).strip()
