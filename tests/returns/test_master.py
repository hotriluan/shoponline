from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from shoponline.config import Settings
from shoponline.db.models import EventLog, InvoiceItemText
from shoponline.importers.excel_table import FileRejected
from shoponline.importers.invoice_pdf import InvoicePdf, PdfLine
from shoponline.returns.master import learn_from_pdf, missing_materials
from tests.returns import factory

SETTINGS = Settings(database_url="x", secret_key="k" * 32, data_dir=Path("."))
NAME = "SƠN V-09 REDDISH CLAY 2004 VN"
UNIT = "LON 0.8 LT"


def pdf_for(order, **changes) -> InvoicePdf:
    pdf = InvoicePdf(
        symbol="1C26TAL",
        number="00008038",
        invoice_date=date(2026, 11, 17),
        delivery=order.do_number,
        po=order.platform_order_id,
        net=111111,
        vat_rate=8,
        tax=8889,
        total=120000,
        lines=(PdfLine(1, NAME, UNIT, Decimal(1), 111111),),
    )
    return replace(pdf, **changes)


def order(db, **kwargs):
    return factory.delivered_order(db, texts=False, **kwargs)


def stored(db):
    return {r.material_number: r for r in db.scalars(select(InvoiceItemText))}


def test_a_matching_pdf_fills_the_master(db):
    created = order(db)
    assert missing_materials(db, created) == [factory.MATERIAL]
    result = learn_from_pdf(db, created, pdf_for(created), "admin", SETTINGS)
    assert result.added == [factory.MATERIAL] and not result.needs_confirmation
    row = stored(db)[factory.MATERIAL]
    assert (row.invoice_name, row.invoice_unit, row.stock_unit) == (NAME, UNIT, "PC")
    assert (row.source, row.updated_by) == ("00008038", "admin")
    assert missing_materials(db, created) == []


def test_the_log_names_materials_but_not_the_buyer(db):
    created = order(db, name="Nguyen Van A", address="1 Duong Thu Nghiem")
    learn_from_pdf(db, created, pdf_for(created), "admin", SETTINGS)
    event = db.scalar(select(EventLog).where(EventLog.kind == "invoice_text_learned"))
    assert factory.MATERIAL in event.detail and NAME in event.detail
    assert "Nguyen Van A" not in event.detail and "Duong Thu Nghiem" not in event.detail


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"delivery": "1910000000"}, "Số DO"),
        ({"po": "OTHER"}, "Số PO"),
        ({"number": "00008039"}, "Số hóa đơn"),
        ({"symbol": "1C25TAL"}, "Ký hiệu"),
        ({"net": 100000}, "Tiền trên PDF"),
        ({"lines": ()}, "0 dòng hàng"),
        (
            {"lines": (PdfLine(1, NAME, UNIT, Decimal(2), 111111),)},
            "số lượng PDF",
        ),
        (
            {"lines": (PdfLine(1, NAME, UNIT, Decimal(1), 100000),)},
            "thành tiền PDF",
        ),
    ],
)
def test_a_pdf_that_is_not_this_invoice_is_refused_and_writes_nothing(db, change, fragment):
    created = order(db)
    with pytest.raises(FileRejected) as err:
        learn_from_pdf(db, created, pdf_for(created, **change), "admin", SETTINGS)
    assert fragment in str(err.value)
    assert stored(db) == {}


def test_a_pdf_with_more_lines_than_the_order_is_refused(db):
    created = order(db)
    two = (PdfLine(1, NAME, UNIT, Decimal(1), 111111), PdfLine(2, "X", UNIT, Decimal(1), 0))
    with pytest.raises(FileRejected, match="2 dòng hàng"):
        learn_from_pdf(db, created, pdf_for(created, lines=two), "admin", SETTINGS)


def test_an_invoice_without_zrsd003_money_is_refused(db):
    created = order(db, net=None, tax=None)
    with pytest.raises(FileRejected, match="đọc lại zrsd003"):
        learn_from_pdf(db, created, pdf_for(created), "admin", SETTINGS)
    assert stored(db) == {}


def test_an_order_without_an_invoice_is_refused(db):
    created = order(db)
    created.do_number = "1910000999"
    with pytest.raises(FileRejected, match="chưa có hóa đơn"):
        learn_from_pdf(db, created, pdf_for(created), "admin", SETTINGS)


@pytest.mark.parametrize("source", ["manual", "00007000"])
def test_a_different_stored_name_is_not_overwritten_without_confirmation(db, source):
    created = order(db)
    factory.invoice_text(db, invoice_name="TÊN CŨ", invoice_unit="LON 1 LT", source=source)
    result = learn_from_pdf(db, created, pdf_for(created), "admin", SETTINGS)
    assert result.needs_confirmation
    (change,) = result.differing
    assert (change.old_name, change.new_name) == ("TÊN CŨ", NAME)
    assert stored(db)[factory.MATERIAL].invoice_name == "TÊN CŨ"


def test_confirmation_overwrites_even_a_manual_row(db):
    created = order(db)
    factory.invoice_text(db, invoice_name="TÊN CŨ", invoice_unit="LON 1 LT", source="manual")
    result = learn_from_pdf(
        db, created, pdf_for(created), "admin", SETTINGS, confirm_overwrite=True
    )
    assert result.overwritten and not result.needs_confirmation
    row = stored(db)[factory.MATERIAL]
    assert (row.invoice_name, row.invoice_unit, row.source) == (NAME, UNIT, "00008038")


def test_an_identical_stored_text_is_left_alone(db):
    created = order(db)
    factory.invoice_text(db, source="manual")
    result = learn_from_pdf(db, created, pdf_for(created), "admin", SETTINGS)
    assert result.unchanged == [factory.MATERIAL] and not result.added
    assert stored(db)[factory.MATERIAL].source == "manual"


def test_a_two_line_order_fills_both_materials(db):
    created = order(
        db,
        lines=((factory.MATERIAL, 1, 60000), ("100002222", 1, 60000)),
        net=111111,
        tax=8889,
    )
    pdf = pdf_for(
        created,
        lines=(
            PdfLine(1, NAME, UNIT, Decimal(1), 55555),
            PdfLine(2, "SƠN LÓT", "LON 5 LT", Decimal(1), 55556),
        ),
    )
    result = learn_from_pdf(db, created, pdf, "admin", SETTINGS)
    assert sorted(result.added) == [factory.MATERIAL, "100002222"]
    assert stored(db)["100002222"].invoice_name == "SƠN LÓT"


def test_a_kit_order_is_read_on_its_parent_line_only(db):
    created = order(
        db,
        lines=((factory.MATERIAL, 1, 120000),),
        so_items=(
            (10, factory.MATERIAL, 1, 120000),
            (11, "100003333", 1, 0),
            (12, "100004444", 1, 0),
        ),
    )
    assert missing_materials(db, created) == [factory.MATERIAL]
    learn_from_pdf(db, created, pdf_for(created), "admin", SETTINGS)
    assert set(stored(db)) == {factory.MATERIAL}
