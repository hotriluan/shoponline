from datetime import date, datetime

from shoponline.db.models import AccountingRun, OrderBatch, SalesOrder
from shoponline.domain import states


def _batch(db, confirmed=False):
    batch = OrderBatch(
        platform="SHOPEE",
        processing_date=date(2026, 11, 20),
        gi_date=date(2026, 11, 20),
        confirmed_at=datetime(2026, 11, 20, 9, 0) if confirmed else None,
        confirmed_by="admin" if confirmed else None,
    )
    db.add(batch)
    db.flush()
    return batch


def _order(db, batch, order_id, status):
    db.add(
        SalesOrder(
            platform="SHOPEE",
            platform_order_id=order_id,
            order_batch_id=batch.id,
            ordered_at=datetime(2026, 11, 20, 8, 0),
            status=status,
        )
    )


def test_today_requires_login(app):
    from fastapi.testclient import TestClient

    resp = TestClient(app).get("/", follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == "/login"


def test_login_lands_on_today(app):
    from fastapi.testclient import TestClient

    resp = TestClient(app).post(
        "/login", data={"username": "admin", "password": "admin-password"}, follow_redirects=False
    )
    assert resp.headers["location"] == "/"


def test_today_shows_counts_and_hides_write_buttons_from_viewer(app, db, login):
    batch = _batch(db)
    _order(db, batch, "A1", states.MAPPING_ERROR)
    _order(db, batch, "A2", states.MAPPING_ERROR)
    _order(db, batch, "A3", states.READY)
    db.add(AccountingRun(status="OPEN", created_by="admin"))
    db.commit()

    admin = login("admin").get("/")
    assert admin.status_code == 200
    assert 'class="n">2</span><span class="l">đơn thiếu ánh xạ' in admin.text
    assert "lô chưa xác nhận" in admin.text
    assert "Đợt mở #" in admin.text

    viewer = login("viewer").get("/")
    assert viewer.status_code == 200
    assert "Xuất file gửi kế toán" not in viewer.text
    assert 'action="/accounting/runs"' not in viewer.text


def test_today_quiet_when_nothing_to_do(app, login):
    html = login("viewer").get("/").text
    assert html.count("Không có việc") >= 4


def test_sidebar_marks_only_the_open_page(app, login):
    html = login("admin").get("/robot/sap-connection").text
    assert html.count('aria-current="page"') == 1
    assert 'href="/robot/sap-connection" aria-current="page"' in html
    robot = login("admin").get("/robot").text
    assert 'href="/robot" aria-current="page"' in robot
    assert 'href="/robot/sap-connection" aria-current="page"' not in robot


def test_static_css_is_served_without_login(app):
    from fastapi.testclient import TestClient

    assert TestClient(app).get("/static/app.css").status_code == 200


def test_templates_carry_no_inline_style_attributes():
    from pathlib import Path

    import shoponline.web.app as web_app

    offenders = [
        p.name
        for p in (Path(web_app.__file__).parent / "templates").glob("*.html")
        if 'style="' in p.read_text(encoding="utf-8")
    ]
    assert offenders == []
