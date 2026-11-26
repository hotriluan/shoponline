from datetime import date, datetime

import pytest

from shoponline.accounting.runs import _pending_orders
from shoponline.db.models import AccountingSentDelivery
from shoponline.domain import states
from shoponline.exports.sales_history_workbook import TAX_INVOICE, collect_rows, pending_orders
from tests import sales_history_setup as setup


def test_a_delivered_order_with_an_invoice_is_refused(db):
    order = setup.order(db, "INVOICED", datetime(2026, 11, 11))
    assert not states.can_cancel(db, order)
    with pytest.raises(states.CancelRefused, match="đã có hóa đơn"):
        states.cancel_order(db, order, "admin", "DO hủy")
    assert order.status == states.DELIVERED


def test_a_delivered_order_without_an_invoice_is_cancelled_and_leaves_both_queues(db):
    order = setup.order(db, "NOINV", datetime(2026, 11, 11), invoice=None)
    assert order in pending_orders(db, date(2026, 11, 30))
    assert order in [o for o, _ in _pending_orders(db, date(2026, 11, 30))]
    assert states.can_cancel(db, order)

    assert states.cancel_order(db, order, "admin", "DO đã hủy trong SAP") is None
    assert (order.status, order.status_reason) == (states.CANCELLED, "DO đã hủy trong SAP")
    assert order not in pending_orders(db, date(2026, 11, 30))
    assert order not in [o for o, _ in _pending_orders(db, date(2026, 11, 30))]


def test_a_do_already_sent_to_accounting_is_cancelled_with_a_warning(db):
    order = setup.order(db, "SENT", datetime(2026, 11, 11), invoice=None)
    db.add(AccountingSentDelivery(delivery=order.do_number))
    db.flush()
    warning = states.cancel_order(db, order, "admin", "DO đã hủy trong SAP")
    assert order.status == states.CANCELLED and "kế toán" in warning


def test_a_reason_is_required(db):
    order = setup.order(db, "NOREASON", datetime(2026, 11, 11), status=states.NEW)
    with pytest.raises(states.CancelRefused, match="lý do"):
        states.cancel_order(db, order, "admin", "  ")


def test_transition_alone_refuses_to_cancel_a_delivered_order(db):
    order = setup.order(db, "DIRECT", datetime(2026, 11, 11), invoice=None)
    with pytest.raises(states.InvalidTransition):
        states.transition(db, order, states.CANCELLED, "admin", "x")


def test_an_uninvoiced_order_never_reaches_the_shop_online_file(db):
    # So an order cancelled this way cannot already be in a pasted file.
    setup.report_name(db)
    setup.order(db, "WAIT", datetime(2026, 11, 11), invoice=None)
    result = collect_rows(db, date(2026, 11, 30))
    assert result.rows == []
    assert [r.kind for b in result.blocked for r in b.reasons] == [TAX_INVOICE]
