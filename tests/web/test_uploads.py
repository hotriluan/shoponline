from openpyxl import Workbook

from shoponline.config import Settings
from shoponline.web.uploads import save_generated


def test_two_saves_in_one_second_keep_separate_files(db, tmp_path):
    settings = Settings(database_url="unused", secret_key="s" * 40, data_dir=tmp_path / "data")
    first = save_generated(db, settings, Workbook(), "a.xlsx", "accounting_file", "t")
    second = save_generated(db, settings, Workbook(), "a.xlsx", "accounting_file", "t")

    assert first.id and second.id and first.id != second.id
    assert first.stored_path != second.stored_path
    assert len(list(settings.export_dir.glob("*.xlsx"))) == 2
