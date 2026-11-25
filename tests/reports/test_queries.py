from datetime import date, datetime

from shoponline.reports import history_import, queries
from shoponline.reports.queries import Filters
from tests import sales_history_setup as setup
from tests.history_setup import line, write

NOV = date(2026, 11, 1)
OCT = date(2026, 10, 1)
AFTER = datetime(2026, 11, 12, 9)


def _invoice(db, order, net, tax):
    row = db.get(setup.SapTaxInvoice, order.do_number)
    row.net_value_vnd, row.tax_vnd = net, tax
    db.flush()


def _history(db, settings, tmp_path, *rows):
    history_import.apply(
        db, settings, write(tmp_path / "h.xlsx", list(rows)), "t", skip_backup_check=True
    )


def _october(**changes):
    return line(created="2026-10-05 10:00", month=10, year=2026, **changes)


def test_monthly_overview_joins_history_and_system_by_month(db, settings, tmp_path):
    _history(db, settings, tmp_path, _october(paid=500000))
    setup.report_name(db)
    order = setup.order(
        db, "S-1", AFTER, lines=((setup.MATERIAL, 1, 120000, 20000),), settlement=80000
    )
    _invoice(db, order, 90000, 7200)
    window = Filters(from_period=OCT, to_period=NOV)

    rows = {r["period"]: r for r in queries.monthly_overview(db, window)}

    assert rows[OCT]["marketplace_value"] == 500000 and rows[OCT]["invoice_value"] is None
    assert rows[OCT]["settled_value"] is None and rows[OCT]["platform_fee"] is None
    nov = rows[NOV]
    assert (nov["marketplace_value"], nov["invoice_value"], nov["settled_value"]) == (
        100000,
        97200,
        80000,
    )
    assert nov["subsidy_gap"] == 2800 and nov["platform_fee"] == 17200
    assert nov["orders"] == 1 and nov["average_order"] == 100000


def test_platform_fee_only_counts_orders_that_have_both_figures(db):
    full = setup.order(db, "S-1", AFTER, settlement=80000)
    _invoice(db, full, 100000, 0)
    no_money = setup.order(db, "S-2", AFTER, settlement=None)
    _invoice(db, no_money, 200000, 0)
    no_invoice = setup.order(db, "S-3", AFTER, invoice=None, settlement=50000)

    row = queries.monthly_overview(db, Filters(from_period=NOV))[0]

    assert row["platform_fee"] == 20000
    assert row["subsidy_gap"] == (120000 - 100000) + (120000 - 200000)
    assert (row["missing_invoice"], row["missing_settlement"]) == (1, 1)
    assert no_invoice.id  # the third order is delivered but has no invoice


def test_return_rate_is_returns_over_invoice_revenue(db):
    from shoponline.db.models import SalesReturnLine
    from tests.returns.factory import sales_return

    order = setup.order(db, "S-1", AFTER)
    _invoice(db, order, 100000, 0)
    doc = sales_return(db, order, year=2026, seq=1)
    db.add(
        SalesReturnLine(
            return_id=doc.id, line_no=1, so_item_no=10, material_number=setup.MATERIAL,
            sap_name="x", invoice_name="x", invoice_unit="x", stock_unit="PC", invoice_qty=1,
            return_qty=1, unit_price=25000, amount_before=25000, amount_returned=25000,
        )
    )  # fmt: skip
    db.flush()

    row = queries.monthly_overview(db, Filters(from_period=NOV))[0]
    by_reason = queries.returns(db, Filters(from_period=NOV))

    assert row["returned_value"] == 25000 and row["return_rate"] == 0.25
    assert by_reason == [
        {"period": NOV, "reason_kind": "CANCEL", "documents": 1, "returned_value": 25000}
    ]


def test_filters_narrow_by_platform_shop_and_months(db, settings, tmp_path):
    _history(
        db,
        settings,
        tmp_path,
        _october(paid=500000),
        _october(paid=1, division="tiktok Bình Dương", name="B"),
    )
    setup.order(db, "S-1", AFTER)
    setup.order(db, "T-1", AFTER, platform="TIKTOK")

    only_tiktok = queries.by_channel(db, Filters(platforms=("TIKTOK",)))
    only_shop = queries.monthly_overview(db, Filters(shop_codes=("SHOPEE_BD",)))
    only_october = queries.monthly_overview(db, Filters(from_period=OCT, to_period=OCT))

    assert {r["shop_code"] for r in only_tiktok} == {"TIKTOK_BD"}
    assert {r["period"] for r in only_shop} == {OCT, NOV}
    assert [r["period"] for r in only_october] == [OCT]
    assert only_october[0]["marketplace_value"] == 500001


def test_by_channel_and_by_product_total_the_same_value(db, settings, tmp_path):
    _history(db, settings, tmp_path, _october(paid=300), _october(paid=700, item="Other", name="B"))
    setup.report_name(db)
    setup.order(db, "S-1", AFTER, lines=((setup.MATERIAL, 3, 1000, 0),))

    channel = queries.by_channel(db, Filters())
    product = queries.by_product(db, Filters())

    assert sum(r["marketplace_value"] for r in channel) == 300 + 700 + 3000
    assert sum(r["marketplace_value"] for r in product) == 300 + 700 + 3000
    assert (
        product[0]["item_name"] == f"Propan - SƠN {setup.MATERIAL}" and product[0]["quantity"] == 3
    )
    assert len(queries.by_product(db, Filters(), limit=1)) == 1


def test_by_province_puts_the_unplaced_last(db, settings, tmp_path):
    _history(
        db, settings, tmp_path,
        _october(paid=100, city="Kiên Giang"),
        _october(paid=900, city="Huyện Châu Thành", name="B"),
        _october(paid=150, city="Thành Phố Thủ Đức", name="C"),
    )  # fmt: skip

    rows = queries.by_province(db, Filters())

    assert [r["province"] for r in rows] == ["Hồ Chí Minh", "An Giang", queries.UNKNOWN_PROVINCE]
    assert rows[-1]["marketplace_value"] == 900


def test_data_notes_warn_about_history_and_the_missing_start_of_november(db, settings, tmp_path):
    setup.order(db, "S-1", AFTER)

    gap = queries.data_notes(db, Filters())
    assert any("thiếu đơn từ ngày 01 đến 10/11" in n for n in gap)
    assert not any("file lịch sử" in n for n in gap)

    _history(db, settings, tmp_path, _october())
    with_history = queries.data_notes(db, Filters())
    assert any("file lịch sử" in n for n in with_history)
    assert any("thiếu đơn từ ngày 01 đến 10/11" in n for n in with_history)

    _history(
        db, settings, tmp_path, line(created="2026-11-05 10:00", month=11, year=2026, name="Z")
    )
    complete = queries.data_notes(db, Filters())
    assert not any("thiếu đơn" in n for n in complete)
    assert not queries.data_notes(db, Filters(from_period=date(2026, 12, 1)))
