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
