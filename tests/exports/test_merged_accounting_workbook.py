from datetime import date
from io import BytesIO

import pytest
from openpyxl import load_workbook

from shoponline.exports import accounting_workbook as mod
from shoponline.exports.accounting_workbook import (
    CustomerLine,
    build_accounting_workbook,
    build_merged_accounting_workbook,
)
from shoponline.importers.excel_table import FileRejected
from tests.fixtures.build_fixtures import ZRSD004_HEADERS, zrsd004_file, zrsd004_row

TODAY = date(2026, 11, 13)
SHOPEE, TIKTOK, LAZADA = "1200001145", "1200001146", "1200001147"


def _lookup(so_number, _sold_to):
    return CustomerLine(f"ORDER-{so_number}", "Người Mua", "Địa chỉ thử")


def _merge(sources, **overrides):
    options = {
        "exclude_deliveries": set(),
        "cutoff": None,
        "today": TODAY,
        "platform_sold_to": {SHOPEE, TIKTOK, LAZADA},
    }
    options.update(overrides)
    return build_merged_accounting_workbook(sources, _lookup, **options)


def _rows_of(workbook):
    buffer = BytesIO()
    workbook.save(buffer)
    sheet = load_workbook(BytesIO(buffer.getvalue())).worksheets[0]
    return [[c.value for c in row] for row in sheet.iter_rows()]


def _col(name):
    return ZRSD004_HEADERS.index(name) + 3  # the three inserted columns sit before it


DELIVERY = ZRSD004_HEADERS.index("Delivery")


def _data(rows):
    return [r for r in rows[1:] if r[DELIVERY]]


def _totals(rows):
    return [r for r in rows[1:] if not r[DELIVERY]]


def test_one_unit_gives_one_total_row(tmp_path):
    source = zrsd004_file(
        tmp_path / "a.xlsx",
        [
            zrsd004_row("1900000001", "210000001", "1", 3, tonase="1.5", tonase_unit="KG"),
            zrsd004_row("1900000002", "210000002", "2", 4, tonase="2.25", tonase_unit="KG"),
        ],
    )
    totals = _totals(_rows_of(_merge([source]).workbook))
    assert len(totals) == 1
    assert totals[0][_col("Delivery Qty")] == 7
    assert totals[0][_col("Actual Delivery Qty")] == 7
    assert totals[0][_col("Sales Unit")] == "PC"
    assert totals[0][_col("Tonase")] == 3.75
    assert totals[0][_col("Tonase Unit")] == "KG"
    assert not totals[0][_col("Net Weight")]


def test_two_units_give_two_total_rows_each_summed_by_its_own_unit(tmp_path):
    source = zrsd004_file(
        tmp_path / "a.xlsx",
        [
            zrsd004_row("1900000001", "210000001", "1", 20, sales_unit="PC"),
            zrsd004_row(
                "1900000002",
                "210000002",
                "2",
                1,
                sales_unit="SET",
                tonase="16.4",
                tonase_unit="KG",
                net_weight="14.032",
                weight_unit="KG",
                volume="15.65",
                volume_unit="LT",
            ),
        ],
    )
    totals = _totals(_rows_of(_merge([source]).workbook))
    assert len(totals) == 2
    set_row, pc_row = totals
    assert set_row[_col("Sales Unit")] == "SET"
    assert set_row[_col("Delivery Qty")] == 1 and set_row[_col("Actual Delivery Qty")] == 1
    assert set_row[_col("Tonase")] == 16.4
    assert set_row[_col("Net Weight")] == 14.032
    assert set_row[_col("Volume")] == 15.65
    assert pc_row[_col("Sales Unit")] == "PC"
    assert pc_row[_col("Delivery Qty")] == 20 and pc_row[_col("Actual Delivery Qty")] == 20
    assert not pc_row[_col("Tonase")] and not pc_row[_col("Net Weight")]
    assert not pc_row[_col("Tonase Unit")] and not pc_row[_col("Volume Unit")]


def test_sums_are_exact_decimals(tmp_path):
    values = ["0.664", "0.744", "0.1", "0.2", "1.005"]
    rows = [
        zrsd004_row(f"19000000{i:02d}", f"2100000{i:02d}", "1", net_weight=v, weight_unit="KG")
        for i, v in enumerate(values)
    ]
    out = _rows_of(_merge([zrsd004_file(tmp_path / "a.xlsx", rows)]).workbook)
    assert repr(_totals(out)[0][_col("Net Weight")]) == "2.713"


def test_three_sources_equal_one_hand_made_file(tmp_path):
    shopee = [
        zrsd004_row("1900000001", "210000001", "1", 2, tonase="1.2", tonase_unit="KG"),
        zrsd004_row("1900000001", "210000001", "2", line_item=20),
    ]
    tiktok = [zrsd004_row("1900000002", "210000002", "3", 1, sold_to=TIKTOK)]
    lazada = [zrsd004_row("1900000003", "210000003", "4", 5, sold_to=LAZADA)]
    sources = [
        zrsd004_file(tmp_path / "s.xlsx", shopee),
        zrsd004_file(tmp_path / "t.xlsx", tiktok),
        zrsd004_file(tmp_path / "l.xlsx", lazada),
    ]
    by_hand = zrsd004_file(tmp_path / "h.xlsx", shopee + tiktok + lazada)

    merged = _rows_of(_merge(sources).workbook)
    expected = _rows_of(build_accounting_workbook(by_hand, _lookup).workbook)

    assert merged == expected


def test_drops_foreign_customers_unissued_future_cutoff_and_sent(tmp_path):
    rows = [
        zrsd004_row("1900000001", "210000001", "1"),
        zrsd004_row("1900000002", "210000002", "1", sold_to="9999999999"),
        zrsd004_row("1900000003", "210000003", "1", gi_date=None),
        zrsd004_row("1900000004", "210000004", "1", gi_date=date(2026, 11, 14)),
        zrsd004_row("1900000005", "210000005", "1", goods_status="A"),
        zrsd004_row("1900000006", "210000006", "1", gi_date=date(2026, 10, 1)),
        zrsd004_row("1900000007", "210000007", "1"),
        zrsd004_row("1900000007", "210000007", "2", line_item=20),
    ]
    result = _merge(
        [zrsd004_file(tmp_path / "a.xlsx", rows)],
        cutoff=date(2026, 10, 31),
        exclude_deliveries={"1900000007"},
    )

    assert result.deliveries == {"1900000001"}
    assert result.so_numbers == {"210000001"}
    assert result.dropped == {
        mod.FOREIGN_CUSTOMER: 1,
        mod.NO_GI_DATE: 2,
        mod.NOT_COMPLETE: 1,
        mod.BEFORE_CUTOFF: 1,
        mod.ALREADY_SENT: 2,
    }
    assert {(s.delivery, s.reason) for s in result.skipped} == {
        ("1900000003", mod.NO_GI_DATE),
        ("1900000004", mod.NO_GI_DATE),
        ("1900000005", mod.NOT_COMPLETE),
    }
    assert len(_data(_rows_of(result.workbook))) == 1


def test_duplicate_line_keeps_the_first_source_and_rows_are_sorted(tmp_path):
    first = zrsd004_file(
        tmp_path / "a.xlsx",
        [zrsd004_row("1900000009", "210000009", "1", 7), zrsd004_row("1900000002", "2", "1", 1)],
    )
    second = zrsd004_file(
        tmp_path / "b.xlsx",
        [zrsd004_row("1900000009", "210000009", "1", 99), zrsd004_row("1900000005", "5", "1", 1)],
    )
    out = _rows_of(_merge([first, second]).workbook)
    assert [r[DELIVERY] for r in _data(out)] == ["1900000002", "1900000005", "1900000009"]
    assert _data(out)[-1][_col("Delivery Qty")] == 7


def test_file_name_uses_the_latest_goods_issue_date(tmp_path):
    rows = [
        zrsd004_row("1900000001", "1", "1", gi_date=date(2026, 11, 11)),
        zrsd004_row("1900000002", "2", "1", gi_date=date(2026, 11, 13)),
    ]
    result = _merge([zrsd004_file(tmp_path / "a.xlsx", rows)])
    assert result.file_name == "SHOP ONLINE 131126.xlsx"


def test_sources_with_different_columns_are_refused(tmp_path):
    good = zrsd004_file(tmp_path / "a.xlsx", [zrsd004_row("1900000001", "1", "1")])
    bad = tmp_path / "b.xlsx"
    wb = load_workbook(good)
    wb.worksheets[0].cell(1, 5).value = "Renamed"
    wb.save(bad)
    with pytest.raises(FileRejected, match="b.xlsx"):
        _merge([good, bad])


def test_nothing_left_is_refused(tmp_path):
    source = zrsd004_file(tmp_path / "a.xlsx", [zrsd004_row("1900000001", "1", "1")])
    with pytest.raises(FileRejected, match="Không có DO mới"):
        _merge([source], exclude_deliveries={"1900000001"})
    with pytest.raises(FileRejected, match="Không có DO mới"):
        _merge([])
