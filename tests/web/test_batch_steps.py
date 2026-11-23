from datetime import datetime

from shoponline.db.models import SalesOrder
from shoponline.domain import states
from shoponline.web.routes.batches import batch_steps


def _order(status):
    return SalesOrder(
        platform="SHOPEE",
        platform_order_id="X",
        ordered_at=datetime(2026, 11, 10),
        status=status,
    )


def _states(steps):
    return [s.state for s in steps]


def test_new_batch_waits_on_mapping():
    steps = batch_steps([_order(states.MAPPING_ERROR), _order(states.READY)], False, False)
    assert _states(steps) == ["done", "current", "todo", "todo", "todo", "todo"]


def test_mapped_batch_waits_on_sales_admin():
    steps = batch_steps([_order(states.READY)], False, False)
    assert _states(steps) == ["done", "done", "current", "todo", "todo", "todo"]


def test_confirmed_batch_with_differences_waits_on_reconcile():
    steps = batch_steps([_order(states.READY)], True, False)
    assert _states(steps) == ["done", "done", "done", "done", "current", "todo"]


def test_delivered_batch_is_complete_except_cancelled_orders():
    orders = [_order(states.DELIVERED), _order(states.CANCELLED)]
    assert _states(batch_steps(orders, True, True)) == ["done"] * 6


def test_current_step_is_marked_on_the_page(db, login):
    from tests import sales_history_setup as setup

    setup.order(db, "SP1", datetime(2026, 11, 10, 9, 0), status=states.READY)
    db.commit()
    html = login("viewer").get(f"/batches/{setup.batch(db).id}").text
    assert html.count('aria-current="step"') == 1
