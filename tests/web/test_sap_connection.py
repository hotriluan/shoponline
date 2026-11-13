import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.config import Settings
from shoponline.db.models import EventLog, SapJob
from shoponline.domain.sku_mapping import upsert_mapping
from shoponline.importers.order_import import import_orders
from shoponline.importers.shopee_orders import read_shopee_orders
from shoponline.sapjobs import queue, sap_settings
from shoponline.sapjobs.queue import SapTarget
from shoponline.web.app import create_app
from shoponline.web.auth import set_user
from tests.fixtures.build_fixtures import shopee_orders_file, shopee_row
from tests.sap_setup import NO_ENV, configure_sap

AEP = SapTarget("AEP", "300")
URL = "/robot/sap-connection"
FORM = {
    "system": "AEP",
    "client": "300",
    "connection": "SAP PROD",
    "sap_user": "AL17016",
    "language": "EN",
    "max_failures": "3",
    "evidence_keep_days": "30",
}


@pytest.fixture
def app(db, tmp_path):
    set_user(db, "admin", "admin-password", "admin")
    set_user(db, "viewer", "viewer-password", "viewer")
    configure_sap(db, AEP, user="AL17016", connection="SAP PROD", language="EN")
    return create_app(
        Settings(database_url="unused", secret_key="s" * 40, data_dir=tmp_path / "data"),
        session_factory=lambda: Session(
            bind=db.bind, join_transaction_mode="create_savepoint", expire_on_commit=False
        ),
        env=NO_ENV,
    )


def _login(app, username):
    client = TestClient(app)
    client.post("/login", data={"username": username, "password": f"{username}-password"})
    return client


def _checks(db):
    db.expire_all()
    return db.scalars(
        select(SapJob).where(SapJob.kind == queue.CHECK_CONNECTION).order_by(SapJob.id)
    ).all()


def _heartbeat(db, *, age=1, password=True, entries=("SAP PROD", "QAS server")):
    control = queue.control(db)
    control.last_seen_at = datetime.now(UTC) - timedelta(seconds=age)
    control.robot_host = "ROBOT-PC"
    control.password_present = password
    control.saplogon_entries = json.dumps(list(entries))
    db.flush()


def test_page_shows_robot_password_and_the_choice_of_logon_entries(db, app):
    _heartbeat(db)
    page = _login(app, "admin").get(URL).text
    assert "đang chạy" in page and "ROBOT-PC" in page
    assert "đã có" in page and "đã xác nhận AEP/300" in page
    assert '<option value="QAS server"' in page and 'value="SAP PROD" selected' in page


def test_password_missing_shows_the_command_to_run(db, app):
    _heartbeat(db, password=False)
    assert "sap-password set" in _login(app, "admin").get(URL).text


def test_without_entries_the_page_asks_for_typed_text(db, app):
    _heartbeat(db, entries=())
    page = _login(app, "admin").get(URL).text
    assert '<input type="text" name="connection"' in page


def test_viewer_sees_the_page_but_cannot_save_or_check(db, app):
    viewer = _login(app, "viewer")
    page = viewer.get(URL).text
    assert "Lưu và kiểm tra" not in page and "disabled" in page
    viewer.post(URL, data={**FORM, "sap_user": "HACKER", "action": "save_check"})
    assert sap_settings.load(db, NO_ENV).sap_user == "AL17016"
    assert _checks(db) == []


def test_invalid_values_come_back_on_the_form_and_are_not_saved(db, app):
    response = _login(app, "admin").post(URL, data={**FORM, "client": "30", "action": "save"})
    assert response.status_code == 422
    assert "3 chữ số" in response.text and 'value="30"' in response.text
    assert sap_settings.load(db, NO_ENV).client == "300"


def test_save_changes_the_user_and_logs_who_changed_what(db, app):
    admin = _login(app, "admin")
    admin.post(URL, data={**FORM, "sap_user": "NEWUSER", "action": "save"})
    config = sap_settings.load(db, NO_ENV)
    assert config.sap_user == "NEWUSER" and config.target_verified
    event = db.scalars(
        select(EventLog)
        .where(EventLog.kind == "sap_settings_changed", EventLog.actor == "admin")
        .order_by(EventLog.id.desc())
    ).first()
    assert "NEWUSER" in event.detail and "AL17016" in event.detail
    assert _checks(db) == []


def test_check_queues_exactly_one_job_and_a_second_click_replaces_a_waiting_one(db, app):
    admin = _login(app, "admin")
    admin.post(URL, data={**FORM, "action": "check"})
    admin.post(URL, data={**FORM, "action": "check"})
    checks = _checks(db)
    assert [c.status for c in checks] == [queue.FAILED, queue.PENDING]
    assert "Thay bằng" in checks[0].error
    assert (checks[1].target_system, checks[1].target_client) == ("AEP", "300")
    assert checks[1].created_by == "admin"


def test_check_is_refused_while_one_is_running(db, app):
    admin = _login(app, "admin")
    admin.post(URL, data={**FORM, "action": "check"})
    queue.claim(db)
    page = admin.post(URL, data={**FORM, "action": "check"}).text
    assert "đang mở" in page or "Đã có việc" in page
    assert len(_checks(db)) == 1


def test_save_and_check_saves_then_checks_the_new_system(db, app):
    _login(app, "admin").post(URL, data={**FORM, "client": "400", "action": "save_check"})
    config = sap_settings.load(db, NO_ENV)
    assert config.target == SapTarget("AEP", "400") and not config.target_verified
    (check,) = _checks(db)
    assert (check.target_system, check.target_client) == ("AEP", "400")


def test_robot_off_is_said_plainly_and_the_check_does_not_hang_silently(db, app):
    _heartbeat(db, age=120)
    admin = _login(app, "admin")
    admin.post(URL, data={**FORM, "action": "check"})
    page = admin.get(URL).text
    assert "Robot không chạy" in page and 'http-equiv="refresh"' in page


def test_busy_robot_says_which_job_it_is_finishing(db, app):
    _heartbeat(db)
    busy = queue.enqueue(db, queue.READ_ZRSD004, AEP, "k", {}, "admin")
    queue.claim(db)
    admin = _login(app, "admin")
    admin.post(URL, data={**FORM, "action": "check"})
    assert f"Đang chờ robot xong việc #{busy.id}" in admin.get(URL).text


def test_finished_check_shows_the_session_or_the_fix_and_stops_refreshing(db, app):
    admin = _login(app, "admin")
    admin.post(URL, data={**FORM, "action": "check"})
    job = queue.claim(db)
    queue.complete(
        db,
        job,
        {
            "system": "AEP",
            "client": "300",
            "user": "AL17016",
            "logged_on_at": "2026-11-13T03:00:00",
        },
    )
    page = admin.get(URL).text
    assert "Đăng nhập thành công" in page and "AL17016" in page
    assert 'http-equiv="refresh"' not in page and "disabled" not in page.split("<fieldset")[1][:40]

    admin.post(URL, data={**FORM, "action": "check"})
    job = queue.claim(db)
    queue.fail(
        db,
        job,
        "Đăng nhập SAP không thành công: [E] Name or password is incorrect",
        result={"reason": "logon_failed"},
    )
    page = admin.get(URL).text
    assert "Name or password is incorrect" in page and "logon_failed" in page


def test_changed_system_blocks_report_reads_until_a_check_succeeds(db, app, tmp_path):
    upsert_mapping(db, "SHOPEE", "Sơn thử A", "Màu 01,1 lít", "100000001", "SAP A", "t")
    file = shopee_orders_file(tmp_path / "s.xlsx", [shopee_row("A1")])
    batch = import_orders(db, read_shopee_orders(file), "SHOPEE", date(2026, 11, 11), "t").batch

    admin = _login(app, "admin")
    admin.post(URL, data={**FORM, "client": "400", "action": "save"})
    assert "kiểm tra kết nối" in admin.post(f"/batches/{batch.id}/confirm").text
    assert "Robot đọc zrsd004 đang khóa" in admin.get(f"/batches/{batch.id}").text
    admin.post(f"/batches/{batch.id}/accounting-file")
    assert _reads(db) == []
    assert "chưa được xác nhận" in admin.get("/batches").text  # banner on every page

    sap_settings.mark_verified(db, NO_ENV, "AEP", "400")
    admin.post(f"/batches/{batch.id}/accounting-file")
    (read,) = _reads(db)
    assert read.kind == queue.READ_ZRSD004 and read.target_client == "400"


def _reads(db):
    db.expire_all()
    return [j for j in db.scalars(select(SapJob)).all() if j.kind != queue.CHECK_CONNECTION]
