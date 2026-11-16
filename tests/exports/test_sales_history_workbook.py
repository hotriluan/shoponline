from datetime import date, datetime
from io import BytesIO

from openpyxl import load_workbook

from shoponline.db.models import GeneratedFile, PlatformSetting, SalesHistoryExported
from shoponline.domain import states
from shoponline.exports.sales_history_workbook import (
    COLUMNS,
    CUSTOMER,
    DIVISION_MISSING,
    REPORT_NAME,
    build_history_workbook,
    collect_rows,
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
    later = setup.order(db, "B-2", datetime(2026, 11, 12, 9, 30))
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
    assert len(COLUMNS) == 17
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
    ]
    assert ws["H3"].value == '=E3&" "&B3' and ws["I3"].value == "=IF(H3=H2,0,1)"
    assert ws["O3"].value == "Propan - SƠN 100002000"
    assert ws["B4"].value == "2026-11-12 09:30"
    assert ws["J2"].number_format == "#,##0" and ws["K2"].number_format == "#,##0"


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


def test_blocked_for_platform_without_division(db):
    db.add(PlatformSetting(platform="SENDO", display_name="SENDO", sap_customer="1299999999"))
    db.flush()
    setup.report_name(db)
    setup.order(db, "SENDO-1", datetime(2026, 11, 11), platform="SENDO")
    assert [r.kind for r in _blocked(db).reasons] == [DIVISION_MISSING]


def test_blocked_order_does_not_hold_back_the_others(db):
    setup.report_name(db)
    good = setup.order(db, "GOOD", datetime(2026, 11, 11))
    setup.order(db, "BAD", datetime(2026, 11, 11, 1), name=None)
    result = collect_rows(db, UNTIL)
    assert result.order_ids == [good.id]
    assert [b.platform_order_id for b in result.blocked] == ["BAD"]


def test_file_name():
    assert history_file_name(date(2026, 11, 16)) == "SHOP ONLINE LỊCH SỬ 161126.xlsx"
