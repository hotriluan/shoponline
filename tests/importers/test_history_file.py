from datetime import date

import pytest

from shoponline.importers.excel_table import FileRejected
from shoponline.importers.history_file import ordered_on_of, read_history
from tests.history_setup import HEADER, line, write

DIVISIONS = {"shopee bình dương": "SHOPEE_BD", "tiktok bình dương": "TIKTOK_BD"}


def _read(tmp_path, *rows):
    return read_history(write(tmp_path / "h.xlsx", list(rows)), DIVISIONS)


def test_division_is_matched_without_case_or_extra_spaces(tmp_path):
    result = _read(
        tmp_path,
        line(division="shopee Bình Dương"),
        line(division="Tiktok  Bình Dương", name="B"),
    )

    assert [x.shop_code for x in result.lines] == ["SHOPEE_BD", "TIKTOK_BD"]
    assert not result.rejected


def test_an_unknown_division_rejects_only_that_line(tmp_path):
    result = _read(tmp_path, line(division="Sendo"), line(name="B"))

    assert len(result.lines) == 1
    assert result.rejected[0].row == 2 and "Sendo" in result.rejected[0].reason


@pytest.mark.parametrize(
    ("created", "expected"),
    [
        ("2025-11-14 16:21", date(2025, 11, 14)),
        ("14-11-2025 16:21", date(2025, 11, 14)),
        ("2025-14-11 16:21", date(2025, 11, 14)),
        ("14 Nov 2025 16:21", date(2025, 11, 14)),
        ("2025-01-2014:08", None),
        ("", None),
    ],
)
def test_created_time_is_read_the_way_that_matches_the_period(created, expected):
    assert ordered_on_of(created, date(2025, 11, 1)) == expected


def test_day_and_month_swapped_are_resolved_by_the_period():
    assert ordered_on_of("2026-11-08 10:00", date(2026, 8, 1)) == date(2026, 8, 11)


def test_money_and_quantity_are_numbers_even_when_typed_as_text(tmp_path):
    result = _read(tmp_path, line(paid="811000", quantity="2", unit=""))

    got = result.lines[0]
    assert (got.customer_paid, got.quantity, got.unit_price) == (811000, 2, None)


def test_a_line_without_paid_or_quantity_is_rejected(tmp_path):
    result = _read(
        tmp_path, line(paid=""), line(quantity="x", name="B"), line(quantity=0, name="C")
    )

    assert not result.lines and len(result.rejected) == 3


def test_period_comes_from_month_and_year_columns(tmp_path):
    result = _read(tmp_path, line(created="not a date", month=3, year=2024))

    got = result.lines[0]
    assert got.period == date(2024, 3, 1) and got.ordered_on is None


def test_boundary_keeps_up_to_october_and_the_part_of_november_before_the_cutover(tmp_path):
    result = _read(
        tmp_path,
        line(created="2026-10-31 10:00", month=10, year=2026, name="a"),
        line(created="2026-11-10 10:00", month=11, year=2026, name="b"),
        line(created="2026-11-11 10:00", month=11, year=2026, name="c"),
        line(created="garbled", month=11, year=2026, name="d"),
        line(created="2026-12-01 10:00", month=12, year=2026, name="e"),
    )

    assert [x.customer_name for x in result.lines] == ["a", "b"]
    assert [r.row for r in result.rejected] == [4, 5, 6]


def test_identical_lines_stay_separate_and_keep_their_keys_when_the_file_grows(tmp_path):
    first = _read(tmp_path, line(), line())
    longer = _read(tmp_path, line(), line(), line())

    keys = [x.line_key for x in first.lines]
    assert len(set(keys)) == 2
    assert [x.line_key for x in longer.lines[:2]] == keys
    assert longer.lines[2].line_key not in keys


def test_lines_of_one_order_share_the_order_key(tmp_path):
    result = _read(tmp_path, line(item="A"), line(item="B"), line(name="Other"))

    a, b, c = result.lines
    assert a.order_key == b.order_key != c.order_key


def test_a_missing_required_column_rejects_the_file(tmp_path):
    path = write(tmp_path / "h.xlsx", [])
    from openpyxl import load_workbook

    workbook = load_workbook(path)
    workbook.active.delete_cols(HEADER.index("Customer paid") + 1)
    workbook.save(path)

    with pytest.raises(FileRejected, match="Customer paid"):
        read_history(path, DIVISIONS)
