from datetime import date, datetime
from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import event

from shoponline.accounting import settlement_invoice_file as invoice_file
from shoponline.importers.excel_table import FileRejected
from tests import sales_history_setup as setup

TODAY = date(2026, 11, 25)
WHEN = datetime(2026, 11, 12, 9)
HEADER = ("Số hóa đơn", "Ngày nhận tiền", "Số tiền")


def _xlsx(rows, header=HEADER) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    out = BytesIO()
    book.save(out)
    return out.getvalue()


def _lazada(db, order_id="LZ-1", invoice="00001234", **kwargs):
    return setup.order(db, order_id, WHEN, platform="LAZADA", invoice=invoice, **kwargs)


def _resolve(db, rows):
    return invoice_file.resolve(db, invoice_file.read_file(_xlsx(rows)), TODAY)


def test_a_valid_line_resolves_to_its_order(db):
    _lazada(db)

    (result,) = _resolve(db, [("00001234", "20/11/2026", 90000)])

    assert (result.order_id, result.error) == ("LZ-1", "")
    assert (result.line.amount, result.line.settled_on) == (90000, date(2026, 11, 20))
    assert result.line.line_no == 2


@pytest.mark.parametrize("cell", [1234, 1234.0, "001234", " 1234 ", "00001234"])
def test_an_invoice_that_lost_its_leading_zeros_still_matches(db, cell):
    _lazada(db)

    (result,) = _resolve(db, [(cell, "20/11/2026", 1)])

    assert result.error == ""
    assert result.order_id == "LZ-1"


@pytest.mark.parametrize(
    "cell", [datetime(2026, 11, 20), datetime(2026, 11, 20, 8, 30), "20/11/2026", "2026-11-20"]
)
def test_the_date_is_read_from_an_excel_date_or_text(db, cell):
    _lazada(db)

    (result,) = _resolve(db, [("1234", cell, 1)])

    assert result.error == ""
    assert result.line.settled_on == date(2026, 11, 20)


@pytest.mark.parametrize(
    ("cell", "message"),
    [
        ("", "không đúng dạng"),
        ("hôm qua", "không đúng dạng"),
        ("31/02/2026", "không đúng dạng"),
        ("26/11/2026", "tương lai"),
        ("11/11/2026", "trước ngày đặt đơn"),
    ],
)
def test_a_bad_date_is_refused(db, cell, message):
    _lazada(db)

    (result,) = _resolve(db, [("1234", cell, 1)])

    assert message in result.error


@pytest.mark.parametrize(
    ("cell", "expected"),
    [(90000, 90000), (90000.0, 90000), ("1.234.567", 1234567), ("1,234,567", 1234567), (0, 0)],
)
def test_amounts_that_are_whole_dong_are_accepted(db, cell, expected):
    _lazada(db)

    (result,) = _resolve(db, [("1234", "20/11/2026", cell)])

    assert result.error == ""
    assert result.line.amount == expected


@pytest.mark.parametrize("cell", [None, -5, 1234.5, "abc"])
def test_a_bad_amount_is_refused(db, cell):
    _lazada(db)

    (result,) = _resolve(db, [("1234", "20/11/2026", cell)])

    assert result.error
    assert result.line.amount is None


def test_a_blank_invoice_is_refused(db):
    blank, zeros = _resolve(db, [(None, "20/11/2026", 1), ("000", "20/11/2026", 1)])

    assert blank.error == zeros.error == "Số hóa đơn trống"


def test_an_invoice_missing_from_sap_is_refused(db):
    (result,) = _resolve(db, [("99999999", "20/11/2026", 1)])

    assert "chưa có trong dữ liệu SAP" in result.error and "99999999" in result.error


def test_an_invoice_of_a_shopee_order_or_without_an_order_is_not_a_lazada_order(db):
    setup.order(db, "SP-1", WHEN, platform="SHOPEE", invoice="00005555")
    setup.tax_invoice(db, "8000000001", "00006666")  # a DO no order owns

    shopee, orphan = _resolve(db, [("5555", "20/11/2026", 1), ("6666", "20/11/2026", 1)])

    assert "không thuộc đơn Lazada nào" in shopee.error
    assert "không thuộc đơn Lazada nào" in orphan.error


def test_an_invoice_for_two_lazada_orders_is_refused_not_split(db):
    first = _lazada(db, "LZ-1")
    second = _lazada(db, "LZ-2", invoice=None)
    second.do_number = first.do_number
    db.flush()

    (result,) = _resolve(db, [("1234", "20/11/2026", 1)])

    assert "ứng với 2 đơn (LZ-1, LZ-2)" in result.error


def test_an_invoice_repeated_in_the_file_fails_on_every_line(db):
    _lazada(db)

    first, second = _resolve(db, [("1234", "20/11/2026", 1), ("001234", "21/11/2026", 2)])

    assert "trùng ở các dòng 2, 3" in first.error
    assert "trùng ở các dòng 2, 3" in second.error


def test_a_line_with_a_read_error_keeps_it(db):
    _lazada(db)

    good, bad = _resolve(db, [("1234", "20/11/2026", 1), ("1234x", "20/11/2026", "abc")])

    assert good.error == ""
    assert "không phải số" in bad.error


def test_a_file_without_a_column_or_not_xlsx_is_rejected():
    with pytest.raises(FileRejected, match="Số tiền"):
        invoice_file.read_file(_xlsx([], header=("Số hóa đơn", "Ngày nhận tiền")))
    with pytest.raises(FileRejected):
        invoice_file.read_file(b"not an excel file")


def test_carry_round_trips_the_readable_lines():
    lines = [
        invoice_file.FileLine(2, "1234", 90000, date(2026, 11, 20)),
        invoice_file.FileLine(3, "55", None, None, "Số tiền trống"),
        invoice_file.FileLine(4, "77", 0, date(2026, 11, 21)),
    ]

    carried = invoice_file.from_carry(invoice_file.to_carry(lines))

    assert carried == [lines[0], lines[2]]


@pytest.mark.parametrize(
    "text",
    ["2\t1234\t5", "x\t1234\t5\t2026-11-20", "2\t1234\t-5\t2026-11-20", "2\t\t5\t2026-11-20"],
)
def test_a_carry_in_the_wrong_shape_is_refused(text):
    with pytest.raises(ValueError):
        invoice_file.from_carry(text)


def test_resolve_looks_invoices_up_in_one_query(db):
    for n in range(1, 4):
        _lazada(db, f"LZ-{n}", invoice=f"0000123{n}")
    lines = invoice_file.read_file(_xlsx([(f"123{n}", "20/11/2026", 1) for n in range(1, 4)]))
    seen = []

    def count(conn, cursor, statement, *args):
        if "sap_tax_invoice" in statement:
            seen.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", count)
    try:
        invoice_file.resolve(db, lines, TODAY)
    finally:
        event.remove(engine, "before_cursor_execute", count)

    assert len(seen) == 1
