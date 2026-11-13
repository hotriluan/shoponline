from datetime import date

import pytest

from shoponline.accounting import ledger


@pytest.fixture(autouse=True)
def old_cutoff(db):
    """The migration sets the cutoff to the day it ran; tests start from a cutoff in the past."""
    ledger.set_cutoff(db, date(2000, 1, 1), "test")


@pytest.fixture
def committed(db_engine):
    """Real committed data for tests that need two connections; wiped afterwards.

    The `db` fixture's work is rolled back, so after the wipe the tables are as migrations left
    them: the cutoff is set to the past inside the test and restored at the end.
    """
    from sqlalchemy import text

    with db_engine.begin() as connection:
        before = connection.execute(text("SELECT cutoff_date FROM accounting_baseline")).scalar()
        connection.execute(text("UPDATE accounting_baseline SET cutoff_date = '2000-01-01'"))
    yield db_engine
    tables = (
        "accounting_sent_delivery",
        "accounting_run_source",
        "accounting_run_read",
        "accounting_run",
        "generated_file",
        "sap_job",
        "event_log",
        "sales_order_item",
        "sales_order",
        "customer_info",
        "order_batch",
        "import_batch",
    )
    with db_engine.begin() as connection:
        for table in tables:
            connection.execute(text(f"DELETE FROM {table}"))
        connection.execute(
            text("UPDATE accounting_baseline SET cutoff_date = :day"), {"day": before}
        )
