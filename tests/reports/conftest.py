import pytest

from shoponline.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url="unused", secret_key="s" * 40, data_dir=tmp_path / "data")
