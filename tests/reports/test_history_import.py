from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from shoponline.db.models import BackupRun, EventLog, HistorySaleLine, ImportBatch
from shoponline.maintenance import retention
from shoponline.reports import history_import
from tests.history_setup import line, write


def _file(tmp_path, *rows, name="h.xlsx"):
    return write(tmp_path / name, list(rows))


def _backup(db, finished_at, status="ok", kind="db"):
    db.add(
        BackupRun(
            kind=kind,
            source="manual",
            actor="t",
            file_name="b.7z",
            local_status=status,
            finished_at=finished_at,
        )
    )
    db.flush()


def _count(db):
    return db.scalar(select(func.count()).select_from(HistorySaleLine))


def test_a_dry_run_reports_without_writing(db, tmp_path):
    path = _file(tmp_path, line(), line(name="B", division="Sendo"))

    result = history_import.plan(db, path)

    assert len(result.new_lines) == 1 and len(result.rejected) == 1
    assert _count(db) == 0


def test_apply_stores_the_lines_one_batch_and_one_event(db, settings, tmp_path):
    path = _file(tmp_path, line(), line(name="B", division="tiktok Bình Dương", paid=5))

    result = history_import.apply(db, settings, path, "tester", skip_backup_check=True)

    assert len(result.new_lines) == 2 and _count(db) == 2
    batch = db.scalar(select(ImportBatch).where(ImportBatch.kind == "history_sales"))
    assert batch.new_count == 2 and "history" in batch.stored_path
    event = db.scalar(select(EventLog).where(EventLog.kind == "history_imported"))
    assert '"backup_check_skipped": true' in event.detail


def test_loading_the_same_or_a_longer_file_again_adds_only_new_lines(db, settings, tmp_path):
    first = _file(tmp_path, line(), line(), name="a.xlsx")
    longer = _file(tmp_path, line(), line(), line(), line(name="B"), name="b.xlsx")

    history_import.apply(db, settings, first, "t", skip_backup_check=True)
    again = history_import.apply(db, settings, first, "t", skip_backup_check=True)
    grown = history_import.apply(db, settings, longer, "t", skip_backup_check=True)

    assert len(again.new_lines) == 0 and again.existing == 2
    assert len(grown.new_lines) == 2 and grown.existing == 2
    assert _count(db) == 4


def test_apply_refuses_without_a_recent_backup(db, settings, tmp_path):
    path = _file(tmp_path, line())
    now = datetime.now(UTC)
    _backup(db, now - timedelta(hours=3))
    _backup(db, now, status="failed")

    with pytest.raises(history_import.BackupMissing):
        history_import.apply(db, settings, path, "t")

    assert _count(db) == 0


def test_apply_goes_ahead_after_a_recent_backup(db, settings, tmp_path):
    path = _file(tmp_path, line())
    _backup(db, datetime.now(UTC) - timedelta(minutes=30))

    history_import.apply(db, settings, path, "t")

    assert _count(db) == 1
    event = db.scalar(select(EventLog).where(EventLog.kind == "history_imported"))
    assert "backup_check_skipped" not in event.detail


def test_unresolved_place_names_are_counted_and_old_provinces_are_not(db, tmp_path):
    path = _file(
        tmp_path,
        line(city="Kiên Giang"),
        line(city="Huyện Châu Thành", name="B"),
        line(city="Huyện Châu Thành", name="C"),
    )

    result = history_import.plan(db, path)

    assert dict(result.unresolved_cities) == {"Huyện Châu Thành": 2}


def test_totals_are_by_year_and_shop(db, tmp_path):
    path = _file(
        tmp_path,
        line(paid=100),
        line(paid=50, name="B"),
        line(paid=7, year=2024, month=3, created="2024-03-02 10:00"),
    )

    result = history_import.plan(db, path)

    assert result.totals == {(2025, "SHOPEE_BD"): 150, (2024, "SHOPEE_BD"): 7}


def test_the_stored_history_file_is_kept_by_the_retention_rules(db, settings, tmp_path):
    path = _file(tmp_path, line())
    history_import.apply(db, settings, path, "t", skip_backup_check=True)
    stored = db.scalar(select(ImportBatch.stored_path).where(ImportBatch.kind == "history_sales"))

    assert retention.Path(stored).resolve() in retention.kept_files(db, settings)
