from datetime import datetime

from sqlalchemy import select

from shoponline.accounting import manual_settlement as manual
from shoponline.clock import today_vn
from shoponline.db.models import PlatformSettlement
from tests import sales_history_setup as setup

WHEN = datetime(2026, 11, 12, 9)
PAGE = "/settlements/lazada"


def _typed(db):
    db.expire_all()
    return {
        r.platform_order_id: r.amount
        for r in db.scalars(select(PlatformSettlement).where(PlatformSettlement.source == "manual"))
    }


def _day():
    return today_vn().isoformat()


def test_viewer_sees_pending_and_entered_orders_but_no_forms(db, login):
    setup.order(db, "LZ-1", WHEN, platform="LAZADA")
    setup.order(db, "LZ-2", WHEN, platform="LAZADA")
    manual.set_amount(db, "LZ-2", 5000, today_vn(), "admin")
    db.commit()

    page = login("viewer").get(PAGE).text

    assert "LZ-1" in page and "LZ-2" in page
    assert 'action="/settlements/lazada/set"' not in page
    assert "Dán nhiều dòng" not in page


def test_admin_sets_edits_and_removes_an_amount(db, login):
    setup.order(db, "LZ-1", WHEN, platform="LAZADA")
    db.commit()
    admin = login("admin")

    admin.post(f"{PAGE}/set", data={"order_id": "LZ-1", "amount": "90.000", "settled_on": _day()})
    assert _typed(db) == {"LZ-1": 90000}
    admin.post(f"{PAGE}/set", data={"order_id": "LZ-1", "amount": "80000", "settled_on": _day()})
    assert _typed(db) == {"LZ-1": 80000}
    admin.post(f"{PAGE}/remove", data={"order_id": "LZ-1"})
    assert _typed(db) == {}


def test_a_bad_amount_is_reported_and_nothing_is_saved(db, login):
    setup.order(db, "LZ-1", WHEN, platform="LAZADA")
    db.commit()
    admin = login("admin")

    page = admin.post(
        f"{PAGE}/set", data={"order_id": "LZ-1", "amount": "abc", "settled_on": _day()}
    ).text

    assert "không phải số nguyên" in page
    assert _typed(db) == {}


def test_autosave_saves_a_row_and_reports_errors_as_json(db, login):
    setup.order(db, "LZ-1", WHEN, platform="LAZADA")
    db.commit()
    admin = login("admin")
    headers = {"x-autosave": "1"}

    ok = admin.post(
        f"{PAGE}/set",
        data={"order_id": "LZ-1", "amount": "90.000", "settled_on": _day(), "month": ""},
        headers=headers,
    )
    assert ok.status_code == 200 and ok.json()["ok"] is True
    assert _typed(db) == {"LZ-1": 90000}

    bad = admin.post(
        f"{PAGE}/set",
        data={"order_id": "LZ-1", "amount": "abc", "settled_on": _day()},
        headers=headers,
    )
    assert bad.status_code == 422 and bad.json()["ok"] is False
    assert _typed(db) == {"LZ-1": 90000}


def test_pending_rows_autosave_and_have_no_save_form(db, login):
    setup.order(db, "LZ-1", WHEN, platform="LAZADA")
    db.commit()

    page = login("admin").get(PAGE).text

    assert 'data-autosave="/settlements/lazada/set"' in page


def test_viewer_cannot_write(db, login):
    setup.order(db, "LZ-1", WHEN, platform="LAZADA")
    db.commit()

    login("viewer").post(
        f"{PAGE}/set", data={"order_id": "LZ-1", "amount": "1", "settled_on": _day()}
    )

    assert _typed(db) == {}


def test_paste_previews_first_then_saves_only_the_good_lines(db, login):
    setup.order(db, "LZ-1", WHEN, platform="LAZADA")
    setup.order(db, "LZ-2", WHEN, platform="LAZADA")
    db.commit()
    admin = login("admin")
    paste = "LZ-1\t70.000\t15/11/2026\nLZ-2\t-5\t15/11/2026\nGHOST\t1\t15/11/2026"

    preview = admin.post(f"{PAGE}/preview", data={"paste": paste}).text

    assert _typed(db) == {}
    assert "lưu được" in preview and "Không có đơn Lazada GHOST" in preview
    assert "Lưu 1 dòng đúng" in preview

    admin.post(f"{PAGE}/save-paste", data={"paste": paste})

    assert _typed(db) == {"LZ-1": 70000}
