"""Read the recipient's name and address from shipping label PDFs (Shopee SPX, TikTok J&T).

A PDF is an untrusted file: the reader checks the signature, size and page count first, and the web
route runs `read_label_pdf` in a worker thread with a time limit. The text layer is read in memory;
no OCR, nothing leaves the machine and nothing is stored. Error messages name page numbers only:
the buyer's name and address are never put into a message or a log.

Two layers keep the layout rules testable without a PDF: `_page_lines` turns a pdfplumber page into
`TextLine` runs (one text, one style, one place), and `parse_spx` / `parse_jt` read those runs.
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from shoponline.domain.order import default_address
from shoponline.importers.excel_table import FileRejected

MAX_BYTES = 40 * 1024 * 1024
MAX_PAGES = 500

PLATFORM_SHOPEE = "SHOPEE"
PLATFORM_TIKTOK = "TIKTOK"

# Words further apart than this sit in different columns of the label.
_COLUMN_GAP = 12.0
_ROW_TOLERANCE = 2.5
_SPX_ADDRESS_HEIGHT = 45.0  # the recipient block is a few lines under "Đến:"
_SPX_LINE_GAP = 14.0
_JT_NAME_MAX_SIZE = 15.0  # the sort code beside the name is set in 20 pt
_JT_ADDRESS_MIN_SIZE = 5.0  # barcode digits and tiny codes are set below this
_JT_NAME_MAX_X = 215.0  # the name sits to the left of the sort code set at this column
_JT_ADDRESS_MAX_X = 200.0  # the sort code sits to the right of this

_VOWELS = set("aeiouy")
_ORDER_SPX = re.compile(r"Mã đơn hàng:\s*(\S+)")
_ORDER_JT = re.compile(r"Order ID:\s*(\d+)")


@dataclass(frozen=True)
class TextLine:
    """One run of words of the same style on one row of a page."""

    text: str
    x0: float
    x1: float
    top: float
    size: float
    bold: bool


@dataclass(frozen=True)
class Label:
    platform: str
    order_id: str
    name: str
    address: str
    pages: tuple[int, ...] = ()
    conflicting: bool = False  # pages of one order disagree on the name or the address


@dataclass(frozen=True)
class LabelRead:
    labels: tuple[Label, ...]
    unreadable: tuple[int, ...]  # 1-based page numbers no layout matched
    page_count: int


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()


# --- layer 1: pdfplumber page -> text runs -------------------------------------------------------


def _is_bold(char: dict[str, Any]) -> bool:
    return "bold" in str(char.get("fontname", "")).lower()


def _page_lines(page: Any) -> list[TextLine]:
    """Runs of one style on one row. Built from characters, not words, because a label sets the
    name right after its caption in another font, and prints some text twice to fake bold."""
    chars = []
    seen: set[tuple[str, int, int]] = set()
    for char in page.chars:
        key = (char["text"], round(char["x0"] * 2), round(char["top"] * 2))
        if key not in seen:
            seen.add(key)
            chars.append(char)
    chars.sort(key=lambda c: (c["top"], c["x0"]))
    rows: list[list[dict[str, Any]]] = []
    for char in chars:
        if rows and abs(char["top"] - rows[-1][0]["top"]) <= _ROW_TOLERANCE:
            rows[-1].append(char)
        else:
            rows.append([char])
    # The sender and the recipient are printed side by side and can sit closer than a column gap:
    # a run never crosses the left edge of the recipient column, which starts at `Đến:`.
    column = _recipient_column(page.chars)
    lines: list[TextLine] = []
    for row in rows:
        row.sort(key=lambda c: c["x0"])
        run: list[dict[str, Any]] = []
        for char in row:
            if run and _starts_new_run(run[-1], char, column):
                lines.append(_run_to_line(run))
                run = []
            if char["text"].strip() or run:
                run.append(char)
        if run:
            lines.append(_run_to_line(run))
    return [line for line in lines if line.text]


def _recipient_column(chars: list[dict[str, Any]]) -> tuple[float, float] | None:
    for index, char in enumerate(chars):
        if char["text"] == "Đ":
            ahead = "".join(c["text"] for c in chars[index : index + 8])
            if unicodedata.normalize("NFC", ahead).startswith("Đến:"):
                return float(char["x0"]), float(char["top"])
    return None


def _starts_new_run(
    previous: dict[str, Any], char: dict[str, Any], column: tuple[float, float] | None
) -> bool:
    if (
        column is not None
        and char["top"] >= column[1] - 1
        and previous["x0"] < column[0] - 2 <= char["x0"]
    ):
        return True
    if char["x0"] - previous["x1"] > _COLUMN_GAP:
        return True
    if char["text"].isspace() or previous["text"].isspace():
        return False
    return _is_bold(previous) != _is_bold(char) or abs(previous["size"] - char["size"]) > 1.0


def _run_to_line(run: list[dict[str, Any]]) -> TextLine:
    text = ""
    previous: dict[str, Any] | None = None
    for char in run:
        if char["text"].isspace():
            text += " "
        elif char["x1"] - char["x0"] < 0.01:
            text += char["text"]  # a combining mark takes no room; it joins the letter before it
            continue
        else:
            if previous is not None and char["x0"] - previous["x1"] > 0.2 * previous["size"]:
                text += " "
            text += char["text"]
        previous = char
    shown = [c for c in run if c["text"].strip()]
    return TextLine(
        text=_clean(text),
        x0=float(min(c["x0"] for c in shown)),
        x1=float(max(c["x1"] for c in shown)),
        top=float(min(c["top"] for c in shown)),
        size=float(max(c["size"] for c in shown)),
        bold=_is_bold(shown[0]),
    )


# --- layer 2: text runs -> label -----------------------------------------------------------------


def _find(lines: list[TextLine], pattern: re.Pattern[str]) -> str:
    for line in lines:
        match = pattern.search(line.text)
        if match:
            return match.group(1)
    return ""


def _value_after(lines: list[TextLine], prefix: str, pattern: re.Pattern[str]) -> str:
    """The value printed after a caption, in the same run or in the run beside it."""
    for line in lines:
        if not line.text.startswith(prefix):
            continue
        beside = " ".join(
            other.text
            for other in lines
            if other is not line and abs(other.top - line.top) <= 3 and other.x0 >= line.x1 - 1
        )
        match = pattern.search(f"{line.text} {beside}")
        if match:
            return match.group(1)
    return ""


def _tidy_address(parts: list[str]) -> str:
    """Parts joined as `<...>, <province>, Việt Nam`, the same shape the order files give."""
    kept = []
    for part in parts:
        part = re.sub(r"\s+,", ",", _clean(part)).strip(", ")
        if part:
            kept.append(part)
    return default_address(*kept) if kept else ""


def parse_spx(lines: list[TextLine]) -> Label | None:
    """Shopee Express label: recipient under `Đến:`, then the sort code in bold."""
    texts = [line.text for line in lines]
    if not (
        any("Mã vận đơn:" in t for t in texts)
        and any("Mã đơn hàng:" in t for t in texts)
        and any(t.startswith("Đến:") for t in texts)
    ):
        return None
    order_id = _find(lines, _ORDER_SPX)
    anchor = next(line for line in lines if line.text.startswith("Đến:"))
    block: list[TextLine] = []
    last_top = anchor.top
    for line in sorted(lines, key=lambda item: item.top):
        if line.top <= anchor.top or line.top > anchor.top + _SPX_ADDRESS_HEIGHT:
            continue
        if line.x0 < anchor.x0 - 3 or line.x0 > anchor.x0 + 3:
            continue
        if line.bold or line.top - last_top > _SPX_LINE_GAP:
            break
        block.append(line)
        last_top = line.top
    if not order_id or len(block) < 2:
        return None
    name = _clean(block[0].text)
    address = _tidy_address([" ".join(line.text for line in block[1:])])
    if not name or not address:
        return None
    return Label(PLATFORM_SHOPEE, order_id, name, address)


def _join_fragments(first: str, second: str) -> str:
    """Join two text lines of one wrapped address. The wrap can fall inside a word (`Lon|g`,
    `hu|yện`) or between words (`lược|huyện`); a join that makes one syllable is a single word."""
    if not first:
        return second
    if not second:
        return first
    if not second[0].isalnum():
        return first + second
    word = first.split(" ")[-1] + second.split(" ")[0]
    plain = unicodedata.normalize("NFD", word).lower()
    letters = [c for c in plain if c.isalpha() and not unicodedata.combining(c)]
    clusters = 0
    inside = False
    for c in letters:
        vowel = c in _VOWELS
        if vowel and not inside:
            clusters += 1
        inside = vowel
    return first + second if clusters == 1 else first + " " + second


def parse_jt(lines: list[TextLine]) -> Label | None:
    """J&T label printed by TikTok: bold name beside `Người nhận`, bold address under the phone."""
    order_id = _value_after(lines, "Order ID:", _ORDER_JT)
    label = next((line for line in lines if line.text.startswith("Người nhận")), None)
    phone = next((line for line in lines if line.text.startswith("(+84)")), None)
    if not order_id or label is None or phone is None:
        return None
    name_lines = [
        line
        for line in sorted(lines, key=lambda item: item.top)
        if line.bold
        and _JT_ADDRESS_MIN_SIZE <= line.size < _JT_NAME_MAX_SIZE
        and label.x1 - 2 <= line.x0 < _JT_NAME_MAX_X
        and label.top - 3 <= line.top < phone.top - 1
    ]
    stop = next(
        (
            line.top
            for line in lines
            if line.text.startswith("Trọng lượng") and line.top > phone.top
        ),
        phone.top + 120,
    )
    address_lines = [
        line
        for line in sorted(lines, key=lambda item: item.top)
        if line.bold
        and line.size >= _JT_ADDRESS_MIN_SIZE
        and line.x0 < _JT_ADDRESS_MAX_X
        and phone.top + 1 < line.top < stop
    ]
    if not name_lines or len(address_lines) < 2:
        return None
    name = _clean(" ".join(line.text for line in name_lines))
    # The last two lines are the ward and the province; everything before is the street, which the
    # label wraps at a fixed width, sometimes inside a word.
    street = ""
    for line in address_lines[:-2]:
        street = _join_fragments(street, line.text)
    address = _tidy_address([street, address_lines[-2].text, address_lines[-1].text])
    if not name or not address:
        return None
    return Label(PLATFORM_TIKTOK, order_id, name, address)


def parse_page(lines: list[TextLine]) -> Label | None:
    return parse_spx(lines) or parse_jt(lines)


def merge_labels(found: list[tuple[int, Label]]) -> tuple[Label, ...]:
    """One label per (platform, order); pages of one order that disagree are marked conflicting."""
    merged: dict[tuple[str, str], Label] = {}
    for page_number, label in found:
        key = (label.platform, label.order_id)
        previous = merged.get(key)
        if previous is None:
            merged[key] = Label(
                label.platform,
                label.order_id,
                label.name,
                label.address,
                (page_number,),
                label.conflicting,
            )
            continue
        differs = (
            previous.name.casefold() != label.name.casefold()
            or previous.address.casefold() != label.address.casefold()
        )
        merged[key] = Label(
            previous.platform,
            previous.order_id,
            previous.name,
            previous.address,
            (*previous.pages, page_number),
            previous.conflicting or label.conflicting or differs,
        )
    return tuple(merged.values())


# --- the file ----------------------------------------


def read_label_pdf(data: bytes) -> LabelRead:
    import pdfplumber

    if not data.startswith(b"%PDF-"):
        raise FileRejected("Không đọc được phiếu vận đơn: file không phải PDF")
    if len(data) > MAX_BYTES:
        raise FileRejected(f"Không đọc được phiếu vận đơn: file quá {MAX_BYTES // 1024 // 1024} MB")
    found: list[tuple[int, Label]] = []
    unreadable: list[int] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            count = len(pdf.pages)
            if count > MAX_PAGES:
                raise FileRejected(f"Không đọc được phiếu vận đơn: quá {MAX_PAGES} trang")
            for number, page in enumerate(pdf.pages, start=1):
                label = parse_page(_page_lines(page))
                if label is None:
                    unreadable.append(number)
                else:
                    found.append((number, label))
                page.flush_cache()
    except FileRejected:
        raise
    except Exception as exc:  # pdfminer raises many types for damaged input
        raise FileRejected("Không đọc được phiếu vận đơn: PDF hỏng hoặc có mã hóa") from exc
    return LabelRead(merge_labels(found), tuple(unreadable), count)
