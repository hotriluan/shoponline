"""The accounting CLI commands, run against the rolled-back test session."""

from contextlib import contextmanager
from datetime import date

import pytest
from sqlalchemy import select

from shoponline import cli
from shoponline.accounting import ledger
from shoponline.config import Settings
from shoponline.db import session as session_module
from shoponline.db.models import AccountingRun, AccountingSentDelivery, EventLog


@pytest.fixture
def run_cli(db, monkeypatch, tmp_path, capsys):
    settings = Settings(database_url="unused", secret_key="s" * 40, data_dir=tmp_path)

    @contextmanager
    def scope(_url):
        yield db

    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(session_module, "session_scope", scope)
    monkeypatch.setattr(cli.getpass, "getuser", lambda: "cli-user")

    def run(*argv):
        code = cli.main(list(argv))
        out = capsys.readouterr()
        return code, out.out, out.err

    return run


def test_add_list_and_remove(run_cli, db):
    code, out, _ = run_cli("accounting-ledger", "add", "1900000501", "1900000502")
    assert code == 0 and "2" in out
    code, out, _ = run_cli("accounting-ledger", "list")
    assert "1900000501" in out and "Mốc ngày" in out
    code, out, _ = run_cli("accounting-ledger", "remove", "1900000501")
    assert code == 0
    assert "1900000501" not in ledger.sent_deliveries(db)
    actors = set(db.scalars(select(EventLog.actor).where(EventLog.kind.like("accounting_ledger%"))))
    assert actors == {"cli-user"}


def test_remove_refuses_a_delivery_of_a_run(run_cli, db):
    run = AccountingRun(status=ledger.FINALIZED, created_by="t")
    db.add(run)
    db.flush()
    db.add(AccountingSentDelivery(delivery="1900000510", run_id=run.id))
    db.flush()

    code, _, err = run_cli("accounting-ledger", "remove", "1900000510")

    assert code == 2 and "1900000510" in err
    assert "1900000510" in ledger.sent_deliveries(db)


def test_cutoff_shows_and_sets(run_cli, db):
    code, out, _ = run_cli("accounting-ledger", "cutoff", "--set", "2026-10-31")
    assert code == 0
    assert ledger.get_cutoff(db) == date(2026, 10, 31)
    code, out, _ = run_cli("accounting-ledger", "cutoff")
    assert "2026-10-31" in out
    code, _, err = run_cli("accounting-ledger", "cutoff", "--set", "31/10/2026")
    assert code == 2 and "YYYY-MM-DD" in err


def _finalized_run(db):
    run = AccountingRun(status=ledger.FINALIZED, created_by="t")
    db.add(run)
    db.flush()
    db.add_all(
        AccountingSentDelivery(delivery=d, run_id=run.id) for d in ("1900000521", "1900000522")
    )
    db.flush()
    return run


def test_revoke_without_yes_only_reports(run_cli, db):
    run = _finalized_run(db)
    code, out, _ = run_cli("accounting-run", "revoke", str(run.id))
    assert code == 0 and "2 DO" in out
    assert run.status == ledger.FINALIZED
    assert {"1900000521", "1900000522"} <= ledger.sent_deliveries(db)


def test_revoke_with_yes_removes_the_run(run_cli, db):
    run = _finalized_run(db)
    code, _, _ = run_cli("accounting-run", "revoke", str(run.id), "--yes")
    assert code == 0
    assert run.status == ledger.REVOKED
    assert not {"1900000521", "1900000522"} & ledger.sent_deliveries(db)
    event = db.scalars(select(EventLog).where(EventLog.kind == "accounting_run_revoked")).one()
    assert event.actor == "cli-user"


def test_revoke_refuses_an_open_run(run_cli, db):
    run = AccountingRun(status=ledger.OPEN, created_by="t")
    db.add(run)
    db.flush()
    code, _, err = run_cli("accounting-run", "revoke", str(run.id), "--yes")
    assert code == 2 and "OPEN" in err
