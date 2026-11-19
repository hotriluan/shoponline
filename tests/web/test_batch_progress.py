"""Batch pages show how many orders already have a tax invoice and money received."""

from datetime import datetime

from tests import sales_history_setup as setup

WHEN = datetime(2026, 11, 10, 9, 0)


def _two_orders(db):
    setup.order(db, "SP1", WHEN, invoice="HD0001", settlement=250000)
    setup.order(db, "SP2", WHEN, invoice=None, settlement=None)
    db.commit()
    return setup.batch(db)


def test_list_counts_orders_with_invoice_and_money(db, login):
    _two_orders(db)
    html = login("viewer").get("/batches").text
    assert "Đã có hóa đơn: 1" in html
    assert "Đã có tiền vô: 1" in html


def test_detail_shows_summary_and_per_order_invoice_and_money(db, login):
    batch = _two_orders(db)
    html = login("viewer").get(f"/batches/{batch.id}").text
    assert "Đã có hóa đơn: 1" in html
    assert "Đã có tiền vô: 1" in html
    assert "<th>Số hóa đơn</th><th>Tiền vô</th>" in html
    assert "HD0001" in html
    assert "250.000" in html or "250,000" in html


def test_lazada_never_counts_money_received(db, login):
    setup.order(db, "LZ1", WHEN, platform="LAZADA", invoice="HD0009")
    db.commit()
    html = login("viewer").get("/batches").text
    assert "Đã có hóa đơn: 1" in html
    assert "Đã có tiền vô: 0" in html
