"""The quick order lookup box: /search and the box on every page."""

from datetime import datetime

from shoponline.returns import service
from tests import sales_history_setup as setup
from tests.returns.factory import sales_return

WHEN = datetime(2026, 11, 12, 9)


def _go(client, q):
    return client.get("/search", params={"q": q}, follow_redirects=False)


def _make(db, order_id="260101ABCDEF", **kw):
    order = setup.order(db, order_id, WHEN, **kw)
    db.commit()
    return order


def test_platform_order_id_matches_ignoring_case_and_stray_whitespace(db, login):
    order = _make(db, "261115BUCPCSEN")
    admin = login("admin")
    for typed in ("261115BUCPCSEN", "  261115bucpcsen\t", "261115 BUCP CSEN"):
        resp = _go(admin, typed)
        assert resp.status_code == 303 and resp.headers["location"] == f"/orders/{order.id}"


def test_invoice_number_matches_with_or_without_leading_zeros(db, login):
    order = _make(db, invoice="00008038")
    admin = login("admin")
    for typed in ("00008038", "8038"):
        assert _go(admin, typed).headers["location"] == f"/orders/{order.id}"
    assert "Không tìm thấy" in _go(admin, "0000").text


def test_so_and_do_numbers_match(db, login):
    order = _make(db)
    order.so_number = "5000123456"
    db.commit()
    admin = login("admin")
    assert _go(admin, "5000123456").headers["location"] == f"/orders/{order.id}"
    assert _go(admin, order.do_number).headers["location"] == f"/orders/{order.id}"


def test_return_number_matches_in_full_by_prefix_and_when_void(db, login):
    order = _make(db, "261115RETURN1")
    doc = sales_return(db, order, year=2026, seq=7)
    db.commit()
    admin = login("admin")
    for typed in (doc.doc_no, "007/11.2026"):
        assert _go(admin, typed).headers["location"] == f"/orders/{order.id}"
    service.void(db, doc.id, "lập nhầm", "admin")
    db.commit()
    resp = _go(admin, "007/11.2026")
    assert resp.status_code == 303 and resp.headers["location"] == f"/orders/{order.id}"


def test_same_id_on_two_platforms_lists_both_with_the_match_kind(db, login):
    _make(db, "SAME0001", platform="SHOPEE")
    _make(db, "SAME0001", platform="TIKTOK", invoice=None)
    resp = _go(login("viewer"), "same0001")
    assert resp.status_code == 200
    assert resp.text.count("/orders/") >= 2 and "Khớp theo" in resp.text and "Mã đơn" in resp.text


def test_partial_match_lists_and_short_or_missing_keys_find_nothing(db, login):
    order = _make(db, "XYZ12345678")
    admin = login("admin")
    page = _go(admin, "12345").text
    assert "Khớp một phần" in page and f"/orders/{order.id}" in page
    assert "Không tìm thấy" in _go(admin, "XYZ").text and "«XYZ»" in _go(admin, "XYZ").text
    assert "Không tìm thấy" in _go(admin, "NOPE9999").text


def test_like_wildcards_do_not_match_everything(db, login):
    _make(db, "WILD00000001")
    admin = login("admin")
    for typed in ("%%%%", "____", "WILD%"):
        assert "Không tìm thấy" in _go(admin, typed).text


def test_empty_key_goes_back_and_anonymous_goes_to_login(db, login, app):
    admin = login("admin")
    assert _go(admin, "   ").status_code == 303
    from fastapi.testclient import TestClient

    resp = _go(TestClient(app), "x")
    assert resp.status_code == 303 and resp.headers["location"] == "/login"


def test_search_box_is_on_pages_when_signed_in_only(db, login, app):
    from fastapi.testclient import TestClient

    assert 'action="/search"' in login("viewer").get("/batches").text
    assert 'action="/search"' not in TestClient(app).get("/login").text
