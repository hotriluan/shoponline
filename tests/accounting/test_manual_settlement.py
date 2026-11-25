from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from shoponline.accounting import manual_settlement as manual
from shoponline.db.models import EventLog, ImportBatch, PlatformSettlement
from tests import sales_history_setup as setup

TODAY = date(2026, 11, 25)


def _lazada(db, order_id="LZ-1", ordered=datetime(2026, 11, 12, 9), **kwargs):
    return setup.order(db, order_id, ordered, platform="LAZADA", **kwargs)


def _rows(db):
    db.expire_all()
    return list(db.scalars(select(PlatformSettlement).where(PlatformSettlement.source == "manual")))


def test_set_edit_and_remove_keep_one_row_per_order_and_log_old_and_new(db):
    _lazada(db)

    manual.set_amount(db, "LZ-1", 90000, date(2026, 11, 20), "admin", TODAY)
    manual.set_amount(db, "LZ-1", 85000, date(2026, 11, 21), "admin", TODAY)

    (row,) = _rows(db)
    assert (row.amount, row.line_key, row.import_batch_id, row.entered_by) == (
        85000,
        "manual:LZ-1",
        None,
        "admin",
    )
    assert row.settled_at == datetime(2026, 11, 21)
    assert manual.remove(db, "LZ-1", "admin") is True
    assert manual.remove(db, "LZ-1", "admin") is False
    assert _rows(db) == []
    events = list(
        db.scalars(
            select(EventLog).where(EventLog.kind.like("settlement_manual%")).order_by(EventLog.id)
        )
    )
    assert [e.kind for e in events] == [
        "settlement_manual_set",
        "settlement_manual_set",
        "settlement_manual_removed",
    ]
    assert '"old": 90000, "new": 85000' in events[1].detail


@pytest.mark.parametrize(
    ("order_id", "amount", "day", "message"),
    [
        ("NOPE", 1, date(2026, 11, 20), "Không có đơn Lazada"),
        ("LZ-1", -1, date(2026, 11, 20), "không được âm"),
        ("LZ-1", 1, date(2026, 11, 26), "tương lai"),
        ("LZ-1", 1, date(2026, 11, 11), "trước ngày đặt đơn"),
    ],
)
def test_values_that_cannot_be_saved_are_refused_with_a_reason(db, order_id, amount, day, message):
    _lazada(db)

    with pytest.raises(manual.SettlementError, match=message):
        manual.set_amount(db, order_id, amount, day, "admin", TODAY)

    assert _rows(db) == []


def test_only_lazada_orders_are_accepted(db):
    setup.order(db, "SP-1", datetime(2026, 11, 12))

    with pytest.raises(manual.SettlementError, match="Không có đơn Lazada"):
        manual.set_amount(db, "SP-1", 1, date(2026, 11, 20), "admin", TODAY)


def test_zero_is_a_valid_amount(db):
    _lazada(db)

    manual.set_amount(db, "LZ-1", 0, date(2026, 11, 20), "admin", TODAY)

    assert [r.amount for r in _rows(db)] == [0]


def test_pending_orders_have_a_do_and_no_money_and_filter_by_month(db):
    _lazada(db, "LZ-OLD", datetime(2026, 11, 12))
    _lazada(db, "LZ-DEC", datetime(2026, 12, 1))
    _lazada(db, "LZ-PAID", datetime(2026, 11, 13))
    _lazada(db, "LZ-NODO", datetime(2026, 11, 14), status="READY")
    setup.order(db, "SP-1", datetime(2026, 11, 12))
    manual.set_amount(db, "LZ-PAID", 5, date(2026, 11, 20), "admin", TODAY)

    assert [o.platform_order_id for o in manual.pending_orders(db)] == ["LZ-OLD", "LZ-DEC"]
    assert [o.platform_order_id for o in manual.pending_orders(db, date(2026, 11, 20))] == [
        "LZ-OLD"
    ]
    assert [o.platform_order_id for o in manual.pending_orders(db, date(2026, 12, 1))] == ["LZ-DEC"]


def test_parse_paste_reads_each_line_and_names_the_bad_ones():
    text = (
        "LZ-1\t1.234.567\t05/11/2026\n\nLZ-2\tabc\t05/11/2026\n"
        "LZ-3\t10\n LZ-4 \t 9 000 \t 6/11/2026 "
    )

    lines = manual.parse_paste(text)

    assert [(x.line_no, x.order_id, x.amount, x.settled_on, bool(x.error)) for x in lines] == [
        (1, "LZ-1", 1234567, date(2026, 11, 5), False),
        (3, "LZ-2", None, None, True),
        (4, "LZ-3", None, None, True),
        (5, "LZ-4", 9000, date(2026, 11, 6), False),
    ]


def test_a_settlement_file_row_does_not_touch_typed_rows(db):
    _lazada(db)
    manual.set_amount(db, "LZ-1", 5000, date(2026, 11, 20), "admin", TODAY)
    setup.order(db, "SP-1", datetime(2026, 11, 12), settlement=None)
    setup.paid(db, "SHOPEE", "SP-1", 1000)

    assert [r.platform_order_id for r in _rows(db)] == ["LZ-1"]


def test_the_database_refuses_a_row_that_is_neither_a_file_row_nor_a_typed_row(db):
    batch = ImportBatch(
        kind="settlement", file_name="s", sha256="0" * 64, stored_path="s", imported_by="t"
    )
    db.add(batch)
    db.flush()
    db.add(
        PlatformSettlement(
            platform="LAZADA",
            platform_order_id="X",
            line_key="k",
            amount=1,
            settled_at=datetime(2026, 11, 1),
            source="manual",
            import_batch_id=batch.id,
        )
    )

    with pytest.raises(IntegrityError):
        db.flush()
