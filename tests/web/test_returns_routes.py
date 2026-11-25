from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from openpyxl import load_workbook
from sqlalchemy import func, select

from shoponline.db.models import (
    GeneratedFile,
    InvoiceItemText,
    SalesReturn,
    SapJob,
)
from shoponline.returns import numbering
from shoponline.sapjobs import queue
from shoponline.sapjobs.queue import SapTarget
from tests.returns import factory
from tests.sap_setup import configure_sap

TODAY = date(2026, 11, 25)
BUYER = "Nguyen Van A"
ADDRESS = "1 Duong Thu Nghiem, Quan Thu Nghiem"
PDF = {"pdf": ("hd.pdf", b"%PDF-1.4 stand-in", "application/pdf")}


@pytest.fixture(autouse=True)
def fixed_day(monkeypatch):
    monkeypatch.setattr("shoponline.returns.service.today_vn", lambda *a, **k: TODAY)
    monkeypatch.setattr("shoponline.web.routes.returns.today_vn", lambda *a, **k: TODAY)


@pytest.fixture
def order(db):
    numbering.set_start(db, 2026, 80, "t")
    return factory.delivered_order(db, texts=False, name=BUYER, address=ADDRESS)


@pytest.fixture
def read_pdf(monkeypatch, order):
    """Reading a PDF returns the invoice of the order; the bytes are not parsed in these tests."""
    calls = []

    def fake(data):
        calls.append(data)
        return factory.invoice_pdf(order)

    monkeypatch.setattr("shoponline.web.routes.returns.read_invoice_pdf", fake)
    return calls


def _form(order, **extra):
    data = {
        "reason": "CANCEL",
        "qty_10": "1",
        "buyer_name": BUYER,
        "buyer_address": ADDRESS,
    }
    data.update(extra)
    return data


def _issued(db):
    db.expire_all()
    return db.scalars(select(SalesReturn)).all()


def _fingerprint(html: str) -> str:
    marker = 'name="fingerprint" value="'
    start = html.index(marker) + len(marker)
    return html[start : html.index('"', start)]


def test_the_order_page_offers_the_return_to_admin_only(db, login, order):
    page = login("admin").get(f"/orders/{order.id}").text
    assert f'href="/orders/{order.id}/return"' in page and "Lập phiếu trả hàng" in page
    assert "Lập phiếu trả hàng" not in login("viewer").get(f"/orders/{order.id}").text


def test_an_order_without_an_invoice_offers_nothing(db, login):
    plain = factory.delivered_order(db, "NOINVOICE", texts=False)
    plain.do_number = "1910000999"
    db.flush()
    assert "Lập phiếu trả hàng" not in login("admin").get(f"/orders/{plain.id}").text


def test_a_missing_master_blocks_and_asks_for_the_pdf(db, login, order):
    page = login("admin").get(f"/orders/{order.id}/return").text
    assert "Chưa lập được phiếu" in page and "tải PDF hóa đơn" in page
    assert f'action="/orders/{order.id}/return/invoice-pdf"' in page
    assert "Phát hành phiếu" not in page
    assert BUYER in page  # the buyer comes filled from the customer data


def test_a_missing_zrsd003_money_offers_the_robot_read(db, login):
    numbering.set_start(db, 2026, 80, "t")
    old = factory.delivered_order(db, "OLDINVOICE", net=None, tax=None)
    page = login("admin").get(f"/orders/{old.id}/return").text
    assert "đọc lại zrsd003" in page
    assert f'action="/orders/{old.id}/return/read-zrsd003"' in page


def test_an_unnumbered_system_shows_the_cli_command(db, login):
    unnumbered = factory.delivered_order(db, "NONUMBER")
    page = login("admin").get(f"/orders/{unnumbered.id}/return").text
    assert "return-number start" in page


def test_the_full_flow_pdf_preview_issue_download_void_reissue(db, login, order, read_pdf):
    admin = login("admin")
    uploaded = admin.post(f"/orders/{order.id}/return/invoice-pdf", files=PDF)
    assert "Đã ghi tên trên hóa đơn: thêm 1 mã" in uploaded.text
    assert len(read_pdf) == 1 and read_pdf[0].startswith(b"%PDF-")
    assert db.get(InvoiceItemText, factory.MATERIAL).invoice_name == factory.INVOICE_NAME

    form = admin.get(f"/orders/{order.id}/return").text
    assert "Phát hành phiếu" in form and factory.SAP_NAME in form and "-111.111" in form
    fingerprint = _fingerprint(form)

    issued = admin.post(
        f"/orders/{order.id}/return",
        data=_form(order, fingerprint=fingerprint),
        follow_redirects=False,
    )
    assert issued.status_code == 303
    (created,) = _issued(db)
    assert issued.headers["location"] == f"/returns/{created.id}"
    assert created.doc_no == "080/11.2026 ALK-KH.STMĐT"

    detail = admin.get(f"/returns/{created.id}").text
    assert "080/11.2026" in detail and BUYER in detail and "Tải biên bản điều chỉnh" in detail
    docx = admin.get(f"/returns/{created.id}/docx")
    assert docx.status_code == 200
    assert "wordprocessingml" in docx.headers["content-type"]
    paragraphs = [p.text for p in Document(BytesIO(docx.content)).paragraphs]
    assert any("080/11.2026 ALK-KH.STMĐT" in text for text in paragraphs)
    xlsx = admin.get(f"/returns/{created.id}/xlsx")
    assert xlsx.status_code == 200 and "spreadsheetml" in xlsx.headers["content-type"]
    assert load_workbook(BytesIO(xlsx.content))["RRG ENGLISH"]["D14"].value == factory.SAP_NAME

    assert f"/returns/{created.id}" in admin.get(f"/orders/{order.id}").text
    assert admin.get(f"/orders/{order.id}/return").text.count("đã có phiếu") >= 1

    voided = admin.post(f"/returns/{created.id}/void", data={"reason": "Khách đổi ý"})
    assert "Đã hủy phiếu 080/11.2026" in voided.text and "Khách đổi ý" in voided.text
    again = admin.post(
        f"/orders/{order.id}/return",
        data=_form(order, fingerprint=_fingerprint(admin.get(f"/orders/{order.id}/return").text)),
    )
    assert "081/11.2026" in again.text


def test_a_second_issue_is_refused_and_leaves_one_return_and_two_files(db, login, order, read_pdf):
    admin = login("admin")
    admin.post(f"/orders/{order.id}/return/invoice-pdf", files=PDF)
    fingerprint = _fingerprint(admin.get(f"/orders/{order.id}/return").text)
    admin.post(f"/orders/{order.id}/return", data=_form(order, fingerprint=fingerprint))
    second = admin.post(f"/orders/{order.id}/return", data=_form(order, fingerprint=fingerprint))
    assert "Chưa lập được phiếu" in second.text and "đã có phiếu" in second.text
    assert len(_issued(db)) == 1
    assert db.scalar(select(func.count()).select_from(GeneratedFile)) == 2


def test_a_draft_that_changed_since_it_was_shown_is_refused(db, login, order, read_pdf):
    admin = login("admin")
    admin.post(f"/orders/{order.id}/return/invoice-pdf", files=PDF)
    fingerprint = _fingerprint(admin.get(f"/orders/{order.id}/return").text)
    db.get(InvoiceItemText, factory.MATERIAL).invoice_name = "TÊN ĐÃ ĐỔI"
    db.flush()
    resp = admin.post(f"/orders/{order.id}/return", data=_form(order, fingerprint=fingerprint))
    assert "xem lại bản nháp" in resp.text and _issued(db) == []


def test_a_partial_return_issues_only_the_chosen_quantity(db, login):
    numbering.set_start(db, 2026, 80, "t")
    two = factory.delivered_order(db, "TWOLINES", lines=((factory.MATERIAL, 2, 120000),))
    admin = login("admin")
    page = admin.post(f"/orders/{two.id}/return/preview", data=_form(two, qty_10="1")).text
    assert "trả một phần" in page
    admin.post(
        f"/orders/{two.id}/return",
        data=_form(two, qty_10="1", fingerprint=_fingerprint(page)),
    )
    (created,) = _issued(db)
    assert created.full_return is False and created.lines[0].return_qty == 1


def test_a_quantity_that_is_not_a_number_is_reported(db, login, order, read_pdf):
    admin = login("admin")
    admin.post(f"/orders/{order.id}/return/invoice-pdf", files=PDF)
    page = admin.post(f"/orders/{order.id}/return/preview", data=_form(order, qty_10="abc")).text
    assert "không phải số" in page


def test_a_pdf_of_another_order_is_refused_and_the_master_stays_empty(
    db, login, order, monkeypatch
):
    monkeypatch.setattr(
        "shoponline.web.routes.returns.read_invoice_pdf",
        lambda data: factory.invoice_pdf(order, po="SOMEONE-ELSE"),
    )
    resp = login("admin").post(f"/orders/{order.id}/return/invoice-pdf", files=PDF)
    assert "không khớp đơn này" in resp.text and "Số PO" in resp.text
    assert db.scalar(select(func.count()).select_from(InvoiceItemText)) == 0


def test_a_pdf_that_cannot_be_read_gives_a_message_not_an_error(db, login, order):
    resp = login("admin").post(
        f"/orders/{order.id}/return/invoice-pdf",
        files={"pdf": ("a.pdf", b"not a pdf at all", "application/pdf")},
    )
    assert resp.status_code == 200 and "không phải PDF" in resp.text


def test_a_pdf_over_the_size_limit_is_refused_before_it_is_read(db, login, order, read_pdf):
    big = {"pdf": ("big.pdf", b"%PDF-" + b"0" * (6 * 1024 * 1024), "application/pdf")}
    resp = login("admin").post(f"/orders/{order.id}/return/invoice-pdf", files=big)
    assert "quá 5 MB" in resp.text and read_pdf == []


def test_a_different_name_in_the_pdf_waits_for_confirmation(db, login, order, read_pdf):
    factory.invoice_text(db, invoice_name="TÊN CŨ", invoice_unit="LON 1 LT", source="manual")
    admin = login("admin")

    resp = admin.post(f"/orders/{order.id}/return/invoice-pdf", files=PDF)
    assert "Tên trong PDF khác tên đã lưu" in resp.text and "TÊN CŨ" in resp.text
    db.expire_all()
    assert db.get(InvoiceItemText, factory.MATERIAL).invoice_name == "TÊN CŨ"

    confirmed = admin.post(
        f"/orders/{order.id}/return/invoice-pdf", files=PDF, data={"confirm_overwrite": "1"}
    )
    assert "1 mã đổi tên" in confirmed.text
    db.expire_all()
    assert db.get(InvoiceItemText, factory.MATERIAL).invoice_name == factory.INVOICE_NAME


def test_the_zrsd003_read_is_queued_for_the_month_of_the_invoice(db, login):
    numbering.set_start(db, 2026, 80, "t")
    old = factory.delivered_order(db, "OLDINVOICE", net=None, tax=None)
    admin = login("admin")

    refused = admin.post(f"/orders/{old.id}/return/read-zrsd003")
    assert "Robot chưa được bật" in refused.text and db.scalar(select(func.count(SapJob.id))) == 0

    configure_sap(db, SapTarget("QAS", "300"))
    queued = admin.post(f"/orders/{old.id}/return/read-zrsd003")
    assert "Robot sẽ đọc zrsd003 từ 01/11/2026 đến 25/11/2026" in queued.text
    job = db.scalar(select(SapJob))
    assert job.kind == queue.READ_ZRSD003
    assert queue.payload_of(job) == {"date_from": "2026-11-01", "date_to": "2026-11-25"}
    assert "Đã có việc" in admin.post(f"/orders/{old.id}/return/read-zrsd003").text


def test_the_list_pages_and_searches(db, login, order, read_pdf):
    admin = login("admin")
    admin.post(f"/orders/{order.id}/return/invoice-pdf", files=PDF)
    admin.post(
        f"/orders/{order.id}/return",
        data=_form(order, fingerprint=_fingerprint(admin.get(f"/orders/{order.id}/return").text)),
    )
    page = admin.get("/returns").text
    assert "080/11.2026" in page and "261115BUCPCSEN" in page and "00008038" in page
    assert "-120.000" in page and "Đã lập" in page
    assert "080/11.2026" in admin.get("/returns?q=261115").text
    assert "080/11.2026" not in admin.get("/returns?q=nothing-like-this").text


def test_a_viewer_sees_the_list_but_neither_the_buyer_nor_the_files(db, login, order, read_pdf):
    admin = login("admin")
    admin.post(f"/orders/{order.id}/return/invoice-pdf", files=PDF)
    admin.post(
        f"/orders/{order.id}/return",
        data=_form(order, fingerprint=_fingerprint(admin.get(f"/orders/{order.id}/return").text)),
    )
    (created,) = _issued(db)
    viewer = login("viewer")

    assert "080/11.2026" in viewer.get("/returns").text
    detail = viewer.get(f"/returns/{created.id}").text
    assert "080/11.2026" in detail
    assert BUYER not in detail and ADDRESS not in detail and "Tải biên bản" not in detail

    for path in (f"/returns/{created.id}/docx", f"/returns/{created.id}/xlsx"):
        resp = viewer.get(path, follow_redirects=False)
        assert resp.status_code == 303 and not resp.content.startswith(b"PK")
    assert viewer.get(f"/orders/{order.id}/return", follow_redirects=False).status_code == 303


def test_a_viewer_cannot_issue_void_or_upload(db, login, order, read_pdf):
    viewer = login("viewer")
    viewer.post(f"/orders/{order.id}/return/invoice-pdf", files=PDF, follow_redirects=False)
    viewer.post(f"/orders/{order.id}/return", data=_form(order, fingerprint="x"))
    viewer.post(f"/orders/{order.id}/return/preview", data=_form(order))
    assert read_pdf == [] and _issued(db) == []
    assert db.scalar(select(func.count()).select_from(InvoiceItemText)) == 0

    admin = login("admin")
    admin.post(f"/orders/{order.id}/return/invoice-pdf", files=PDF)
    admin.post(
        f"/orders/{order.id}/return",
        data=_form(order, fingerprint=_fingerprint(admin.get(f"/orders/{order.id}/return").text)),
    )
    (created,) = _issued(db)
    viewer.post(f"/returns/{created.id}/void", data={"reason": "x"})
    db.expire_all()
    assert db.get(SalesReturn, created.id).status == "ISSUED"


def test_voiding_needs_a_reason(db, login, order, read_pdf):
    admin = login("admin")
    admin.post(f"/orders/{order.id}/return/invoice-pdf", files=PDF)
    admin.post(
        f"/orders/{order.id}/return",
        data=_form(order, fingerprint=_fingerprint(admin.get(f"/orders/{order.id}/return").text)),
    )
    (created,) = _issued(db)
    resp = admin.post(f"/returns/{created.id}/void", data={"reason": "  "})
    assert "Nhập lý do hủy phiếu" in resp.text
    db.expire_all()
    assert db.get(SalesReturn, created.id).status == "ISSUED"


def test_a_download_whose_file_is_gone_is_a_404_not_a_crash(db, login, order, read_pdf):
    admin = login("admin")
    admin.post(f"/orders/{order.id}/return/invoice-pdf", files=PDF)
    admin.post(
        f"/orders/{order.id}/return",
        data=_form(order, fingerprint=_fingerprint(admin.get(f"/orders/{order.id}/return").text)),
    )
    (created,) = _issued(db)
    Path(db.get(GeneratedFile, created.docx_file_id).stored_path).unlink()
    assert admin.get(f"/returns/{created.id}/docx").status_code == 404
