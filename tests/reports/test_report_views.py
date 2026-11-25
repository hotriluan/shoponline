from datetime import date, datetime

from sqlalchemy import text

from shoponline.db.models import ProvinceAlias, SalesReturnLine
from shoponline.reports import REPORTING_CUTOVER
from tests import sales_history_setup as setup
from tests.history_setup import line, write
from tests.returns.factory import sales_return

AFTER = datetime(2026, 11, 12, 9)
BEFORE = datetime(2026, 11, 10, 23, 59)


def _lines(db, source=None):
    sql = "SELECT * FROM report_sale_line"
    if source:
        sql += f" WHERE source = '{source}'"
    return db.execute(text(sql)).mappings().all()


def _revenue(db):
    return {
        r["sales_order_id"]: r
        for r in db.execute(text("SELECT * FROM report_order_revenue")).mappings()
    }


def _invoice(db, order, net, tax):
    row = db.get(setup.SapTaxInvoice, order.do_number)
    row.net_value_vnd, row.tax_vnd = net, tax
    db.flush()


def test_the_cutover_in_the_views_is_the_one_in_the_code(db):
    for view in ("report_sale_line", "report_order_revenue"):
        definition = db.execute(text(f"SELECT pg_get_viewdef('{view}'::regclass)")).scalar()
        assert f"'{REPORTING_CUTOVER:%Y-%m-%d} " in definition


def test_system_lines_start_at_the_cutover_and_skip_cancelled_orders(db):
    setup.report_name(db)
    kept = setup.order(db, "S-AFTER", AFTER)
    setup.order(db, "S-BEFORE", BEFORE)
    setup.order(db, "S-CANCELLED", AFTER, status="CANCELLED")
    db.flush()

    rows = _lines(db, "system")

    assert [r["order_key"] for r in rows] == [str(kept.id)]
    assert set(_revenue(db)) == {kept.id}


def test_a_system_line_is_priced_net_of_subsidy_and_named_from_the_report_name(db):
    setup.report_name(db)
    setup.order(db, "S-1", AFTER, lines=((setup.MATERIAL, 2, 120000, 20000),))

    row = _lines(db, "system")[0]

    assert row["customer_paid"] == 200000 and row["quantity"] == 2
    assert row["item_name"] == f"Propan - SƠN {setup.MATERIAL}" and row["size"] == "0.8 lít"
    assert row["period"] == date(2026, 11, 1) and row["ordered_on"] == date(2026, 11, 12)
    assert (row["platform"], row["shop_code"], row["division"]) == (
        "SHOPEE", "SHOPEE_BD", "Shopee Bình Dương"
    )  # fmt: skip


def test_without_a_report_name_the_platform_names_are_used(db):
    setup.order(db, "S-1", AFTER, lines=((None, 1, 1000, 0),))

    row = _lines(db, "system")[0]

    assert (row["item_name"], row["size"], row["variation"]) == ("P", None, "V1")


def test_province_of_a_system_order_comes_from_its_address_then_the_alias(db):
    setup.order(db, "S-1", AFTER)
    setup.order(db, "S-2", AFTER, address="1 Lê Lợi, Huyện Châu Thành, Việt Nam")
    db.flush()
    assert {r["province"] for r in _lines(db, "system")} == {"Hồ Chí Minh", None}

    db.add(ProvinceAlias(raw_key="huyen chau thanh", province="Tiền Giang", updated_by="t"))
    db.flush()

    assert {r["province"] for r in _lines(db, "system")} == {"Hồ Chí Minh", "Tiền Giang"}


def test_history_lines_are_in_the_view_with_shop_division_and_province(db, tmp_path, settings):
    from shoponline.reports import history_import

    path = write(
        tmp_path / "h.xlsx", [line(city="Kiên Giang"), line(city="Huyện Châu Thành", name="B")]
    )
    history_import.apply(db, settings, path, "t", skip_backup_check=True)

    rows = {r["province"]: r for r in _lines(db, "history")}

    assert set(rows) == {"An Giang", None}
    assert rows["An Giang"]["division"] == "Shopee Bình Dương"
    assert rows["An Giang"]["customer_paid"] == 811000
    assert rows["An Giang"]["period"] == date(2025, 11, 1)


def test_order_revenue_has_the_three_figures_and_nothing_is_invented(db):
    both = setup.order(
        db, "S-1", AFTER, lines=((setup.MATERIAL, 1, 120000, 20000),), settlement=80000
    )
    _invoice(db, both, 90000, 7200)
    waiting = setup.order(db, "S-2", AFTER, invoice=None, settlement=None)

    revenue = _revenue(db)

    assert revenue[both.id]["marketplace_value"] == 100000
    assert revenue[both.id]["invoice_value"] == 97200
    assert revenue[both.id]["settled_value"] == 80000
    assert revenue[waiting.id]["invoice_value"] is None
    assert revenue[waiting.id]["settled_value"] is None


def test_a_lazada_order_gets_its_hand_typed_money(db):
    order = setup.order(db, "L-1", AFTER, platform="LAZADA")
    setup.paid(db, "LAZADA", "L-1", 70000)

    assert _revenue(db)[order.id]["settled_value"] == 70000


def test_returns_count_issued_documents_only(db):
    order = setup.order(db, "S-1", AFTER)
    issued = sales_return(db, order, year=2026, seq=1)
    voided = sales_return(db, order, year=2026, seq=2, status="VOID")
    for doc, amount in ((issued, 30000), (voided, 99999)):
        db.add(
            SalesReturnLine(
                return_id=doc.id, line_no=1, so_item_no=10, material_number=setup.MATERIAL,
                sap_name="x", invoice_name="x", invoice_unit="x", stock_unit="PC",
                invoice_qty=1, return_qty=1, unit_price=amount, amount_before=amount,
                amount_returned=amount,
            )
        )  # fmt: skip
    db.flush()

    assert _revenue(db)[order.id]["returned_value"] == 30000


def test_one_invoice_per_order_so_revenue_is_not_doubled(db):
    order = setup.order(db, "S-1", AFTER)
    _invoice(db, order, 100, 8)
    setup.paid(db, "SHOPEE", "S-1", 5, key="second")

    rows = db.execute(text("SELECT * FROM report_order_revenue")).mappings().all()

    assert (
        len(rows) == 1
        and rows[0]["invoice_value"] == 108
        and rows[0]["settled_value"] == setup.SETTLED + 5
    )
