"""Shipping label reader. The layout tests use made-up names and addresses placed where the real
labels put them; the real PDFs hold buyers' data and are only read when a path is given."""

import os
from pathlib import Path

import pytest

from shoponline.domain.report_names import province_of
from shoponline.importers.excel_table import FileRejected
from shoponline.importers.shipping_label_pdf import (
    MAX_BYTES,
    Label,
    TextLine,
    _join_fragments,
    _page_lines,
    merge_labels,
    parse_jt,
    parse_page,
    parse_spx,
    read_label_pdf,
)


def line(text, x0, top, *, bold=False, size=7.5, width=None):
    return TextLine(text, x0, x0 + (width or len(text) * 3.5), top, size, bold)


def spx_page(
    order="26110000AAAAAA", name="Nguyễn Thử", address=("12 Đường Thử, Phường Một,", "Tỉnh Thử")
):
    lines = [
        line("Mã vận đơn: SPXVN0000000000X", 142, 42),
        line(f"Mã đơn hàng: {order}", 141, 55),
        line("Từ:", 11, 70, bold=True),
        line("Đến:(Chỉ giao giờ hành chính)", 151, 70, bold=True),
        line("SHOP_GUI Người Gửi", 11, 80),
        line(name, 151, 80),
        line("Số 1 đường Gửi, khu Gửi", 11, 88),
    ]
    for index, text in enumerate(address):
        lines.append(line(text, 151, 88 + 7.5 * index))
    lines.append(line("MBD-28-12-TN02-N", 34, 147, bold=True, size=17.2))
    return lines


def jt_page(
    order="587300000000000001",
    name="user0000000000001",
    street=("Ấp Một, An Hai ,",),
    ward="Xã Ba,",
    province="An Giang",
):
    lines = [
        line("Người gửi", 17, 87, size=5.8),
        line("SHOP GUI", 45, 86, bold=True, size=9.0),
        line("Người nhận", 18, 104, size=5.8, width=31),
        line(name, 52, 103, bold=True, size=12.9),
        line("830", 220, 100, bold=True, size=20.0),
        line("B270F01", 194, 123, bold=True, size=20.0),
        line("(+84)89*****19", 116, 129, bold=True, size=10.0),
        line("012", 220, 144, bold=True, size=20.0),
        line("0", 8, 117, bold=True, size=3.8, width=7),
        line("8", 283, 116, bold=True, size=3.8, width=7),
    ]
    for index, text in enumerate(street):
        lines.append(line(text, 20, 147 + 13 * index, bold=True, size=11.3))
    lines.append(line(ward, 20, 198, bold=True, size=9.4))
    lines.append(line(province, 20, 218, bold=True, size=8.6))
    lines += [
        line("ĐƯỢC ĐỒNG KIÊM", 115, 224, size=8.1),
        line("Trọng lượng:", 149, 236, size=5.8),
        line("Order ID:", 149, 246, size=5.8, width=24),
        line(order, 206, 246, size=7.1),
    ]
    return lines


def test_spx_label_gives_order_name_and_address_with_the_sort_code_left_out():
    label = parse_spx(spx_page())

    assert label == Label(
        "SHOPEE",
        "26110000AAAAAA",
        "Nguyễn Thử",
        "12 Đường Thử, Phường Một, Tỉnh Thử, Việt Nam",
    )
    assert province_of(label.address) is None  # "Tỉnh Thử" is not one of the 34 provinces


def test_spx_address_wraps_over_any_number_of_lines():
    lines = spx_page(address=("1 Đường Thử,", "Phường Hai,", "Tỉnh Quảng Ninh"))

    assert parse_spx(lines).address == "1 Đường Thử, Phường Hai, Tỉnh Quảng Ninh, Việt Nam"
    assert province_of(parse_spx(lines).address) == "Quảng Ninh"


def test_spx_ignores_the_sender_column_and_the_page_without_the_markers():
    assert parse_spx(spx_page()[:2] + spx_page()[4:]) is None  # no "Đến:"
    assert parse_spx([line("Hóa đơn", 10, 10)]) is None


def test_spx_label_without_a_recipient_address_is_unreadable():
    assert parse_spx(spx_page(address=())) is None


def test_jt_label_keeps_a_tiktok_username_and_joins_street_ward_province():
    label = parse_jt(jt_page())

    assert label == Label(
        "TIKTOK",
        "587300000000000001",
        "user0000000000001",
        "Ấp Một, An Hai, Xã Ba, An Giang, Việt Nam",
    )
    assert province_of(label.address) == "An Giang"


def test_jt_drops_the_inspection_note_the_barcode_digits_and_the_sort_codes():
    label = parse_jt(jt_page())

    assert "ĐỒNG KIÊM" not in label.address
    assert "830" not in label.name and "B270F01" not in label.name


@pytest.mark.parametrize(
    ("first", "second", "joined"),
    [
        ("tỉnh Vĩnh Lon", "g", "tỉnh Vĩnh Long"),
        ("xã Tân Lộc huy", "ện Bình", "xã Tân Lộc huyện Bình"),
        ("xã Tân lược", "huyện Bình Tân", "xã Tân lược huyện Bình Tân"),
        ("340 đường 208 (Ngã Tư ác qui)", ",", "340 đường 208 (Ngã Tư ác qui),"),
        ("", "Ấp Một", "Ấp Một"),
    ],
)
def test_a_wrapped_address_joins_inside_a_word_but_not_between_words(first, second, joined):
    assert _join_fragments(first, second) == joined


def test_jt_street_wrapped_inside_a_word_is_repaired():
    label = parse_jt(
        jt_page(street=("tổ 12 ấp Tân Lộc xã Tân lược", "huyện Bình Tân tỉnh Vĩnh Lon", "g ,"))
    )

    assert label.address.startswith("tổ 12 ấp Tân Lộc xã Tân lược huyện Bình Tân tỉnh Vĩnh Long, ")


def test_a_page_of_no_known_layout_is_not_read():
    assert parse_page([line("Hóa đơn bán hàng", 10, 10), line("Tổng cộng", 10, 30)]) is None
    assert parse_page([]) is None


def test_jt_label_missing_the_order_id_or_name_is_unreadable():
    no_order = [ln for ln in jt_page() if not ln.text.startswith(("Order", "587"))]
    no_name = [ln for ln in jt_page() if ln.size != 12.9]

    assert parse_jt(no_order) is None
    assert parse_jt(no_name) is None


def test_pages_of_one_order_become_one_label_and_disagreement_is_flagged():
    a = Label("SHOPEE", "A1", "Nguyễn Thử", "1 Đường Thử, Việt Nam")
    same = Label("SHOPEE", "A1", "nguyễn thử", "1 đường thử, Việt Nam")
    other = Label("SHOPEE", "A1", "Người Khác", "1 Đường Thử, Việt Nam")
    elsewhere = Label("TIKTOK", "A1", "Nguyễn Thử", "1 Đường Thử, Việt Nam")

    merged = merge_labels([(1, a), (2, same)])
    assert [(m.pages, m.conflicting) for m in merged] == [((1, 2), False)]

    merged = merge_labels([(1, a), (2, other), (3, elsewhere)])
    assert [(m.platform, m.pages, m.conflicting) for m in merged] == [
        ("SHOPEE", (1, 2), True),
        ("TIKTOK", (3,), False),
    ]


class FakePage:
    def __init__(self, chars):
        self.chars = chars


def char(text, x0, top, *, size=7.5, bold=False, width=4.0):
    return {
        "text": text,
        "x0": x0,
        "x1": x0 + width,
        "top": top,
        "size": size,
        "fontname": "Sans-Bold" if bold else "Sans",
    }


def word_chars(text, x0, top, **kwargs):
    out = []
    for index, letter in enumerate(text):
        out.append(char(letter, x0 + index * 4.0, top, **kwargs))
    return out


def test_page_lines_split_the_sender_from_the_recipient_at_the_recipient_column():
    chars = (
        word_chars("Đến:", 150, 70, bold=True)
        + word_chars("Gui", 100, 80)  # sender's last word ends right before the recipient column
        + word_chars("Nhan", 150, 80)
    )

    texts = [(ln.text, ln.x0) for ln in _page_lines(FakePage(chars))]

    assert ("Gui", 100.0) in texts and ("Nhan", 150.0) in texts


def test_page_lines_separate_a_caption_from_the_name_in_another_style():
    chars = word_chars("Người", 18, 104, size=5.8) + word_chars("An", 40, 103, size=12.9, bold=True)

    lines = _page_lines(FakePage(chars))

    assert [(ln.text, ln.bold) for ln in lines] == [("Người", False), ("An", True)]


def test_page_lines_keep_a_combining_mark_on_its_letter_and_drop_a_repeated_glyph():
    mark = char("̣", 6.0, 10, width=0.0)
    chars = [char("a", 1, 10), char("â", 5, 10), mark, char("p", 9.2, 10), char("p", 9.2, 10)]

    assert [ln.text for ln in _page_lines(FakePage(chars))] == ["aập"]


def test_a_file_that_is_not_a_pdf_is_refused():
    with pytest.raises(FileRejected, match="không phải PDF"):
        read_label_pdf(b"PK\x03\x04 not a pdf")


def test_a_damaged_pdf_is_refused():
    with pytest.raises(FileRejected):
        read_label_pdf(b"%PDF-1.4\n garbage without structure")


def test_a_pdf_over_the_size_limit_is_refused():
    with pytest.raises(FileRejected, match="MB"):
        read_label_pdf(b"%PDF-" + b"0" * MAX_BYTES)


def test_a_pdf_over_the_page_limit_is_refused(monkeypatch):
    import pdfplumber

    class Many:
        pages = [object()] * 501

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(pdfplumber, "open", lambda *_a, **_k: Many())

    with pytest.raises(FileRejected, match="500 trang"):
        read_label_pdf(b"%PDF-1.4")


SPX_SAMPLE = os.environ.get("SHOPONLINE_SAMPLE_SPX_LABEL_PDF")
JT_SAMPLE = os.environ.get("SHOPONLINE_SAMPLE_JT_LABEL_PDF")


@pytest.mark.skipif(not SPX_SAMPLE, reason="no real Shopee label PDF given")
def test_reads_a_real_shopee_label_pdf():
    result = read_label_pdf(Path(SPX_SAMPLE).read_bytes())

    assert len(result.labels) == 16 and result.unreadable == ()
    assert all(label.platform == "SHOPEE" and label.name for label in result.labels)
    assert all(province_of(label.address) for label in result.labels)


@pytest.mark.skipif(not JT_SAMPLE, reason="no real TikTok label PDF given")
def test_reads_a_real_tiktok_label_pdf():
    result = read_label_pdf(Path(JT_SAMPLE).read_bytes())

    assert len(result.labels) == 7 and result.unreadable == ()
    assert all(label.platform == "TIKTOK" and label.name for label in result.labels)
    assert all(province_of(label.address) for label in result.labels)
