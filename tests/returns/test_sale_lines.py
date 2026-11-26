from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select

from shoponline.db.models import SalesReturnSaleLine
from shoponline.returns import sale_lines
from shoponline.returns.amounts import Blocked
from shoponline.returns.sale_lines import ReturnedQuantity, SaleLine
from tests.returns import factory

A, B = "100001787", "100002222"


@dataclass
class Item:
    id: int
    material_number: str | None
    quantity: int
    unit_price: int
    unit_subsidy: int = 0


def taken(material, invoiced, returned):
    return ReturnedQuantity(material, Decimal(invoiced), Decimal(returned))


def test_a_whole_return_takes_back_every_platform_line():
    items = [Item(1, A, 1, 120000, 20000), Item(2, B, 2, 30000)]
    found = sale_lines.split(items, [taken(A, 1, 1), taken(B, 2, 2)])
    assert found == [SaleLine(1, 1, 100000), SaleLine(2, 2, 60000)]


def test_a_partial_return_takes_only_the_returned_units():
    items = [Item(1, A, 1, 120000), Item(2, B, 3, 30000, 5000)]
    assert sale_lines.split(items, [taken(A, 1, 0), taken(B, 3, 1)]) == [SaleLine(2, 1, 25000)]


def test_two_platform_lines_of_one_material_at_different_prices_keep_their_own_price():
    items = [Item(1, A, 2, 50000), Item(2, A, 4, 40000)]
    found = sale_lines.split(items, [taken(A, 6, 3)])
    assert found == [SaleLine(1, 1, 50000), SaleLine(2, 2, 80000)]


def test_a_share_that_does_not_land_on_whole_units_is_blocked():
    items = [Item(1, A, 1, 50000), Item(2, A, 1, 40000)]
    found = sale_lines.split(items, [taken(A, 2, 1)])
    assert isinstance(found, Blocked)
    assert "không chia đúng" in found.reason and A in found.reason


def test_a_material_missing_from_the_platform_order_is_blocked():
    found = sale_lines.split([Item(1, A, 1, 50000)], [taken(A, 1, 0), taken(B, 1, 1)])
    assert isinstance(found, Blocked) and "không có trên đơn sàn" in found.reason


def test_a_quantity_that_differs_from_the_invoice_is_blocked():
    found = sale_lines.split([Item(1, A, 2, 50000)], [taken(A, 3, 3)])
    assert isinstance(found, Blocked) and "không quy đổi được" in found.reason


def test_a_whole_return_with_a_platform_line_not_on_the_invoice_is_blocked():
    found = sale_lines.split([Item(1, A, 1, 50000), Item(2, B, 1, 1000)], [taken(A, 1, 1)])
    assert isinstance(found, Blocked) and B in found.reason


def test_a_kit_is_split_on_its_parent_material(db):
    order = factory.delivered_order(
        db,
        lines=((A, 1, 120000),),
        so_items=((10, A, 1, 120000), (11, "100003333", 1, 0)),
    )
    # Return lines carry the SAP main lines only; the kit's parent matches the platform line.
    (item,) = order.items
    assert sale_lines.split(order.items, [taken(A, 1, 1)]) == [SaleLine(item.id, 1, 120000)]


def test_backfill_writes_missing_sale_lines_once_and_reports_what_it_cannot(db):
    order = factory.delivered_order(db)
    old = factory.sales_return(db, order, year=2026, seq=80, status="VOID")
    old.lines = [_line(A, 1, 1)]
    other = factory.delivered_order(db, "261115OTHER001", lines=((B, 1, 120000),))
    stray = factory.sales_return(db, other, year=2026, seq=81)
    stray.lines = [_line(A, 1, 1)]
    db.flush()

    written, blocked = sale_lines.backfill(db)
    assert written == [old.doc_no]
    assert [doc for doc, _ in blocked] == [stray.doc_no]
    rows = db.scalars(select(SalesReturnSaleLine)).all()
    assert [(r.return_id, r.quantity, r.customer_paid) for r in rows] == [(old.id, 1, 120000)]

    again, blocked_again = sale_lines.backfill(db)
    assert again == [] and len(blocked_again) == 1


def _line(material, invoiced, returned):
    from shoponline.db.models import SalesReturnLine

    return SalesReturnLine(
        line_no=1,
        so_item_no=10,
        material_number=material,
        sap_name="S",
        invoice_name="N",
        invoice_unit="U",
        stock_unit="PC",
        invoice_qty=invoiced,
        return_qty=returned,
        unit_price=111111,
        amount_before=111111,
        amount_returned=111111 if returned else 0,
    )
