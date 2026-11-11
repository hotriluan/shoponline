from datetime import date
from types import SimpleNamespace

from shoponline.domain.expected_value import expected_so_value
from shoponline.domain.gi_date import suggest_gi_date
from shoponline.domain.order import default_address
from shoponline.domain.sku_mapping import normalize_key


def test_gi_date_monday_gives_tuesday():
    assert suggest_gi_date(date(2026, 11, 9)) == date(2026, 11, 10)


def test_gi_date_friday_gives_monday():
    assert suggest_gi_date(date(2026, 11, 6)) == date(2026, 11, 9)


def test_gi_date_friday_before_month_end_keeps_d():
    # Monday would be 02/11, another month
    assert suggest_gi_date(date(2026, 10, 30)) == date(2026, 10, 30)


def test_gi_date_last_day_of_year_keeps_d():
    assert suggest_gi_date(date(2026, 12, 31)) == date(2026, 12, 31)


def test_gi_date_saturday_gives_monday():
    assert suggest_gi_date(date(2026, 11, 7)) == date(2026, 11, 9)


def test_normalize_key_whitespace_and_unicode_form():
    nfd = "Cánh gián - 2004,0.8 lít".encode().decode()
    import unicodedata

    decomposed = unicodedata.normalize("NFD", nfd)
    assert normalize_key(decomposed) == normalize_key("Cánh  gián - 2004,0.8 lít ")


def test_normalize_key_keeps_space_after_comma_difference():
    # Shopee and TikTok spell the same color differently; mapping is per platform.
    assert normalize_key("Cánh gián - 2004,0.8 lít") != normalize_key("Cánh gián - 2004, 0.8 lít")


def test_expected_value_subtracts_unit_subsidy():
    items = [
        SimpleNamespace(quantity=3, unit_price=120000, unit_subsidy=0),
        SimpleNamespace(quantity=2, unit_price=100000, unit_subsidy=15000),
    ]
    assert expected_so_value(items) == 360000 + 170000


def test_default_address_skips_blank_parts():
    assert default_address("Phường Bỉm Sơn", "Tỉnh Thanh Hóa") == (
        "Phường Bỉm Sơn, Tỉnh Thanh Hóa, Việt Nam"
    )
    assert default_address("", "Gia Lai") == "Gia Lai, Việt Nam"
