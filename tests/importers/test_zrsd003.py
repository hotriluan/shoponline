from datetime import date

import pytest
from sqlalchemy import func, select

from shoponline.db.models import ImportBatch, SapTaxInvoice
from shoponline.importers.excel_table import FileRejected
from shoponline.importers.sap_reports import read_zrsd003
from shoponline.reconcile.report_ingest import ingest_zrsd003
from tests.fixtures.build_fixtures import ZRSD003_HEADERS, zrsd003_file, zrsd003_row

OTHER_CUSTOMER = "1200000042"


def _record(path):
    return ImportBatch(
        kind="zrsd003",
        platform=None,
        file_name=path.name,
        sha256="0" * 64,
        stored_path=str(path),
        imported_by="t",
    )


def test_reads_invoices_as_text_and_skips_other_billing_types(tmp_path):
    path = zrsd003_file(
        tmp_path / "z3.xlsx",
        [
            zrsd003_row("1910061168", "7914", "1200001146"),
            zrsd003_row("1910061170", "0012", billing_type="ZBA2"),
            zrsd003_row("", ""),
        ],
    )
    rows = read_zrsd003(path)
    assert [(r.delivery, r.tax_invoice_doc, r.bill_to, r.billing_date) for r in rows] == [
        ("1910061168", "7914", "1200001146", date(2026, 11, 13))
    ]


@pytest.mark.parametrize("missing", ["OD Doc.", "Tax Invoice Doc.", "Bill-to", "Billing Date"])
def test_rejects_a_file_without_a_required_column(tmp_path, missing):
    headers = [h for h in ZRSD003_HEADERS if h != missing]
    path = zrsd003_file(tmp_path / "z3.xlsx", [zrsd003_row("1", "2")], headers=headers)
    with pytest.raises(FileRejected, match=missing.rstrip(".")):
        read_zrsd003(path)


def test_rejects_an_invoice_row_without_a_number_or_a_file_without_invoices(tmp_path):
    path = zrsd003_file(tmp_path / "a.xlsx", [zrsd003_row("1910000001", "")])
    with pytest.raises(FileRejected, match="không nhập gì"):
        read_zrsd003(path)
    path = zrsd003_file(tmp_path / "b.xlsx", [zrsd003_row("1910000001", "1", billing_type="ZS1")])
    with pytest.raises(FileRejected, match="không có hóa đơn nào"):
        read_zrsd003(path)


def test_ingest_keeps_platform_customers_only_and_upserts_by_delivery(db, tmp_path):
    first = zrsd003_file(
        tmp_path / "first.xlsx",
        [
            zrsd003_row("1910061168", "7914", "1200001146"),
            zrsd003_row("1910061169", "7903", "1200001145"),
            zrsd003_row("1910061200", "7950", "1200001118"),
            zrsd003_row("1910061300", "7999", OTHER_CUSTOMER),
        ],
    )
    result = ingest_zrsd003(db, _record(first), "t")
    assert (result.kept, result.skipped_other_customers, result.new, result.updated) == (3, 1, 3, 0)
    assert db.get(SapTaxInvoice, "1910061300") is None

    again = zrsd003_file(
        tmp_path / "again.xlsx",
        [
            zrsd003_row("1910061168", "8000", "1200001146"),
            zrsd003_row("1910061169", "7903", "1200001145"),
        ],
    )
    record = _record(again)
    result = ingest_zrsd003(db, record, "t")
    assert (result.kept, result.new, result.updated) == (2, 0, 2)
    assert (record.new_count, record.updated_count) == (0, 2)
    assert db.scalar(select(func.count()).select_from(SapTaxInvoice)) == 3
    db.expire_all()
    invoice = db.get(SapTaxInvoice, "1910061168")
    assert invoice.tax_invoice_doc == "8000" and invoice.import_batch_id == record.id


def test_ingest_writes_nothing_when_the_file_is_rejected(db, tmp_path):
    path = zrsd003_file(tmp_path / "bad.xlsx", [zrsd003_row("1910061168", "")])
    with pytest.raises(FileRejected):
        ingest_zrsd003(db, _record(path), "t")
    assert db.scalar(select(func.count()).select_from(SapTaxInvoice)) == 0


def test_a_broken_row_of_a_customer_outside_the_platforms_does_not_reject_the_file(db, tmp_path):
    path = zrsd003_file(
        tmp_path / "mixed.xlsx",
        [
            zrsd003_row("1910000001", "INV-1"),
            zrsd003_row("1910000002", "", bill_to=OTHER_CUSTOMER),  # no invoice number
            zrsd003_row("1910000003", "INV-3", bill_to=OTHER_CUSTOMER),
        ],
    )

    result = ingest_zrsd003(db, _record(path), "t")

    assert result.kept == 1 and result.skipped_other_customers == 1
    assert db.scalar(select(SapTaxInvoice.delivery)) == "1910000001"


def test_a_broken_row_of_a_platform_customer_still_rejects_the_file(db, tmp_path):
    path = zrsd003_file(
        tmp_path / "bad.xlsx",
        [zrsd003_row("1910000001", "INV-1"), zrsd003_row("1910000002", "")],
    )

    with pytest.raises(FileRejected, match="không nhập gì"):
        ingest_zrsd003(db, _record(path), "t")

    assert db.scalar(select(func.count()).select_from(SapTaxInvoice)) == 0
