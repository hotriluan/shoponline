"""Text that goes into an Office XML part: one line, no characters XML 1.0 forbids."""

from __future__ import annotations

import re

# XML 1.0 allows tab, line feed, carriage return and everything from space up, except the
# surrogate block and the two non-characters at the top of the basic plane.
_INVALID_XML = re.compile("[^\\t\\n\\r -\\ud7ff\\ue000-\\ufffd\\U00010000-\\U0010ffff]")
_WHITESPACE = re.compile(r"\s+")


def clean_text(value: str) -> str:
    """One line of text safe to put in a Word run or an Excel cell: no forbidden characters, any
    run of spaces, tabs or line breaks becomes one space."""
    return _WHITESPACE.sub(" ", _INVALID_XML.sub("", value or "")).strip()
