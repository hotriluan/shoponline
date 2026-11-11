from datetime import date

import pytest
from sqlalchemy import select

from shoponline.db.models import SalesOrder, SapSoRef
from shoponline.domain import states
from shoponline.domain.sku_mapping import upsert_mapping
from shoponline.importers.excel_table import FileRejected
from shoponline.importers.order_import import import_orders
from shoponline.importers.sap_reports import read_zrsd001, read_zrsd004
from shoponline.importers.shopee_orders import read_shopee_orders
from shoponline.reconcile.so_link import (
    LinkError,
    batch_report,
    link_manually,
    mark_delivered,
    store_so_reports,
)
from tests.fixtures.build_fixtures import (
    shopee_orders_file,
    shopee_row,
    zrsd001_file,
    zrsd001_row,
    zrsd004_file,
    zrsd004_row,
)

D = date(2026, 11, 11)


@pytest.fixture
def batch(db, tmp_path):
    upsert_mapping(db, "SHOPEE", "Sơn thử A", "Màu 01,1 lít", "100000001", "SAP A", "t")
    upsert_mapping(db, "SHOPEE", "Bộ thử B", "Bộ 1", "100000003", "SAP KIT", "t")
    path = shopee_orders_file(
        tmp_path / "s.xlsx",
        [
            shopee_row("A1", quantity=2),
            shopee_row("A2", seller_subsidy=10000),
            shopee_row("A3", product="Bộ thử B", variation="Bộ 1"),
            shopee_row("A4"),
        ],
    )
    return import_orders(db, read_shopee_orders(path), "SHOPEE", D, "t").batch


def _order(db, order_id):
    return db.scalar(select(SalesOrder).where(SalesOrder.platform_order_id == order_id))


def _load(db, tmp_path, rows, **kwargs):
    reports = read_zrsd001(zrsd001_file(tmp_path / "z1.xlsx", rows))
    return store_so_reports(db, reports, "t", **kwargs)


def test_links_orders_and_reports_four_kinds(db, tmp_path, batch):
    result = _load(
        db,
        tmp_path,
        [
            zrsd001_row("210000001", "A1", "100000001", 2, 200000),
            zrsd001_row("210000002", "A2", "100000001", 1, 100000),  # subsidy not applied
            # kit: main line 10 plus a zero-value component line 11
            zrsd001_row("210000003", "A3", "100000003", 1, 100000),
            zrsd001_row("210000003", "A3", "100000099", 1, 0, item_no="11"),
            zrsd001_row("210000009", "A9-typo", "100000001", 1, 100000),  # wrong PO No
            zrsd001_row("210000010", "A4", "100000001", 1, 100000),
            zrsd001_row("210000011", "A4", "100000001", 1, 100000),  # duplicate SO for A4
            zrsd001_row("210000020", "OTHER", "100000001", sold_to="1200001146"),  # TikTok
        ],
    )
    assert {o.platform_order_id for o in result.linked} == {"A1", "A2", "A3"}
    assert _order(db, "A1").status == states.SO_LINKED
    assert _order(db, "A1").so_number == "210000001"
    assert _order(db, "A4").so_number is None

    report = batch_report(db, batch)
    assert [o.platform_order_id for o in report.missing_so] == ["A4"]
    assert [r.so_number for r in report.unmatched_sos] == ["210000009"]
    assert report.duplicate_po == [("A4", ["210000010", "210000011"])]
    assert [m.order.platform_order_id for m in report.value_mismatch] == ["A2"]
    assert report.value_mismatch[0].expected == 90000


def test_reimport_changes_nothing(db, tmp_path, batch):
    rows = [zrsd001_row("210000001", "A1", "100000001", 2, 200000)]
    first = _load(db, tmp_path, rows)
    second = _load(db, tmp_path, rows)
    assert (first.new, second.new, second.unchanged, len(second.linked)) == (1, 0, 1, 0)


def test_material_mismatch_reported(db, tmp_path, batch):
    _load(db, tmp_path, [zrsd001_row("210000001", "A1", "100000777", 2, 200000)])
    report = batch_report(db, batch)
    assert "vật tư" in report.value_mismatch[0].detail


def test_manual_link_clears_unmatched(db, tmp_path, batch):
    _load(db, tmp_path, [zrsd001_row("210000009", "A4-typo", "100000001", 1, 100000)])
    order = _order(db, "A4")
    link_manually(db, order, "210000009", "t")
    assert order.status == states.SO_LINKED
    report = batch_report(db, batch)
    assert report.unmatched_sos == []
    with pytest.raises(LinkError):
        link_manually(db, _order(db, "A1"), "210000009", "t")


def test_wrong_filter_warns(db, tmp_path, batch):
    result = _load(
        db,
        tmp_path,
        [zrsd001_row("210000001", "A1", "100000001", 2, 200000, doc_date=date(2026, 11, 3))],
        expect_batch=batch,
    )
    assert result.warnings and "bộ lọc" in result.warnings[0]


def test_zrsd001_with_hand_added_duplicate_po_column(db, tmp_path):
    # Admins sometimes add a second "PO No" column; the first one is used.
    from openpyxl import load_workbook

    path = zrsd001_file(tmp_path / "z.xlsx", [zrsd001_row("210000001", "A1", "100000001")])
    wb = load_workbook(path)
    ws = wb.active
    ws.insert_cols(10)
    ws.cell(1, 10, "PO No")
    ws.cell(2, 10, "A1")
    wb.save(path)
    assert read_zrsd001(path)[0].po_no == "A1"


def test_zrsd001_missing_column_rejected(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(["PO No", "SalesDoc"])
    wb.save(tmp_path / "bad.xlsx")
    with pytest.raises(FileRejected, match="Net Value"):
        read_zrsd001(tmp_path / "bad.xlsx")


def test_delivered_from_zrsd004(db, tmp_path, batch):
    _load(db, tmp_path, [zrsd001_row("210000001", "A1", "100000001", 2, 200000)])
    rows = read_zrsd004(
        zrsd004_file(tmp_path / "z4.xlsx", [zrsd004_row("1900000001", "210000001", "100000001", 2)])
    )
    assert mark_delivered(db, rows, "t") == 1
    order = _order(db, "A1")
    assert (order.status, order.do_number) == (states.DELIVERED, "1900000001")
    assert db.get(SapSoRef, "210000001").po_no == "A1"
