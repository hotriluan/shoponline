import pytest

from shoponline.config import ConfigError, load_settings

GOOD = {
    "SHOPONLINE_DATABASE_URL": "postgresql+psycopg://u:p@localhost/x",
    "SHOPONLINE_SECRET_KEY": "k" * 32,
    "SHOPONLINE_DATA_DIR": "C:/data",
}


def test_reads_required_and_defaults():
    settings = load_settings(dict(GOOD))
    assert settings.web_host == "127.0.0.1"
    assert settings.web_port == 8750
    assert settings.upload_dir.name == "uploads"


def test_names_every_missing_variable():
    with pytest.raises(ConfigError) as err:
        load_settings({"SHOPONLINE_SECRET_KEY": "k" * 32})
    assert "SHOPONLINE_DATABASE_URL" in str(err.value)
    assert "SHOPONLINE_DATA_DIR" in str(err.value)


def test_rejects_short_secret():
    with pytest.raises(ConfigError, match="32"):
        load_settings({**GOOD, "SHOPONLINE_SECRET_KEY": "short"})


def test_rejects_non_numeric_port():
    with pytest.raises(ConfigError, match="PORT"):
        load_settings({**GOOD, "SHOPONLINE_WEB_PORT": "abc"})


def test_invoice_symbol_defaults_and_follows_the_billing_year():
    from datetime import date

    settings = load_settings(dict(GOOD))
    assert settings.invoice_symbol(date(2026, 11, 17)) == "1C26TAL"
    assert settings.invoice_symbol(date(2027, 1, 2)) == "1C27TAL"
    custom = load_settings({**GOOD, "SHOPONLINE_INVOICE_SYMBOL_PATTERN": "2K{yy}XYZ"})
    assert custom.invoice_symbol(date(2026, 11, 17)) == "2K26XYZ"


@pytest.mark.parametrize(
    "pattern", ["1C26TAL", "1C{year}TAL", "1C{yy", "1C {yy}", "A{yy}" + "B" * 20]
)
def test_rejects_a_broken_invoice_symbol_pattern(pattern):
    with pytest.raises(ConfigError, match="INVOICE_SYMBOL"):
        load_settings({**GOOD, "SHOPONLINE_INVOICE_SYMBOL_PATTERN": pattern})
