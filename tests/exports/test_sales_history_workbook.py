from datetime import date, datetime
from io import BytesIO

from openpyxl import load_workbook

from shoponline.db.models import GeneratedFile, SalesHistoryExported
from shoponline.domain import states
from shoponline.exports.sales_history_workbook import (
    ALL_SHEET,
    COLUMNS,
    CUSTOMER,
    REPORT_NAME,
    SETTLEMENT,
    TAX_INVOICE,
    Reason,
    build_history_workbook,
    collect_all_rows,
    collect_rows,
    history_all_file_name,
    history_draft_file_name,
    history_file_name,
)
from tests import sales_history_setup as setup

UNTIL = date(2026, 11, 16)


def _sheet(rows):
    buffer = BytesIO()
    build_history_workbook(rows).save(buffer)
    buffer.seek(0)
    return load_workbook(buffer)["sheet1"]


def _confirm(db, order):
    record = GeneratedFile(
        kind="sales_history", file_name="h", stored_path="h", sha256="0" * 64, created_by="t"
    )
    db.add(record)
    db.flush()
    db.add(
        SalesHistoryExported(sales_order_id=order.id, generated_file_id=record.id, confirmed_by="t")
    )
    db.flush()


def test_money_order_and_layout(db):
    setup.report_name(db)
    setup.report_name(db, "100002000")
    later = setup.order(db, "B-2", datetime(2026, 11, 12, 9, 30), invoice="0007914")
    first = setup.order(
        db,
        "A-1",
        datetime(2026, 11, 11, 8, 5),
        lines=((setup.MATERIAL, 2, 120000, 15000), ("100002000", 1, 99000, 0)),
    )

    result = collect_rows(db, UNTIL)

    assert result.blocked == []
    assert result.order_ids == [first.id, later.id]
    assert [(r.customer_paid, r.unit_price, r.quantity) for r in result.rows] == [
        (210000, 120000, 2),  # (120000 - 15000) x 2
        (99000, 99000, 1),
        (120000, 120000, 1),
    ]
    ws = _sheet(result.rows)
    assert len(COLUMNS) == 20 and COLUMNS[-3:] == ("Mã đơn", "Tax Invoice Doc.", "Tiền Vô")
    assert [c.value for c in ws[1]] == list(COLUMNS)
    assert ws.max_row == 4
    assert [c.value for c in ws[2]] == [
        "Shopee Bình Dương",
        "2026-11-11 08:05",
        11,
        2026,
        "Nguyễn Văn A",
        "******",
        "Hồ Chí Minh",
        '=E2&" "&B2',
        "=IF(H2=H1,0,1)",
        210000,
        120000,
        None,
        None,
        2,
        "Propan - SƠN 100001787",
        "0.8 lít",
        "Màu sắc:2004 Cánh gián",
        "A-1",
        "HDA-1",
        setup.SETTLED,
    ]
    assert ws["T3"].value is None  # only the first line of an order carries the money
    assert ws["H3"].value == '=E3&" "&B3' and ws["I3"].value == "=IF(H3=H2,0,1)"
    assert ws["O3"].value == "Propan - SƠN 100002000"
    assert ws["B4"].value == "2026-11-12 09:30"
    assert ws["J2"].number_format == "#,##0" and ws["K2"].number_format == "#,##0"
    assert ws["S4"].value == "0007914" and ws["S4"].number_format == "@"  # text, zeros kept
    assert ws["R4"].number_format == "@"
    assert ws["T2"].number_format == "#,##0" and ws["T4"].value == setup.SETTLED


def test_only_pending_delivered_orders_up_to_the_day(db):
    setup.report_name(db)
    setup.order(db, "READY", datetime(2026, 11, 11), status=states.READY)
    setup.order(db, "CANCELLED", datetime(2026, 11, 11), status=states.CANCELLED)
    _confirm(db, setup.order(db, "CONFIRMED", datetime(2026, 11, 11)))
    tomorrow = setup.order(db, "TOMORROW", datetime(2026, 11, 17, 0, 0))
    last_minute = setup.order(db, "LAST-MINUTE", datetime(2026, 11, 16, 23, 59))
    late_do = setup.order(db, "LATE-DO", datetime(2026, 10, 31, 22, 0))  # DO came in November

    result = collect_rows(db, UNTIL)

    assert result.order_ids == [late_do.id, last_minute.id]
    everything = collect_rows(db, date(2026, 11, 17)).order_ids
    assert everything == [late_do.id, last_minute.id, tomorrow.id]


def test_division_per_platform(db):
    setup.report_name(db)
    for n, platform in enumerate(("SHOPEE", "TIKTOK", "LAZADA")):
        setup.order(db, f"{platform}-1", datetime(2026, 11, 11, n), platform=platform)

    rows = collect_rows(db, UNTIL).rows

    assert [r.division for r in rows] == ["Shopee Bình Dương", "tiktok Bình Dương", "Lazada Mall"]


def test_division_follows_the_shop_of_the_order(db):
    setup.report_name(db)
    setup.order(db, "A-1", datetime(2026, 11, 11, 1), shop_code="SHOPEE_PGT")
    setup.order(db, "A-2", datetime(2026, 11, 11, 2))

    rows = collect_rows(db, UNTIL).rows

    assert [r.division for r in rows] == ["Shopee PGT", "Shopee Bình Dương"]


def _blocked(db):
    result = collect_rows(db, UNTIL)
    assert result.rows == [] and result.order_ids == []
    (blocked,) = result.blocked
    return blocked


def test_blocked_without_customer_name(db):
    setup.report_name(db)
    setup.order(db, "NO-NAME", datetime(2026, 11, 11), name="  ")
    blocked = _blocked(db)
    assert blocked.platform_order_id == "NO-NAME"
    assert [(r.kind, r.text) for r in blocked.reasons] == [(CUSTOMER, "Thiếu tên khách")]


def test_blocked_without_customer_row(db):
    setup.report_name(db)
    setup.order(db, "NO-ROW", datetime(2026, 11, 11), customer=False)
    assert [r.text for r in _blocked(db).reasons] == [
        "Thiếu tên khách",
        "Địa chỉ không ra tỉnh/thành",
    ]


def test_blocked_when_address_has_no_province(db):
    setup.report_name(db)
    setup.order(db, "NO-CITY", datetime(2026, 11, 11), address="Phường Một, Tỉnh Thử, Việt Nam")
    assert [(r.kind, r.text) for r in _blocked(db).reasons] == [
        (CUSTOMER, "Địa chỉ không ra tỉnh/thành")
    ]


def test_blocked_without_report_name(db):
    setup.report_name(db)
    setup.order(
        db,
        "NO-REPORT",
        datetime(2026, 11, 11),
        lines=((setup.MATERIAL, 1, 1000, 0), ("100009999", 1, 1000, 0), ("100009999", 2, 1, 0)),
    )
    assert [(r.kind, r.text) for r in _blocked(db).reasons] == [
        (REPORT_NAME, "Mã 100009999 chưa có tên báo cáo")
    ]


def test_blocked_order_does_not_hold_back_the_others(db):
    setup.report_name(db)
    good = setup.order(db, "GOOD", datetime(2026, 11, 11))
    setup.order(db, "BAD", datetime(2026, 11, 11, 1), name=None)
    result = collect_rows(db, UNTIL)
    assert result.order_ids == [good.id]
    assert [b.platform_order_id for b in result.blocked] == ["BAD"]


def test_blocked_until_the_do_has_a_tax_invoice(db):
    setup.report_name(db)
    waiting = setup.order(db, "WAIT", datetime(2026, 11, 11), invoice=None)
    blocked = _blocked(db)
    assert [(r.kind, r.text) for r in blocked.reasons] == [
        (TAX_INVOICE, f"DO {waiting.do_number} chưa có Tax Invoice Doc.")
    ]
    setup.tax_invoice(db, waiting.do_number, "7914")
    result = collect_rows(db, UNTIL)
    assert result.blocked == [] and [r.tax_invoice_doc for r in result.rows] == ["7914"]


def test_tax_invoice_reason_adds_to_the_others(db):
    setup.order(db, "BOTH", datetime(2026, 11, 11), name=None, invoice=None)
    assert [r.kind for r in _blocked(db).reasons] == [CUSTOMER, REPORT_NAME, TAX_INVOICE]


def test_file_name():
    assert history_file_name(date(2026, 11, 16)) == "SHOP ONLINE LỊCH SỬ 161126.xlsx"


def test_settlement_is_the_sum_of_the_order_rows_including_zero_and_negative(db):
    setup.report_name(db)
    setup.order(db, "TT-1", datetime(2026, 11, 11), platform="TIKTOK", settlement=None)
    setup.paid(db, "TIKTOK", "TT-1", 100000, key="a")
    setup.paid(db, "TIKTOK", "TT-1", -2700, key="b")
    setup.order(db, "TT-ZERO", datetime(2026, 11, 11, 1), platform="TIKTOK", settlement=0)
    setup.order(db, "SP-OUT", datetime(2026, 11, 11, 2), settlement=-2700)

    result = collect_rows(db, UNTIL)

    assert result.blocked == []
    assert [(r.platform_order_id, r.settlement) for r in result.rows] == [
        ("TT-1", 97300),
        ("TT-ZERO", 0),
        ("SP-OUT", -2700),
    ]


def test_only_the_first_line_of_an_order_carries_the_settlement(db):
    setup.report_name(db)
    setup.order(db, "A-1", datetime(2026, 11, 11), lines=((setup.MATERIAL, 1, 1, 0),) * 3)

    rows = collect_rows(db, UNTIL).rows

    assert [r.settlement for r in rows] == [setup.SETTLED, None, None]


def test_shopee_and_tiktok_wait_for_settlement_but_lazada_does_not(db):
    setup.report_name(db)
    setup.order(db, "SP-1", datetime(2026, 11, 11), settlement=None)
    setup.order(db, "TT-1", datetime(2026, 11, 11, 1), platform="TIKTOK", settlement=None)
    setup.order(db, "LZ-1", datetime(2026, 11, 11, 2), platform="LAZADA")

    result = collect_rows(db, UNTIL)

    assert [r.platform_order_id for r in result.rows] == ["LZ-1"]
    assert result.rows[0].settlement is None
    assert [b.platform_order_id for b in result.blocked] == ["SP-1", "TT-1"]
    assert all(b.reasons == (Reason(SETTLEMENT, "Chưa có tiền vô"),) for b in result.blocked)


def test_lazada_money_typed_in_shows_in_the_file_and_missing_money_never_blocks(db):
    from shoponline.accounting import manual_settlement

    setup.report_name(db)
    setup.order(db, "LZ-1", datetime(2026, 11, 11, 2), platform="LAZADA")
    setup.order(db, "LZ-2", datetime(2026, 11, 11, 3), platform="LAZADA")
    manual_settlement.set_amount(db, "LZ-1", 87500, date(2026, 11, 15), "admin", date(2026, 11, 16))

    result = collect_rows(db, UNTIL)

    assert result.blocked == []
    assert {r.platform_order_id: r.settlement for r in result.rows} == {"LZ-1": 87500, "LZ-2": None}


def test_a_settlement_of_another_platform_does_not_count(db):
    setup.report_name(db)
    setup.order(db, "SAME-ID", datetime(2026, 11, 11), platform="SHOPEE", settlement=None)
    setup.paid(db, "TIKTOK", "SAME-ID", 5)

    result = collect_rows(db, UNTIL)

    assert result.rows == [] and len(result.blocked) == 1


def test_settlement_reason_adds_to_the_others(db):
    setup.report_name(db)
    setup.order(db, "X", datetime(2026, 11, 11), name=None, settlement=None)

    (blocked,) = collect_rows(db, UNTIL).blocked

    assert {r.kind for r in blocked.reasons} == {CUSTOMER, SETTLEMENT}


def _draft_orders(db):
    setup.report_name(db)
    setup.order(db, "FULL", datetime(2026, 11, 11, 1))
    setup.order(db, "NO-INV", datetime(2026, 11, 11, 2), invoice=None)
    setup.order(db, "NO-PAID", datetime(2026, 11, 11, 3), settlement=None)
    setup.order(db, "NO-NAME", datetime(2026, 11, 11, 4), lines=(("999", 1, 1, 0),))


def test_a_draft_adds_the_orders_that_only_wait_for_an_invoice_or_settlement(db):
    _draft_orders(db)

    result = collect_rows(db, UNTIL, draft=True)

    assert [(r.platform_order_id, r.status) for r in result.rows] == [
        ("FULL", ""),
        ("NO-INV", "Chờ hóa đơn"),
        ("NO-PAID", "Chờ tiền vô"),
    ]
    by_id = {r.platform_order_id: r for r in result.rows}
    assert by_id["NO-INV"].tax_invoice_doc is None and by_id["NO-INV"].settlement == setup.SETTLED
    assert by_id["NO-PAID"].settlement is None and by_id["NO-PAID"].tax_invoice_doc
    assert [b.platform_order_id for b in result.blocked] == ["NO-NAME"]
    assert len(result.order_ids) == 3


def test_without_the_draft_flag_the_waiting_orders_stay_blocked(db):
    _draft_orders(db)

    result = collect_rows(db, UNTIL)

    assert [r.platform_order_id for r in result.rows] == ["FULL"]
    assert [b.platform_order_id for b in result.blocked] == ["NO-INV", "NO-PAID", "NO-NAME"]


def test_a_draft_order_waiting_for_both_lists_both(db):
    setup.report_name(db)
    setup.order(db, "BOTH", datetime(2026, 11, 11), invoice=None, settlement=None)

    (row,) = collect_rows(db, UNTIL, draft=True).rows

    assert row.status == "Chờ hóa đơn; Chờ tiền vô"


def test_the_draft_workbook_has_a_status_column_and_the_real_one_does_not(db):
    _draft_orders(db)
    rows = collect_rows(db, UNTIL, draft=True).rows
    buffer = BytesIO()
    build_history_workbook(rows, draft=True).save(buffer)
    book = load_workbook(buffer)
    draft = book["NHÁP - KHÔNG DÁN"]

    assert draft.max_column == 21 and draft["U1"].value == "Trạng thái"
    assert [draft.cell(r, 21).value for r in (2, 3, 4)] == [None, "Chờ hóa đơn", "Chờ tiền vô"]
    assert draft["S3"].value is None and draft["T4"].value is None
    assert "sheet1" not in book.sheetnames  # a draft is never mistaken for the real sheet
    assert _sheet(rows).max_column == len(COLUMNS) == 20


def test_draft_file_name():
    assert history_draft_file_name(date(2026, 11, 16)) == "NHÁP SHOP ONLINE LỊCH SỬ 161126.xlsx"


def test_a_customer_name_that_looks_like_a_formula_stays_text(db):
    setup.report_name(db)
    for n, name in enumerate(("=1+1", "+84 Lan", "-Minh", "@SUM(A1)", "Nguyễn Văn A")):
        setup.order(db, f"F-{n}", datetime(2026, 11, 11, 8, n), name=name)
    rows = collect_rows(db, UNTIL).rows

    ws = _sheet(rows)

    names = [ws.cell(r, 5) for r in range(2, ws.max_row + 1)]
    assert [c.value for c in names] == ["=1+1", "+84 Lan", "-Minh", "@SUM(A1)", "Nguyễn Văn A"]
    assert {c.data_type for c in names} == {"s"}
    assert ws["H2"].data_type == "f" and ws["I3"].data_type == "f"  # the file's own formulas


FROM, TO = date(2026, 11, 10), date(2026, 11, 12)


def _all_orders(db):
    setup.report_name(db)
    confirmed = setup.order(db, "CONF", datetime(2026, 11, 10, 9))
    _confirm(db, confirmed)
    setup.order(db, "FULL", datetime(2026, 11, 10, 10))
    setup.order(db, "WAIT", datetime(2026, 11, 11, 9), invoice=None, settlement=None)
    setup.order(
        db,
        "READY",
        datetime(2026, 11, 11, 10),
        status=states.READY,
        lines=((None, 1, 50000, 0),),
        settlement=None,
    )
    setup.order(db, "CANCEL", datetime(2026, 11, 12, 9), status=states.CANCELLED)
    setup.order(db, "NONAME", datetime(2026, 11, 12, 23, 59), name=None, customer=False)
    setup.order(db, "OUT", datetime(2026, 11, 13, 0, 0))
    setup.order(db, "BEFORE", datetime(2026, 11, 9, 23, 59))


def _all_sheet(db, first=FROM, last=TO):
    rows = collect_all_rows(db, first, last)
    buffer = BytesIO()
    build_history_workbook(rows, draft=True, title=ALL_SHEET).save(buffer)
    buffer.seek(0)
    return load_workbook(buffer)[ALL_SHEET]


def test_all_orders_in_the_range_in_any_status_with_their_state(db):
    _all_orders(db)

    ws = _all_sheet(db)

    by_id = {ws.cell(r, 18).value: r for r in range(2, ws.max_row + 1)}
    assert list(by_id) == ["CONF", "FULL", "WAIT", "READY", "CANCEL", "NONAME"]
    status = {k: ws.cell(r, 21).value for k, r in by_id.items()}
    assert status == {
        "CONF": "Đã có DO; Đã xác nhận dán",
        "FULL": "Đã có DO; Chưa xác nhận",
        "WAIT": "Đã có DO; Chờ hóa đơn; Chờ tiền vô; Chưa xác nhận",
        "READY": "Sẵn sàng; Chưa xác nhận",
        "CANCEL": "Đã hủy; Chưa xác nhận",
        "NONAME": "Đã có DO; Chưa xác nhận",
    }
    conf = by_id["CONF"]
    assert ws.cell(conf, 19).value == "HDCONF" and ws.cell(conf, 20).value == setup.SETTLED
    assert ws.cell(by_id["WAIT"], 19).value is None and ws.cell(by_id["WAIT"], 20).value is None
    assert ws.cell(by_id["CANCEL"], 20).value == setup.SETTLED  # money shows in any status


def test_all_orders_leaves_missing_data_empty_or_takes_the_platforms(db):
    _all_orders(db)

    ws = _all_sheet(db)

    by_id = {ws.cell(r, 18).value: r for r in range(2, ws.max_row + 1)}
    noname = by_id["NONAME"]
    assert not ws.cell(noname, 5).value and not ws.cell(noname, 7).value
    ready = by_id["READY"]  # no material: the platform's own product and variation
    assert [ws.cell(ready, c).value for c in (15, 16, 17)] == ["P", None, "V1"]


def test_all_orders_has_one_row_per_line_with_money_and_status_on_the_first(db):
    setup.report_name(db)
    setup.order(
        db,
        "MULTI",
        datetime(2026, 11, 10, 9),
        lines=((setup.MATERIAL, 1, 100, 0), (setup.MATERIAL, 2, 200, 0)),
    )

    ws = _all_sheet(db)

    assert ws.max_row == 3
    assert [ws.cell(r, 20).value for r in (2, 3)] == [setup.SETTLED, None]
    assert [ws.cell(r, 21).value for r in (2, 3)] == ["Đã có DO; Chưa xác nhận", None]
    assert [ws.cell(r, 19).value for r in (2, 3)] == ["HDMULTI", "HDMULTI"]


def test_all_orders_includes_both_end_days_and_one_day_ranges(db):
    _all_orders(db)

    one_day = collect_all_rows(db, date(2026, 11, 12), date(2026, 11, 12))
    next_day = collect_all_rows(db, date(2026, 11, 13), date(2026, 11, 13))

    assert {r.platform_order_id for r in one_day} == {"CANCEL", "NONAME"}
    assert [r.platform_order_id for r in next_day] == ["OUT"]
    assert collect_all_rows(db, date(2026, 12, 1), date(2026, 12, 31)) == []


def test_all_orders_workbook_layout_and_file_name(db):
    _all_orders(db)

    ws = _all_sheet(db)

    assert ws.title == ALL_SHEET and ws.max_column == 21 and ws["U1"].value == "Trạng thái"
    assert _sheet(collect_rows(db, UNTIL).rows).max_column == len(COLUMNS) == 20
    assert history_all_file_name(FROM, TO) == "TẤT CẢ ĐƠN SHOP ONLINE 101126-121126.xlsx"
