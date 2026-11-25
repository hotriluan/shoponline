from decimal import Decimal
from types import SimpleNamespace

import pytest

from shoponline.returns.amounts import (
    Blocked,
    InvoiceLine,
    InvoiceLines,
    invoice_lines,
    returned,
)
from shoponline.returns.money import format_vnd, round_half_up


def item(no, material="100001787", qty=1, total=120000):
    return SimpleNamespace(
        item_no=no, material_number=material, quantity=Decimal(qty), net_value_incl=total
    )


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [(5, 2, 3), (25, 10, 3), (7, 2, 4), (4, 2, 2), (1, 3, 0), (2, 3, 1), (-5, 2, -3), (0, 7, 0)],
)
def test_round_half_up_rounds_halves_away_from_zero(numerator, denominator, expected):
    assert round_half_up(numerator, denominator) == expected


def test_round_half_up_takes_a_decimal_quantity():
    assert round_half_up(100001, Decimal("2")) == 50001
    assert round_half_up(10, Decimal("4")) == 3


def test_format_vnd_groups_with_dots_and_keeps_the_sign():
    assert [format_vnd(v) for v in (0, 999, 111111, -8889, 1234567)] == [
        "0",
        "999",
        "111.111",
        "-8.889",
        "1.234.567",
    ]


def test_one_line_invoice_matches_the_zrsd003_totals():
    result = invoice_lines([item(10)], 111111, 8889)
    assert not isinstance(result, Blocked)
    assert (result.vat_rate, result.net, result.tax) == (8, 111111, 8889)
    (line,) = result.lines
    assert (line.net, line.unit_price, line.quantity) == (111111, 111111, 1)


@pytest.mark.parametrize(("rate", "total"), [(10, 110000), (5, 105000), (8, 108000)])
def test_other_vat_rates(rate, total):
    result = invoice_lines([item(10, total=total)], 100000, total - 100000)
    assert result.vat_rate == rate and result.lines[0].net == 100000


def test_partial_return_rounds_halves_up_not_to_even():
    line = InvoiceLine(10, "100001787", Decimal(2), 108109, 100101, 50051)
    invoice = InvoiceLines((line,), vat_rate=8, net=100101, tax=8008)
    figures = returned(invoice, {10: 1})
    assert figures.lines[0].amount == 50051  # 50050.5 goes up; round() would give 50050
    tiny = InvoiceLines((InvoiceLine(10, "m", Decimal(1), 0, 10, 10),), vat_rate=5, net=10, tax=1)
    half = InvoiceLines((InvoiceLine(10, "m", Decimal(2), 0, 20, 10),), vat_rate=5, net=20, tax=1)
    assert returned(half, {10: 1}).tax == 1  # 10 * 5% = 0.5 goes up; round() would give 0
    assert returned(tiny, {10: 1}).full_return is True


def test_rounding_gap_between_lines_goes_to_the_largest_line():
    items = [item(10, total=60000), item(20, total=60000)]
    result = invoice_lines(items, 111111, 8889)
    assert sorted(line.net for line in result.lines) == [55555, 55556]
    assert sum(line.net for line in result.lines) == 111111


def test_unit_price_is_rounded_but_the_line_amount_stays():
    result = invoice_lines([item(10, qty=3, total=108000)], 100000, 8000)
    (line,) = result.lines
    assert line.unit_price == 33333 and line.net == 100000


def test_sub_lines_of_a_kit_are_ignored():
    items = [item(10, total=120000), item(11, "200", total=0), item(12, "300", total=0)]
    result = invoice_lines(items, 111111, 8889)
    assert [line.so_item_no for line in result.lines] == [10]


def test_blocks_when_the_order_total_differs_from_the_invoice():
    result = invoice_lines([item(10, total=130000)], 111111, 8889)
    assert isinstance(result, Blocked) and "SO đã đổi" in result.reason


def test_blocks_a_vat_rate_that_is_not_a_whole_percent():
    result = invoice_lines([item(10, total=120000)], 111111, 8000)
    assert isinstance(result, Blocked) and "phần trăm nguyên" in result.reason


def test_blocks_without_lines_or_with_a_zero_net():
    assert isinstance(invoice_lines([], 111111, 8889), Blocked)
    assert isinstance(invoice_lines([item(11)], 111111, 8889), Blocked)
    assert isinstance(invoice_lines([item(10)], 0, 0), Blocked)


def test_a_line_without_quantity_blocks():
    assert isinstance(invoice_lines([item(10, qty=0)], 111111, 8889), Blocked)


def _two_lines():
    return invoice_lines(
        [item(10, qty=2, total=60000), item(20, "200", qty=1, total=60000)], 111111, 8889
    )


def test_full_return_is_the_zrsd003_totals():
    figures = returned(_two_lines(), {10: 2, 20: 1})
    assert (figures.full_return, figures.net, figures.tax) == (True, 111111, 8889)


def test_partial_return_has_only_the_chosen_amounts():
    invoice = _two_lines()
    figures = returned(invoice, {10: 1})
    expected = round_half_up(invoice.lines[0].net * 1, Decimal(2))
    assert figures.full_return is False
    assert [(line.so_item_no, line.amount) for line in figures.lines] == [(10, expected), (20, 0)]
    assert figures.net == expected
    assert figures.tax == round_half_up(expected * 8, 100)


@pytest.mark.parametrize("quantities", [{}, {10: 0}, {10: 3}, {10: -1}, {99: 1}])
def test_a_return_needs_a_sensible_quantity(quantities):
    assert isinstance(returned(_two_lines(), quantities), Blocked)
