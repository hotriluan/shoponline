import pytest
from sqlalchemy import func, select

from shoponline.db.models import ImportBatch, PlatformSettlement
from shoponline.importers.excel_table import FileRejected
from shoponline.reconcile.report_ingest import ingest_settlement
from tests.fixtures.build_fixtures import (
    lazada_settlement_file,
    shopee_settlement_file,
    shopee_settlement_row,
    tiktok_settlement_file,
    tiktok_settlement_row,
)


def _record(path):
    return ImportBatch(
        kind="settlement",
        platform=None,
        file_name=path.name,
        sha256="0" * 64,
        stored_path=str(path),
        imported_by="t",
    )


def _rows(db, platform):
    db.expire_all()
    return db.scalar(
        select(func.count())
        .select_from(PlatformSettlement)
        .where(PlatformSettlement.platform == platform)
    )


def test_ingest_sets_the_platform_and_counts_new_rows(db, tmp_path):
    path = shopee_settlement_file(
        tmp_path / "s.xlsx",
        [shopee_settlement_row("A1", 100.0), shopee_settlement_row("A2", -2700.0)],
    )
    record = _record(path)
    result = ingest_settlement(db, record, "t")
    assert record.platform == "SHOPEE"
    assert (result.kept, result.orders, result.new, result.updated, result.unchanged) == (
        2,
        2,
        2,
        0,
        0,
    )
    assert _rows(db, "SHOPEE") == 2


def test_reading_the_same_file_again_changes_nothing(db, tmp_path):
    path = shopee_settlement_file(
        tmp_path / "s.xlsx",
        [shopee_settlement_row("A1", 100.0), shopee_settlement_row("A1", 100.0)],
    )
    ingest_settlement(db, _record(path), "t")
    again = ingest_settlement(db, _record(path), "t")
    assert (again.new, again.updated, again.unchanged) == (0, 0, 2)
    assert _rows(db, "SHOPEE") == 2
    assert db.scalar(select(func.sum(PlatformSettlement.amount))) == 200


def test_overlapping_shopee_files_do_not_add_a_transaction_twice(db, tmp_path):
    first = shopee_settlement_file(
        tmp_path / "a.xlsx",
        [shopee_settlement_row("A1", 100.0), shopee_settlement_row("A2", 50.0)],
    )
    second = shopee_settlement_file(
        tmp_path / "b.xlsx",
        [shopee_settlement_row("A2", 50.0), shopee_settlement_row("A3", 7.0)],
    )
    ingest_settlement(db, _record(first), "t")
    result = ingest_settlement(db, _record(second), "t")
    assert (result.new, result.unchanged) == (1, 1)
    assert _rows(db, "SHOPEE") == 3


def test_tiktok_changed_amount_counts_as_updated(db, tmp_path):
    first = tiktok_settlement_file(tmp_path / "a.xlsx", [tiktok_settlement_row("111", "100")])
    second = tiktok_settlement_file(tmp_path / "b.xlsx", [tiktok_settlement_row("111", "90")])
    ingest_settlement(db, _record(first), "t")
    record = _record(second)
    result = ingest_settlement(db, record, "t")
    assert (result.new, result.updated, result.unchanged) == (0, 1, 0)
    assert (record.new_count, record.updated_count, record.unchanged_count) == (0, 1, 0)
    assert db.scalar(select(PlatformSettlement.amount)) == 90
    assert db.scalar(select(PlatformSettlement.import_batch_id)) == record.id


def test_a_rejected_file_writes_nothing(db, tmp_path):
    with pytest.raises(FileRejected):
        ingest_settlement(db, _record(lazada_settlement_file(tmp_path / "l.xlsx")), "t")
    assert db.scalar(select(func.count()).select_from(PlatformSettlement)) == 0
