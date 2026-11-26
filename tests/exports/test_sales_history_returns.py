"""Return rows in the Shop Online history file: negative rows, reversals, column I constants."""

from datetime import date, datetime
from io import BytesIO

from openpyxl import load_workbook

from shoponline.exports.sales_history_workbook import (
    ISSUE,
    SETTLEMENT,
    VOID,
    build_history_workbook,
    collect_all_rows,
    collect_rows,
)
from tests import sales_history_setup as setup

UNTIL = date(2026, 11, 16)
TWO_LINES = (("100001787", 1, 120000, 20000), ("100002222", 2, 30000, 0))


def _names(db):
    setup.report_name(db)
    setup.report_name(db, "100002222")


def _sheet(rows):
    buffer = BytesIO()
    build_history_workbook(rows).save(buffer)
    return load_workbook(BytesIO(buffer.getvalue())).active


def test_a_return_issued_before_pasting_sits_in_the_same_file_and_nets_to_zero(db):
    _names(db)
    order = setup.order(db, "A", datetime(2026, 11, 11, 9), lines=TWO_LINES)
    sales_return = setup.returned(db, order, 80)

    result = collect_rows(db, UNTIL)
    assert result.order_ids == [order.id]
    assert result.return_ids == [(sales_return.id, ISSUE)]
    assert sum(r.customer_paid for r in result.all_rows) == 0
    assert sum(r.quantity for r in result.all_rows) == 0
    first, second = result.return_rows
    assert (first.quantity, first.customer_paid, first.transaction) == (-1, -100000, -1)
    assert (second.quantity, second.customer_paid, second.transaction) == (-2, -60000, 0)
    assert first.ordered_at == order.ordered_at and first.tax_invoice_doc == "HDA"
    assert first.settlement is None and first.status == ""

    ws = _sheet(result.all_rows)
    # Sale rows keep the formula; return rows hold numbers, so SUM(I) is 1 - 1 = 0.
    assert ws["I2"].value.startswith("=IF(")
    assert [ws[f"I{r}"].value for r in (4, 5)] == [-1, 0]
    assert ws["J4"].value == -100000 and ws["N5"].value == -2


def test_a_partial_return_after_pasting_comes_alone_with_zero_transactions(db):
    _names(db)
    order = setup.order(db, "B", datetime(2026, 11, 11, 9), lines=TWO_LINES)
    setup.pasted_order(db, order, setup.history_file(db))
    sales_return = setup.returned(db, order, 81, taken={2: 1}, reason="RETURN")

    result = collect_rows(db, UNTIL)
    assert result.rows == [] and result.return_ids == [(sales_return.id, ISSUE)]
    (row,) = result.return_rows
    assert (row.quantity, row.customer_paid, row.transaction) == (-1, -30000, 0)


def test_cancelling_a_return_after_its_rows_were_pasted_adds_the_reversal(db):
    _names(db)
    order = setup.order(db, "C", datetime(2026, 11, 11, 9))
    pasted = setup.history_file(db)
    setup.pasted_order(db, order, pasted)
    sales_return = setup.returned(db, order, 82, status="VOID")
    setup.pasted_return(db, sales_return, ISSUE, pasted)

    result = collect_rows(db, UNTIL)
    assert result.return_ids == [(sales_return.id, VOID)]
    (row,) = result.return_rows
    assert (row.quantity, row.customer_paid, row.transaction) == (1, 120000, 1)

    setup.pasted_return(db, sales_return, VOID, pasted)
    assert collect_rows(db, UNTIL).return_rows == []


def test_a_return_cancelled_before_its_rows_were_pasted_adds_nothing(db):
    _names(db)
    order = setup.order(db, "D", datetime(2026, 11, 11, 9))
    setup.pasted_order(db, order, setup.history_file(db))
    setup.returned(db, order, 83, status="VOID")
    result = collect_rows(db, UNTIL)
    assert result.return_rows == [] and result.return_ids == []


def test_no_negative_rows_for_an_order_that_is_not_in_the_file(db):
    _names(db)
    # A partial return of a Shopee order still waiting for its money: the order is blocked.
    order = setup.order(db, "E", datetime(2026, 11, 11, 9), lines=TWO_LINES, settlement=None)
    setup.returned(db, order, 84, taken={2: 1})
    result = collect_rows(db, UNTIL)
    assert result.rows == [] and result.return_rows == []
    assert [r.kind for b in result.blocked for r in b.reasons] == [SETTLEMENT]


def test_a_shopee_order_returned_whole_does_not_wait_for_its_money(db):
    _names(db)
    order = setup.order(db, "F", datetime(2026, 11, 11, 9), settlement=None)
    setup.returned(db, order, 85)
    result = collect_rows(db, UNTIL)
    assert result.blocked == [] and result.order_ids == [order.id]
    assert sum(r.customer_paid for r in result.all_rows) == 0


def test_a_customer_name_starting_with_equals_stays_text_on_return_rows(db):
    _names(db)
    order = setup.order(db, "G", datetime(2026, 11, 11, 9), name="=Nguyen")
    setup.returned(db, order, 86)
    ws = _sheet(collect_rows(db, UNTIL).all_rows)
    assert ws["E3"].value == "=Nguyen" and ws["E3"].data_type == "s"


def test_a_purged_customer_takes_the_name_from_the_return(db):
    _names(db)
    order = setup.order(db, "H", datetime(2026, 11, 11, 9), customer=False)
    setup.pasted_order(db, order, setup.history_file(db))
    setup.returned(db, order, 87)
    (row,) = collect_rows(db, UNTIL).return_rows
    assert row.billing_name == "Nguyễn Văn A" and row.billing_city


def test_the_draft_labels_return_rows(db):
    _names(db)
    order = setup.order(db, "I", datetime(2026, 11, 11, 9))
    setup.returned(db, order, 88)
    (row,) = collect_rows(db, UNTIL, draft=True).return_rows
    assert row.status == "Hủy đơn (cả đơn) – biên bản 088/11.2026 ALK-KH.STMĐT"


def test_the_all_orders_file_labels_the_order_and_adds_its_return_rows(db):
    _names(db)
    order = setup.order(db, "J", datetime(2026, 11, 11, 9))
    setup.returned(db, order, 89, reason="RETURN")
    rows = collect_all_rows(db, date(2026, 11, 1), date(2026, 11, 30))
    sale, back = rows
    assert "Trả hàng – biên bản 089/" in sale.status
    assert back.quantity == -1 and back.status.endswith("Chưa xác nhận")


def test_a_return_without_sale_lines_is_blocked_not_written_empty(db):
    _names(db)
    order = setup.order(db, "K", datetime(2026, 11, 11, 9))
    setup.pasted_order(db, order, setup.history_file(db))
    sales_return = setup.returned(db, order, 90)
    sales_return.sale_lines = []
    db.flush()
    result = collect_rows(db, UNTIL)
    assert result.return_ids == [] and result.return_rows == []
    (blocked,) = result.blocked
    assert "backfill" in blocked.reasons[0].text
