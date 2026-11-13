from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from shoponline.config import ConfigError
from shoponline.db.models import EventLog, RobotControl, SapSetting
from shoponline.sapjobs import queue, sap_settings
from shoponline.sapjobs.queue import SapTarget
from shoponline.sapjobs.sap_settings import SapSettingsError
from tests.sap_setup import NO_ENV, configure_sap

ENV = {
    "SHOPONLINE_SAP_SYSTEM": "aep",
    "SHOPONLINE_SAP_CLIENT": "300",
    "SHOPONLINE_SAP_CONNECTION": "SAP PRODUCTION",
    "SHOPONLINE_SAP_USER": "AL17016",
    "SHOPONLINE_SAP_LANGUAGE": "EN",
    "SHOPONLINE_ROBOT_MAX_FAILURES": "5",
}


def test_first_load_builds_the_row_from_the_environment_and_trusts_it(db):
    config = sap_settings.load(db, ENV)
    assert config.target == SapTarget("AEP", "300")
    assert config.connection == "SAP PRODUCTION" and config.sap_user == "AL17016"
    assert config.language == "EN"
    assert config.max_failures == 5 and config.evidence_keep_days == 30
    assert config.target_verified  # a robot already running is not locked out by the upgrade
    assert db.get(SapSetting, 1).changed_by == "env"


def test_empty_environment_leaves_the_robot_unconfigured(db):
    config = sap_settings.load(db, NO_ENV)
    assert config.target is None and not config.target_verified
    assert config.max_failures == 3


def test_database_value_wins_and_a_null_column_falls_back_to_the_environment(db):
    sap_settings.load(db, NO_ENV)  # row created with nothing
    sap_settings.save(db, "admin", NO_ENV, sap_user="NEWUSER")
    config = sap_settings.load(db, ENV)
    assert config.sap_user == "NEWUSER"
    assert config.connection == "SAP PRODUCTION"  # still NULL in the row


def test_environment_with_only_one_of_system_and_client_is_refused(db):
    with pytest.raises(ConfigError):
        sap_settings.load(db, {"SHOPONLINE_SAP_SYSTEM": "AEP"})


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"system": "AE", "client": "300", "sap_user": "U"}, "3 ký tự"),
        ({"system": "AEP", "client": "30", "sap_user": "U"}, "3 chữ số"),
        ({"system": "AEP", "client": "", "sap_user": "U"}, "cả hệ thống và client"),
        ({"system": "AEP", "client": "300", "sap_user": " "}, "User SAP"),
        ({"language": "ENG"}, "2 chữ cái"),
        ({"max_failures": "0"}, "số nguyên dương"),
        ({"evidence_keep_days": "abc"}, "số nguyên dương"),
        ({"nonsense": "x"}, "không có trong cấu hình"),
    ],
)
def test_invalid_values_are_refused_and_nothing_is_stored(db, fields, message):
    with pytest.raises(SapSettingsError, match=message):
        sap_settings.save(db, "admin", NO_ENV, **fields)
    row = db.get(SapSetting, 1)
    assert row is None or (row.system is None and row.sap_user is None and row.language is None)


def test_save_normalises_and_records_who_changed_what(db):
    changes = sap_settings.save(
        db,
        "admin",
        NO_ENV,
        system="aep",
        client="300",
        sap_user=" AL17016 ",
        language="en",
        connection="SAP PRODUCTION",
    )
    assert changes["system"] == ["", "AEP"] and changes["language"] == ["", "EN"]
    config = sap_settings.load(db, NO_ENV)
    assert config.target == SapTarget("AEP", "300") and config.sap_user == "AL17016"
    event = db.scalars(select(EventLog).where(EventLog.kind == "sap_settings_changed")).one()
    assert event.actor == "admin" and "AEP" in event.detail
    assert "assword" not in event.detail


def test_saving_the_same_values_again_writes_no_event(db):
    configure_sap(db, SapTarget("AEP", "300"))
    before = db.scalars(select(EventLog)).all()
    assert sap_settings.save(db, "admin", NO_ENV, sap_user="robot01", max_failures="3") == {}
    assert len(db.scalars(select(EventLog)).all()) == len(before)


def test_changing_system_or_client_clears_the_verification_but_other_fields_do_not(db):
    configure_sap(db, SapTarget("AEP", "300"))
    assert sap_settings.load(db, NO_ENV).target_verified
    sap_settings.save(db, "admin", NO_ENV, sap_user="OTHER", language="VI")
    assert sap_settings.load(db, NO_ENV).target_verified
    sap_settings.save(db, "admin", NO_ENV, client="400")
    config = sap_settings.load(db, NO_ENV)
    assert config.target == SapTarget("AEP", "400") and not config.target_verified


def test_a_check_for_the_old_target_does_not_verify_the_new_one(db):
    configure_sap(db, SapTarget("AEP", "300"), verified=False)
    assert not sap_settings.mark_verified(db, NO_ENV, "AEP", "400")
    assert not sap_settings.load(db, NO_ENV).target_verified
    assert sap_settings.mark_verified(db, NO_ENV, "AEP", "300")
    assert sap_settings.load(db, NO_ENV).target_verified


def test_robot_alive_needs_a_heartbeat_newer_than_thirty_seconds(db):
    control = queue.control(db)
    now = datetime.now(UTC)
    assert not sap_settings.robot_alive(control, now)
    control.last_seen_at = now - timedelta(seconds=10)
    assert sap_settings.robot_alive(control, now)
    control.last_seen_at = now - timedelta(seconds=31)
    assert not sap_settings.robot_alive(control, now)
    assert isinstance(control, RobotControl)
