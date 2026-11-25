"""Province names as written in the accountants' history file, resolved to the 34 provinces
that exist after the 2025 merger (Nghị quyết 202/2025/QH15).

The merger joined whole provinces, so a pre-merger province name maps to exactly one new
province. District or city names ("Thành Phố Phan Thiết") do not: they stay unresolved until an
admin maps them on the province-alias page.
"""

from __future__ import annotations

import re
import unicodedata

from shoponline.domain.districts import DISTRICTS
from shoponline.domain.report_names import PROVINCES

# new province -> the old provinces joined into it (the new name itself is added separately)
MERGED = {
    "Huế": ("Thừa Thiên Huế",),
    "Tuyên Quang": ("Hà Giang",),
    "Lào Cai": ("Yên Bái",),
    "Thái Nguyên": ("Bắc Kạn",),
    "Phú Thọ": ("Vĩnh Phúc", "Hòa Bình"),
    "Bắc Ninh": ("Bắc Giang",),
    "Hưng Yên": ("Thái Bình",),
    "Hải Phòng": ("Hải Dương",),
    "Ninh Bình": ("Hà Nam", "Nam Định"),
    "Quảng Trị": ("Quảng Bình",),
    "Đà Nẵng": ("Quảng Nam",),
    "Quảng Ngãi": ("Kon Tum",),
    "Gia Lai": ("Bình Định",),
    "Khánh Hòa": ("Ninh Thuận",),
    "Lâm Đồng": ("Đắk Nông", "Bình Thuận"),
    "Đắk Lắk": ("Phú Yên",),
    "Hồ Chí Minh": ("Bình Dương", "Bà Rịa - Vũng Tàu"),
    "Đồng Nai": ("Bình Phước",),
    "Tây Ninh": ("Long An",),
    "Cần Thơ": ("Sóc Trăng", "Hậu Giang"),
    "Vĩnh Long": ("Bến Tre", "Trà Vinh"),
    "Đồng Tháp": ("Tiền Giang",),
    "Cà Mau": ("Bạc Liêu",),
    "An Giang": ("Kiên Giang",),
}
# Other spellings the history file uses for a province (written as the file writes them).
SPELLINGS = {
    "Đăk Nông": "Lâm Đồng",
    "Đăk Lắk": "Đắk Lắk",
    "Bà Rịa Vũng Tàu": "Hồ Chí Minh",
    "Vũng Tàu": "Hồ Chí Minh",
    "Sài Gòn": "Hồ Chí Minh",
    "TP HCM": "Hồ Chí Minh",
    "TPHCM": "Hồ Chí Minh",
    "Hồ Chí Minh City": "Hồ Chí Minh",
    "Ho Chi Minh": "Hồ Chí Minh",
    "Thừa Thiên - Huế": "Huế",
    "Thành Ph Hồ Chí Minh": "Hồ Chí Minh",
    "Bắk Cạn": "Thái Nguyên",
    "Bắc Nin": "Bắc Ninh",
    "Đồng Na": "Đồng Nai",
}
_PREFIXES = ("thanh pho ", "tinh ", "tp ")


def fold_key(text: str | None) -> str:
    """A name reduced to lower-case letters and digits separated by single spaces, without tone
    marks, so "Thành phố Hồ Chí Minh", "TP. Hồ Chí Minh" and "ho chi minh" meet at one key."""
    decomposed = unicodedata.normalize("NFD", (text or "").replace("đ", "d").replace("Đ", "D"))
    plain = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    key = re.sub(r"[^a-z0-9]+", " ", plain.casefold()).strip()
    for prefix in _PREFIXES:
        if key.startswith(prefix):
            return key[len(prefix) :].strip()
    return key


def _district_aliases() -> dict[str, str]:
    """key -> province for the districts and cities; a key two provinces claim is dropped."""
    found: dict[str, str | None] = {}
    prefixes = {"quan": ("quan ",), "huyen": ("huyen ",), "city": ("", "thi xa ")}
    for province, kinds in DISTRICTS.items():
        for kind, names in kinds.items():
            for name in names:
                for prefix in prefixes[kind]:
                    key = fold_key(prefix + name)
                    found[key] = province if found.get(key, province) == province else None
    return {key: province for key, province in found.items() if province}


def seed_aliases() -> dict[str, str]:
    """raw key -> new province, for every province of 2025 and before, the spellings above and
    the districts of domain.districts. A province name always wins over a district's."""
    pairs = {name: name for name in PROVINCES}
    pairs.update({old: new for new, olds in MERGED.items() for old in olds})
    pairs.update(SPELLINGS)
    aliases = _district_aliases()
    aliases.update({fold_key(raw): province for raw, province in pairs.items()})
    return aliases


def last_part(address: str | None) -> str:
    """The last comma-separated part of an address that is not the country."""
    parts = [p.strip() for p in (address or "").split(",") if p.strip()]
    if parts and fold_key(parts[-1]) == "viet nam":
        parts.pop()
    return parts[-1] if parts else ""


def place_key(address: str | None) -> str | None:
    """The folded last part of an address: the key the reports look up in province_alias."""
    return fold_key(last_part(address)) or None


def resolve(raw: str | None, aliases: dict[str, str]) -> str | None:
    """The province the raw text names, or None."""
    return aliases.get(fold_key(raw)) if raw and raw.strip() else None
