"""Values for the Shop Online history file that the platform files do not give directly.

- `province_of`: the province (one of the 34 after the 2025 merger) at the end of an address,
  written the way the history file writes it, without "Tỉnh" / "Thành phố".
- `suggest_report_name`: a first guess at itemName, size and variation of a material from the
  platform product and variation names mapped to it. Only a prefill; an admin saves it.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

PROVINCES = (
    "Hà Nội",
    "Huế",
    "Lai Châu",
    "Điện Biên",
    "Sơn La",
    "Lạng Sơn",
    "Quảng Ninh",
    "Thanh Hóa",
    "Nghệ An",
    "Hà Tĩnh",
    "Cao Bằng",
    "Tuyên Quang",
    "Lào Cai",
    "Thái Nguyên",
    "Phú Thọ",
    "Bắc Ninh",
    "Hưng Yên",
    "Hải Phòng",
    "Ninh Bình",
    "Quảng Trị",
    "Đà Nẵng",
    "Quảng Ngãi",
    "Gia Lai",
    "Khánh Hòa",
    "Lâm Đồng",
    "Đắk Lắk",
    "Hồ Chí Minh",
    "Đồng Nai",
    "Tây Ninh",
    "Cần Thơ",
    "Vĩnh Long",
    "Đồng Tháp",
    "Cà Mau",
    "An Giang",
)
PREFIXES = ("thành phố ", "tỉnh ", "tp. ", "tp ")
COUNTRY = "việt nam"
_TONE_MARKS = "̣̀́̉̃"  # huyền, sắc, hỏi, ngã, nặng
# Old tone placement ("Hoà", "Hoá") -> the placement used in PROVINCES ("Hòa", "Hóa").
_OLD_TONES = {
    unicodedata.normalize("NFC", f"{pair[0]}{pair[1]}{mark}"): unicodedata.normalize(
        "NFC", f"{pair[0]}{mark}{pair[1]}"
    )
    for pair in ("oa", "oe")
    for mark in _TONE_MARKS
}


def _key(text: str) -> str:
    key = unicodedata.normalize("NFC", text).strip().casefold()
    key = re.sub(r"\s+", " ", key)
    for old, new in _OLD_TONES.items():
        key = key.replace(old, new)
    return key


_BY_KEY = {_key(name): name for name in PROVINCES}


def province_of(address: str | None) -> str | None:
    """The province at the end of `<...>, <province>, Việt Nam`, or None when not one of the 34."""
    if not address:
        return None
    parts = [p.strip() for p in unicodedata.normalize("NFC", address).split(",") if p.strip()]
    if parts and _key(parts[-1]) == COUNTRY:
        parts.pop()
    if not parts:
        return None
    last = _key(parts[-1])
    for prefix in PREFIXES:
        if last.startswith(prefix):
            last = last[len(prefix) :].strip()
            break
    return _BY_KEY.get(last)


@dataclass(frozen=True)
class ReportNameSuggestion:
    item_name: str = ""
    size: str = ""
    variation: str = ""


ITEM_PREFIX = "Propan - "
COLOR_LABEL = "Màu sắc:"
_SIZE_ONLY = re.compile(r"^\d+([.,]\d+)?\s*(lít|l|kg|g|ml)$", re.IGNORECASE)


def _split_variation(variation_name: str) -> tuple[str, str]:
    """(color, size) from `<color>, <size>`; a variation without a comma is one or the other."""
    text = unicodedata.normalize("NFC", variation_name or "").strip()
    if "," in text:
        color, size = text.rsplit(",", 1)
        return color.strip(), size.strip()
    if _SIZE_ONLY.match(text):
        return "", text
    return text, ""


def _suggest_one(product_name: str, variation_name: str) -> ReportNameSuggestion:
    color, size = _split_variation(variation_name)
    product = unicodedata.normalize("NFC", product_name or "").strip()
    item = ""
    tail = f" - {size}"
    if size and product.startswith(ITEM_PREFIX) and product.endswith(tail):
        item = product[: -len(tail)].strip()
    return ReportNameSuggestion(item, size, f"{COLOR_LABEL}{color}" if color else "")


def _most_common(values: Iterable[str]) -> str:
    counts = Counter(v for v in values if v).most_common(2)
    if not counts or (len(counts) == 2 and counts[0][1] == counts[1][1]):
        return ""
    return counts[0][0]


def suggest_report_name(platform_names: Iterable[tuple[str, str]]) -> ReportNameSuggestion:
    """Guess from (product name, variation name) pairs of one material; "" where unsure."""
    guesses = [_suggest_one(product, variation) for product, variation in platform_names]
    return ReportNameSuggestion(
        item_name=_most_common(g.item_name for g in guesses),
        size=_most_common(g.size for g in guesses),
        variation=_most_common(g.variation for g in guesses),
    )
