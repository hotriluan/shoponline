from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select

from shoponline.db.models import (
    CustomerInfo,
    EventLog,
    GeneratedFile,
    InvoiceItemText,
    SalesReturn,
    SalesReturnLine,
    SkuMapping,
)
from shoponline.domain import states
from shoponline.returns import service
from shoponline.returns.amounts import Blocked
from shoponline.returns.service import Buyer, ReturnBlocked, StaleReturn
from tests.returns import factory


def preview(db, settings, order, kind="CANCEL", selection=None, buyer=None):
    return service.build_preview(db, settings, order.id, kind, selection, buyer)


def issue(db, settings, order, kind="CANCEL", selection=None, buyer=None, actor="admin"):
    buyer = buyer or Buyer()
    draft = service.build_preview(db, settings, order.id, kind, selection, buyer)
    assert not isinstance(draft, Blocked), draft
    return service.issue(db, settings, order.id, kind, selection, buyer, draft.fingerprint, actor)


def exports_dir(settings) -> list[Path]:
    return sorted(settings.export_dir.glob("*")) if settings.export_dir.exists() else []


def test_a_whole_order_previews_the_zrsd003_figures(db, settings, numbered):
    order = factory.delivered_order(db)
    draft = preview(db, settings, order)
    assert not isinstance(draft, Blocked)
    assert (draft.invoice_net, draft.invoice_tax, draft.vat_rate) == (111111, 8889, 8)
    assert (draft.returned_net, draft.returned_tax, draft.full_return) == (111111, 8889, True)
    assert (draft.invoice_symbol, draft.billing_date) == ("1C26TAL", date(2026, 11, 17))
    (line,) = draft.lines
    assert (line.invoice_name, line.invoice_unit, line.sap_name) == (
        factory.INVOICE_NAME,
        factory.INVOICE_UNIT,
        factory.SAP_NAME,
    )
    assert (line.invoice_qty, line.return_qty, line.amount_returned) == (1, 1, 111111)
    assert (draft.buyer_name, draft.platform_name) == ("Nguyen Van A", "Shopee")


def test_the_symbol_follows_the_billing_year(db, settings, numbered):
    order = factory.delivered_order(db, billing_date=date(2027, 1, 4))
    assert preview(db, settings, order).invoice_symbol == "1C27TAL"


def test_a_partial_return_of_a_two_line_order_keeps_every_line_in_the_snapshot(
    db, settings, numbered
):
    order = factory.delivered_order(
        db, lines=((factory.MATERIAL, 1, 60000), ("100002222", 2, 60000))
    )
    created = issue(db, settings, order, "RETURN", selection={20: 1})
    assert created.full_return is False and created.reason_kind == "RETURN"
    lines = {line.so_item_no: line for line in created.lines}
    assert lines[10].return_qty == 0 and lines[10].amount_returned == 0
    assert lines[20].return_qty == 1 and lines[20].invoice_qty == 2
    assert created.returned_net == lines[20].amount_returned
    assert created.invoice_net == 111111 and len(created.lines) == 2


@pytest.mark.parametrize(
    ("change", "fragment", "code"),
    [
        ("not_delivered", "đã giao", None),
        ("no_invoice", "chưa có hóa đơn", "missing_money"),
        ("no_money", "đọc lại zrsd003", "missing_money"),
        ("no_so", "dòng SO", None),
        ("so_changed", "SO đã đổi", None),
        ("no_texts", "tải PDF hóa đơn", "missing_texts"),
        ("no_buyer", "tên người mua", None),
        ("no_address", "địa chỉ người mua", None),
    ],
)
def test_each_missing_piece_blocks_with_its_own_reason(
    db, settings, numbered, change, fragment, code
):
    order = factory.delivered_order(
        db,
        texts=change != "no_texts",
        net=None if change == "no_money" else 111111,
        tax=None if change == "no_money" else 8889,
        name=None if change == "no_buyer" else "Nguyen Van A",
        address=None if change == "no_address" else "1 Duong Thu Nghiem",
        lines=((factory.MATERIAL, 1, 130000 if change == "so_changed" else 120000),),
    )
    if change == "not_delivered":
        order.status = states.CANCELLED
    if change == "no_invoice":
        order.do_number = "1910000999"
    if change == "no_so":
        order.so_number = "SO404"
    blocked = preview(db, settings, order)
    assert isinstance(blocked, Blocked) and fragment in blocked.reason
    assert (code in blocked.codes) if code else not blocked.codes


def test_the_buyer_typed_on_the_form_replaces_the_missing_customer(db, settings, numbered):
    order = factory.delivered_order(db, name=None, address=None)
    assert isinstance(preview(db, settings, order), Blocked)
    typed = preview(db, settings, order, buyer=Buyer("Tran B", "2 Duong Khac"))
    assert (typed.buyer_name, typed.buyer_address) == ("Tran B", "2 Duong Khac")


def test_a_deleted_customer_row_is_no_obstacle_when_the_buyer_is_typed(db, settings, numbered):
    order = factory.delivered_order(db)
    db.query(CustomerInfo).delete()
    assert isinstance(preview(db, settings, order), Blocked)
    assert not isinstance(preview(db, settings, order, buyer=Buyer("A", "B")), Blocked)


def test_an_unnumbered_system_blocks_with_the_numbering_code(db, settings, issue_day):
    order = factory.delivered_order(db)
    blocked = preview(db, settings, order)
    assert isinstance(blocked, Blocked) and blocked.codes == {"numbering"}


def test_the_sap_name_falls_back_to_the_platform_mapping_and_must_be_unique(db, settings, numbered):
    order = factory.delivered_order(db)
    for item in order.items:
        item.sap_name = None
    blocked = preview(db, settings, order)
    assert "chưa có tên SAP" in blocked.reason

    def mapping(sap_name, key):
        db.add(
            SkuMapping(
                platform="SHOPEE",
                product_key=key,
                variation_key="v",
                product_name="P",
                variation_name="V",
                material_number=factory.MATERIAL,
                sap_name=sap_name,
                updated_by="t",
            )
        )
        db.flush()

    mapping("TÊN SAP A", "a")
    assert preview(db, settings, order).lines[0].sap_name == "TÊN SAP A"
    mapping("TÊN SAP B", "b")
    assert "nhiều tên SAP" in preview(db, settings, order).reason


def test_issue_stores_the_snapshot_and_two_files(db, settings, numbered):
    order = factory.delivered_order(db)
    created = issue(db, settings, order)
    assert created.doc_no == "080/11.2026 ALK-KH.STMĐT" and created.status == "ISSUED"
    assert (created.doc_year, created.doc_seq) == (2026, 80)
    assert (created.invoice_symbol, created.tax_invoice_doc, created.delivery) == (
        "1C26TAL",
        "8038",
        order.do_number,
    )
    assert (created.returned_net, created.returned_tax) == (111111, 8889)
    assert (created.buyer_name, created.platform_name) == ("Nguyen Van A", "Shopee")
    docx, xlsx = (db.get(GeneratedFile, i) for i in (created.docx_file_id, created.xlsx_file_id))
    assert (docx.kind, xlsx.kind) == ("invoice_adjustment", "return_request")
    assert docx.file_name == "BBDC 080-11.2026 261115BUCPCSEN.docx"
    assert xlsx.file_name == "RRG 080-11.2026 261115BUCPCSEN.xlsx"
    assert Path(docx.stored_path).suffix == ".docx" and Path(xlsx.stored_path).suffix == ".xlsx"
    assert Path(docx.stored_path).stat().st_size > 0 and Path(xlsx.stored_path).stat().st_size > 0
    assert db.scalar(select(func.count()).select_from(SalesReturnLine)) == 1


def test_the_event_log_names_the_return_but_not_the_buyer(db, settings, numbered):
    order = factory.delivered_order(db, name="Nguyen Van A", address="1 Duong Thu Nghiem")
    issue(db, settings, order)
    for event in db.scalars(select(EventLog).where(EventLog.kind == "sales_return_issued")):
        assert "080/11.2026" in event.detail
        assert "Nguyen Van A" not in event.detail and "Duong Thu Nghiem" not in event.detail


def test_a_second_issue_is_refused_and_leaves_no_stray_file(db, settings, numbered):
    order = factory.delivered_order(db)
    issue(db, settings, order)
    before = exports_dir(settings)
    draft = preview(db, settings, order)
    assert isinstance(draft, Blocked) and "đã có phiếu 080/11.2026" in draft.reason
    with pytest.raises(ReturnBlocked):
        service.issue(db, settings, order.id, "CANCEL", None, Buyer(), "x" * 16, "admin")
    assert exports_dir(settings) == before
    assert db.scalar(select(func.count()).select_from(SalesReturn)) == 1


def test_the_unique_index_stops_a_double_click_before_any_file_is_written(
    db, settings, numbered, monkeypatch
):
    order = factory.delivered_order(db)
    stale = preview(db, settings, order)  # what the second click still holds
    issue(db, settings, order)
    before = exports_dir(settings)
    # In a true race the second request's own check has not seen the first return yet.
    monkeypatch.setattr(service, "build_preview", lambda *a, **k: stale)
    with pytest.raises(ReturnBlocked, match="đã có phiếu"):
        service.issue(db, settings, order.id, "CANCEL", None, Buyer(), stale.fingerprint, "admin")
    assert exports_dir(settings) == before


def test_a_changed_draft_is_refused(db, settings, numbered):
    order = factory.delivered_order(db)
    draft = preview(db, settings, order)
    db.get(InvoiceItemText, factory.MATERIAL).invoice_name = "TÊN ĐÃ ĐỔI"
    db.flush()
    with pytest.raises(StaleReturn, match="xem lại bản nháp"):
        service.issue(db, settings, order.id, "CANCEL", None, Buyer(), draft.fingerprint, "admin")
    assert not exports_dir(settings)


def test_voiding_keeps_the_number_and_lets_the_order_be_returned_again(db, settings, numbered):
    order = factory.delivered_order(db)
    first = issue(db, settings, order)
    with pytest.raises(ValueError, match="lý do"):
        service.void(db, first.id, "  ", "admin")
    service.void(db, first.id, "Khách đổi ý", "admin")
    db.refresh(first)
    assert (first.status, first.void_reason, first.voided_by) == ("VOID", "Khách đổi ý", "admin")
    assert first.doc_no == "080/11.2026 ALK-KH.STMĐT"
    assert all(Path(db.get(GeneratedFile, i).stored_path).exists() for i in (first.docx_file_id,))
    second = issue(db, settings, order)
    assert second.doc_no == "081/11.2026 ALK-KH.STMĐT"
    with pytest.raises(ValueError, match="đã hủy"):
        service.void(db, first.id, "again", "admin")
    kinds = {e.kind for e in db.scalars(select(EventLog))}
    assert {"sales_return_issued", "sales_return_voided"} <= kinds


def test_a_kit_is_returned_on_its_parent_line_only(db, settings, numbered):
    order = factory.delivered_order(
        db,
        lines=((factory.MATERIAL, 1, 120000),),
        so_items=(
            (10, factory.MATERIAL, 1, 120000),
            (11, "100003333", 1, 0),
            (12, "100004444", 1, 0),
        ),
    )
    created = issue(db, settings, order)
    assert [line.so_item_no for line in created.lines] == [10]


def test_an_unnumbered_issue_raises_a_blocked_error(db, settings, issue_day):
    order = factory.delivered_order(db)
    with pytest.raises(ReturnBlocked) as err:
        service.issue(db, settings, order.id, "CANCEL", None, Buyer(), "x", "admin")
    assert "numbering" in err.value.blocked.codes


def test_a_failure_while_rendering_removes_the_files_already_written(
    db, settings, numbered, monkeypatch
):
    order = factory.delivered_order(db)

    def broken(_):
        raise RuntimeError("render failed")

    monkeypatch.setattr(service.return_request_workbook, "render", broken)
    with pytest.raises(RuntimeError, match="render failed"):
        issue(db, settings, order)
    assert exports_dir(settings) == []
