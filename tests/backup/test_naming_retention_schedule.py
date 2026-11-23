"""Pure rules: backup names, which backups a place deletes, when the schedule is due."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from types import SimpleNamespace

from shoponline.backup import naming, schedule
from shoponline.backup.retention import KeepRules, to_delete
from shoponline.clock import VIETNAM

NOW = datetime(2026, 11, 27, 17, 0, tzinfo=VIETNAM)  # a Friday
SETTINGS = SimpleNamespace(db_time=time(16, 30), full_weekday=4, full_time=time(16, 30))


def _name(kind: str, moment: datetime) -> str:
    return naming.make(kind, "shoponline", moment)


# --- naming ---------------------------------------------------------------------------------


def test_new_and_old_names():
    new = naming.parse("shoponline-full-shoponline-20261123-163000.7z")
    assert (new.kind, new.database, new.legacy) == ("full", "shoponline", False)
    assert new.taken_at == datetime(2026, 11, 23, 16, 30, tzinfo=VIETNAM)
    old = naming.parse("shoponline-shoponline-20261111-230000.7z")
    assert (old.kind, old.database, old.legacy) == ("db", "shoponline", True)
    assert naming.parse("shoponline-db-shoponline-20261123-163000.7z").legacy is False
    assert naming.parse("notes.txt") is None
    assert naming.parse("shoponline-db-shoponline-20261399-163000.7z") is None


def test_make_uses_vietnam_time():
    utc_moment = datetime(2026, 11, 23, 9, 30, tzinfo=VIETNAM).astimezone(VIETNAM)
    assert _name("db", utc_moment) == "shoponline-db-shoponline-20261123-093000.7z"


# --- retention ------------------------------------------------------------------------------


def test_keeps_newest_n_of_each_kind_only():
    dbs = [_name("db", NOW - timedelta(hours=h)) for h in range(16)]
    apps = [_name("app", NOW - timedelta(days=d)) for d in range(3)]
    doomed = to_delete(dbs + apps, "shoponline", KeepRules(keep_db=15), NOW)
    assert doomed == [dbs[-1]]  # the oldest database backup; application ones untouched


def test_many_backups_in_one_day_still_keep_only_n():
    same_day = [_name("db", NOW - timedelta(minutes=m)) for m in range(20)]
    assert len(to_delete(same_day, "shoponline", KeepRules(keep_db=15), NOW)) == 5


def test_old_names_count_as_database_backups():
    old = [f"shoponline-shoponline-202611{d:02d}-230000.7z" for d in range(1, 18)]
    doomed = to_delete(old, "shoponline", KeepRules(keep_db=15), NOW)
    assert doomed == old[:2]


def test_full_backups_go_by_age_not_count():
    rules = KeepRules(full_max_days=30)
    old = _name("full", NOW - timedelta(days=31))
    young = [_name("full", NOW - timedelta(days=29))]
    manual = [_name("full", NOW - timedelta(hours=h)) for h in range(1, 25)]
    assert to_delete([old, *young, *manual], "shoponline", rules, NOW) == [old]


def test_even_the_only_full_backup_expires():
    only = _name("full", NOW - timedelta(days=40))
    assert to_delete([only], "shoponline", KeepRules(), NOW) == [only]


def test_other_files_and_databases_are_never_touched():
    names = ["readme.txt", *[_name("db", NOW - timedelta(hours=h)) for h in range(3)]]
    names.append(naming.make("db", "otherdb", NOW - timedelta(days=400)))
    assert to_delete(names, "shoponline", KeepRules(keep_db=1), NOW) == sorted(names[2:4])


# --- schedule -------------------------------------------------------------------------------


def test_database_backup_due_after_today_slot():
    before = NOW.replace(hour=16, minute=0)
    yesterday_run = NOW - timedelta(days=1)
    assert not schedule.is_due("db", before, SETTINGS, before - timedelta(hours=20))
    assert schedule.is_due("db", NOW, SETTINGS, yesterday_run)
    assert not schedule.is_due("db", NOW, SETTINGS, NOW.replace(minute=40))


def test_machine_off_at_slot_catches_up_once():
    evening = NOW.replace(hour=21)
    assert schedule.is_due("db", evening, SETTINGS, NOW - timedelta(days=1))
    assert not schedule.is_due("db", evening + timedelta(minutes=15), SETTINGS, evening)


def test_friday_runs_database_then_full():
    last = {"db": NOW - timedelta(days=1), "full": NOW - timedelta(days=7)}
    assert schedule.due_kinds(NOW, SETTINGS, last) == ["db", "full"]
    saturday = NOW + timedelta(days=1)
    assert schedule.due_kinds(saturday, SETTINGS, {"db": NOW, "full": NOW}) == ["db"]


def test_full_slot_and_next_slot():
    monday = datetime(2026, 11, 23, 9, 0, tzinfo=VIETNAM)
    assert schedule.last_slot("full", monday, SETTINGS) == datetime(
        2026, 11, 20, 16, 30, tzinfo=VIETNAM
    )
    assert schedule.next_slot("full", monday, SETTINGS) == datetime(
        2026, 11, 27, 16, 30, tzinfo=VIETNAM
    )
    assert schedule.next_slot("db", monday, SETTINGS) == datetime(
        2026, 11, 23, 16, 30, tzinfo=VIETNAM
    )
    assert schedule.last_slot("app", monday, SETTINGS) is None


def test_never_backed_up_is_due():
    assert schedule.due_kinds(NOW, SETTINGS, {}) == ["db", "full"]
