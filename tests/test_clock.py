from datetime import UTC, date, datetime

from shoponline.clock import today_vn


def test_vietnam_is_already_tomorrow_late_in_the_utc_day():
    assert today_vn(datetime(2026, 11, 13, 20, 0, tzinfo=UTC)) == date(2026, 11, 14)


def test_vietnam_is_still_today_early_in_the_utc_day():
    assert today_vn(datetime(2026, 11, 13, 2, 0, tzinfo=UTC)) == date(2026, 11, 13)


def test_naive_time_counts_as_utc():
    assert today_vn(datetime(2026, 11, 13, 17, 30)) == date(2026, 11, 14)


def test_without_argument_returns_a_date():
    assert isinstance(today_vn(), date)
