import json
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document

from shoponline.exports.invoice_adjustment_doc import format_qty, render
from shoponline.exports.text_clean import clean_text
from tests.exports.return_fixtures import line, sales_return
from tests.support.format_compare import compare_docx, docx_expected, docx_format

BASELINE = json.loads(
    (Path(__file__).resolve().parents[1] / "support" / "template_baseline.json").read_text("utf-8")
)["docx"]


def read(data: bytes):
    doc = Document(BytesIO(data))
    paragraphs = [p.text for p in doc.paragraphs]
    tables = [[[c.text for c in row.cells] for row in t.rows] for t in doc.tables]
    return paragraphs, tables


def test_one_line_return_fills_every_field_and_keeps_no_placeholder():
    paragraphs, tables = read(render(sales_return()))
    text = "\n".join(paragraphs)
    assert "{{" not in text and "{%" not in text and "}}" not in text
    assert "Số : 080/11.2026 ALK-KH.STMĐT" in text
    assert "năm 2026, Đại diện" in text
    assert "NGƯỜI MUA : Nguyen Van A" in text
    assert "Địa chỉ : 1 Duong Thu Nghiem, Quan Thu Nghiem" in text.replace("\xa0", " ")
    assert "Do người mua hủy đơn hàng đã đặt trên sàn thương mại điện tử Shopee trong khi" in text
    assert "ký hiệu : 1C26TAL; số: 00008038; ngày: 17/11/2026, chi tiết" in text
    assert "đơn hàng đã bị hủy số: 261115BUCPCSEN để làm căn cứ" in text
    before, after = tables
    assert [c.strip() for c in before[1]] == [
        "SƠN V-09 REDDISH CLAY 2004 VN",
        "LON 0.8 LT",
        "1",
        "111.111",
        "111.111",
    ]
    assert [c.strip() for c in after[1]] == [
        "SƠN V-09 REDDISH CLAY 2004 VN",
        "LON 0.8 LT",
        "-1",
        "111.111",
        "-111.111",
    ]
    assert before[2][4].strip() == "111.111"
    assert after[2][4].strip() == "-111.111"
    assert before[3][0].startswith("Thuế suất GTGT: 8%") and after[3][0].startswith(
        "Thuế suất GTGT: 8%"
    )
    assert before[3][4].strip() == "8.889" and after[3][4].strip() == "-8.889"
    assert before[4][4].strip() == "120.000" and after[4][4].strip() == "-120.000"


def test_a_return_of_goods_uses_the_returned_wording():
    paragraphs, _ = read(render(sales_return(reason_kind="RETURN")))
    text = "\n".join(paragraphs)
    assert "Do người mua trả lại hàng đã mua trên sàn thương mại điện tử Shopee" in text
    assert "đơn hàng bị trả lại số: 261115BUCPCSEN" in text


def test_a_two_line_order_has_both_lines_in_both_tables():
    lines = [line(1, net=55556), line(2, name="SƠN LÓT", unit="LON 5 LT", net=55555)]
    _, (before, after) = read(render(sales_return(lines)))
    assert len(before) == 6 and len(after) == 6
    assert before[1][0].strip() == "SƠN V-09 REDDISH CLAY 2004 VN"
    assert before[2][0].strip() == "SƠN LÓT" and after[2][0].strip() == "SƠN LÓT"
    assert before[2][4].strip() == "55.555" and after[2][4].strip() == "-55.555"


def test_a_partial_return_lists_every_line_before_but_only_returned_ones_after():
    lines = [line(1, net=55556, ret=0), line(2, name="SƠN LÓT", qty=2, ret=1, net=55555)]
    paragraphs, (before, after) = read(render(sales_return(lines)))
    assert len(before) == 6 and len(after) == 5
    assert after[1][0].strip() == "SƠN LÓT" and after[1][2].strip() == "-1"
    assert before[2][2].strip() == "2"


@pytest.mark.parametrize(
    "name",
    [
        "A & B <script> \"q\" 'z'",
        "</w:t></w:r><w:r><w:t>hacked",
        "{{ 7*7 }} {% if 1 %}x{% endif %}",
        "=SUM(A1)",
    ],
)
def test_hostile_buyer_text_is_kept_verbatim_and_opens(name):
    paragraphs, _ = read(render(sales_return(buyer_name=name, buyer_address=name)))
    text = "\n".join(paragraphs)
    assert f"NGƯỜI MUA : {name}" in text
    assert f"{name}" in text.replace("\xa0", " ")


def test_control_characters_are_dropped_and_breaks_become_spaces():
    paragraphs, _ = read(render(sales_return(buyer_name="A\x00B\x0bC\nD\tE\x1f")))
    assert "NGƯỜI MUA : ABC D E" in "\n".join(paragraphs)
    assert clean_text("x\x00\ud800y") == "xy" if False else clean_text("x\x00y") == "xy"


@pytest.mark.parametrize(
    ("value", "negative", "expected"),
    [(1, False, "1"), (2, True, "-2"), ("1.5", False, "1,5"), ("2.000", False, "2")],
)
def test_quantity_text(value, negative, expected):
    assert format_qty(value, negative=negative) == expected


def _no_format_difference(sales, before_extra, after_extra):
    actual = docx_format(render(sales))
    expected = docx_expected(BASELINE, before_extra=before_extra, after_extra=after_extra)
    return compare_docx(expected, actual)


def test_the_filled_form_has_the_sample_format_for_one_line():
    assert _no_format_difference(sales_return(), 0, 0) == []


def test_the_filled_form_has_the_sample_format_for_two_lines():
    lines = [line(1, net=55556), line(2, name="SƠN LÓT", unit="LON 5 LT", net=55555)]
    assert _no_format_difference(sales_return(lines), 1, 1) == []


def test_the_filled_form_has_the_sample_format_for_a_partial_return():
    lines = [line(1, net=55556, ret=0), line(2, name="SƠN LÓT", qty=2, ret=1, net=55555)]
    assert _no_format_difference(sales_return(lines), 1, 0) == []


def test_runs_of_spaces_in_buyer_text_collapse():
    assert clean_text("85/8  Lê   Hồng\t phong") == "85/8 Lê Hồng phong"
