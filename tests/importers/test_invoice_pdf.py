import io
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from shoponline.importers.excel_table import FileRejected
from shoponline.importers.invoice_pdf import (
    MAX_PAGES,
    parse_amount,
    parse_invoice,
    read_invoice_pdf,
)

HEAD = (
    "HÓA ĐƠN GIÁ TRỊ GIA TĂNG Mẫu số - Ký hiệu: 1C26TAL\nSố: 00008038\n"
    "Ngày 17 tháng 11 năm 2026 Số DO: 1910061281\nSố PO: 261115BUCPCSEN"
)
SELLER = "CÔNG TY TNHH\nSố tài khoản: 6500807999 tại Ngân Hàng"
BUYER = "Họ tên người mua hàng: Nguyen Van A\nĐịa chỉ: 1 Duong Thu Nghiem"
HEADER_ROW = ["STT", "Tên hàng hóa, dịch vụ", "Đơn vị tính", "Số lượng", "Đơn giá", "Thành tiền"]
INDEX_ROW = ["1", "2", "3", "4", "5", "6 = 4 x 5"]
BLANK = [""] * 6


def tables(lines, *, head=HEAD, net="111.111", vat="8", tax="8.889", total="120.000"):
    foot = [
        [f"Cộng tiền hàng: {net}", None, None, None, None, None],
        [f"Thuế suất GTGT: {vat}% Tiền thuế GTGT: {tax}", None, None, None, None, None],
        [f"Tổng cộng tiền thanh toán: {total}", None, None, None, None, None],
    ]
    rows = [[head, None, None, None, None, None], [SELLER] + [None] * 5, [BUYER] + [None] * 5]
    rows += [HEADER_ROW, INDEX_ROW, *lines, BLANK, BLANK, *foot]
    return [rows]


ONE = ["1", "SƠN V-09 REDDISH CLAY 2004 VN", "LON 0.8 LT", "1", "111.111", "111.111"]


def test_reads_the_header_and_one_line():
    invoice = parse_invoice(tables([ONE]))
    assert (invoice.symbol, invoice.number, invoice.invoice_date) == (
        "1C26TAL",
        "00008038",
        date(2026, 11, 17),
    )
    assert (invoice.delivery, invoice.po) == ("1910061281", "261115BUCPCSEN")
    assert (invoice.net, invoice.vat_rate, invoice.tax, invoice.total) == (111111, 8, 8889, 120000)
    (line,) = invoice.lines
    assert (line.name, line.unit, line.quantity, line.amount) == (
        "SƠN V-09 REDDISH CLAY 2004 VN",
        "LON 0.8 LT",
        Decimal(1),
        111111,
    )


def test_reads_two_lines_with_a_fractional_unit_price_and_a_wrapped_name():
    second = ["2", "SƠN LÓT\nNỘI THẤT", "LON 5 LT", "3", "55.555,5", "166.667"]
    invoice = parse_invoice(tables([ONE, second]))
    assert [line.number for line in invoice.lines] == [1, 2]
    assert invoice.lines[1].name == "SƠN LÓT NỘI THẤT"
    assert invoice.lines[1].quantity == Decimal(3) and invoice.lines[1].amount == 166667


@pytest.mark.parametrize(
    ("text", "value"),
    [("111.111", 111111), ("55.555,5", Decimal("55555.5")), ("0", 0), ("1.234.567", 1234567)],
)
def test_amount_formats(text, value):
    assert parse_amount(text) == value


@pytest.mark.parametrize("text", ["1,111.5", "12.34", "abc", "", "1..000", "-5"])
def test_malformed_amounts_are_refused(text):
    with pytest.raises(ValueError, match="sai dạng"):
        parse_amount(text)


def test_a_missing_delivery_number_is_named_in_the_rejection():
    head = HEAD.replace("Số DO: 1910061281", "")
    with pytest.raises(FileRejected) as err:
        parse_invoice(tables([ONE], head=head))
    assert any("số DO" in d for d in err.value.details)


def test_a_badly_formatted_line_amount_rejects_the_file():
    bad = ["1", "SƠN", "LON", "1", "111.111", "11x.111"]
    with pytest.raises(FileRejected, match="không đọc được") as err:
        parse_invoice(tables([bad]))
    assert any("Dòng hàng 1" in d for d in err.value.details)


@pytest.mark.parametrize("name", ["SƠN\x07", "", "S" * 201])
def test_a_control_character_an_empty_or_a_long_name_is_refused(name):
    with pytest.raises(FileRejected):
        parse_invoice(tables([["1", name, "LON", "1", "1", "1"]]))


def test_rejection_text_never_carries_the_buyer():
    with pytest.raises(FileRejected) as err:
        parse_invoice(tables([["1", "SƠN", "LON", "x", "1", "1"]]))
    text = str(err.value)
    assert "Nguyen Van A" not in text and "Duong Thu Nghiem" not in text


def test_no_item_table_is_refused():
    with pytest.raises(FileRejected):
        parse_invoice([[[HEAD, None, None, None, None, None]]])


def _blank_pdf(pages: int) -> bytes:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument.new()
    for _ in range(pages):
        pdf.new_page(200, 200)
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def test_a_file_that_is_not_a_pdf_is_refused():
    with pytest.raises(FileRejected, match="không phải PDF"):
        read_invoice_pdf(b"PK\x03\x04 not a pdf")


def test_a_pdf_over_the_page_limit_is_refused():
    with pytest.raises(FileRejected, match="trang"):
        read_invoice_pdf(_blank_pdf(MAX_PAGES + 1))


def test_a_pdf_without_text_is_refused_as_a_scan():
    with pytest.raises(FileRejected, match="không có chữ"):
        read_invoice_pdf(_blank_pdf(1))


def test_a_damaged_pdf_is_refused():
    with pytest.raises(FileRejected):
        read_invoice_pdf(b"%PDF-1.4\n garbage without structure")


def test_a_pdf_over_the_size_limit_is_refused():
    with pytest.raises(FileRejected, match="MB"):
        read_invoice_pdf(b"%PDF-" + b"0" * (5 * 1024 * 1024 + 1))


@pytest.mark.skipif(
    not os.environ.get("SHOPONLINE_SAMPLE_INVOICE_PDF"), reason="no real invoice PDF given"
)
def test_reads_a_real_invoice_pdf():
    invoice = read_invoice_pdf(Path(os.environ["SHOPONLINE_SAMPLE_INVOICE_PDF"]))
    assert invoice.symbol.startswith("1C") and invoice.number.isdigit() and invoice.lines
    assert sum(line.amount for line in invoice.lines) == invoice.net
    assert invoice.net + invoice.tax == invoice.total
