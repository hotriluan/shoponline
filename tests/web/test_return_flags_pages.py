"""Return labels on the pages that list orders: batch, Lazada payouts, accounting runs."""

from datetime import datetime

import pytest

from shoponline.db.models import AccountingRun, AccountingSentDelivery
from shoponline.returns import service
from tests import sales_history_setup as setup
from tests.returns.factory import sales_return

WHEN = datetime(2026, 11, 12, 9)


@pytest.fixture
def returned(db):
    order = setup.order(db, "LZ-1", WHEN, platform="LAZADA")
    doc = sales_return(db, order, year=2026, seq=80)
    db.commit()
    return order, doc


def test_the_batch_page_shows_the_label_and_loses_it_when_the_return_is_voided(db, login, returned):
    order, doc = returned
    admin = login("admin")
    page = admin.get(f"/batches/{order.order_batch_id}").text
    assert "Hủy sau HĐ" in page and f'<a href="/returns/{doc.id}">{doc.doc_no}</a>' in page

    viewer_page = login("viewer").get(f"/batches/{order.order_batch_id}").text
    assert "Hủy sau HĐ" in viewer_page
    assert f'<a href="/returns/{doc.id}">' not in viewer_page

    service.void(db, doc.id, "lập nhầm", "admin")
    db.commit()
    assert "Hủy sau HĐ" not in admin.get(f"/batches/{order.order_batch_id}").text


def test_lazada_lists_and_previews_warn_about_an_order_returned_whole(db, login, returned):
    admin = login("admin")
    assert "Hủy sau HĐ" in admin.get("/settlements/lazada").text
    preview = admin.post(
        "/settlements/lazada/preview", data={"paste": "LZ-1\t70.000\t12/11/2026"}
    ).text
    assert "Đơn đã hủy hoặc trả cả đơn" in preview and "lưu được" in preview


def test_lazada_partial_return_shows_the_label_without_the_warning(db, login):
    order = setup.order(db, "LZ-2", WHEN, platform="LAZADA")
    sales_return(db, order, year=2026, seq=81).full_return = False
    db.commit()
    page = (
        login("admin")
        .post("/settlements/lazada/preview", data={"paste": "LZ-2\t70.000\t12/11/2026"})
        .text
    )
    assert "Trả một phần" in page and "Đơn đã hủy hoặc trả cả đơn" not in page


def test_a_finalized_accounting_run_lists_the_deliveries_with_a_return(db, login, returned):
    order, doc = returned
    run = AccountingRun(status="FINALIZED", created_by="admin", finalized_by="admin")
    db.add(run)
    db.flush()
    db.add(AccountingSentDelivery(delivery=order.do_number, run_id=run.id))
    db.commit()
    page = login("viewer").get(f"/accounting/runs/{run.id}").text
    assert "DO của đơn có phiếu trả hàng (1)" in page
    assert f"DO {order.do_number}" in page and doc.doc_no in page
