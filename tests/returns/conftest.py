import pytest


@pytest.fixture
def committed(db_engine):
    """Real committed data for tests that need two connections; wiped afterwards.

    The `db` fixture's work is rolled back, so after the wipe the tables are as the migrations
    left them. Children go first: sales_return points at generated_file and sales_order.
    """
    from sqlalchemy import text

    yield db_engine
    tables = (
        "sales_return_line",
        "sales_return",
        "document_counter",
        "invoice_item_text",
        "generated_file",
        "event_log",
        "sap_tax_invoice",
        "sap_so_ref_item",
        "sap_so_ref",
        "sales_order_item",
        "sales_order",
        "customer_info",
        "order_batch",
    )
    with db_engine.begin() as connection:
        for table in tables:
            connection.execute(text(f"DELETE FROM {table}"))


@pytest.fixture
def settings(tmp_path):
    from shoponline.config import Settings

    return Settings(database_url="unused", secret_key="s" * 40, data_dir=tmp_path / "data")


@pytest.fixture
def issue_day(monkeypatch):
    """The day documents are issued: 25/11/2026 in Vietnam, whatever the clock says."""
    from datetime import date

    day = date(2026, 11, 25)
    monkeypatch.setattr("shoponline.returns.service.today_vn", lambda *a, **k: day)
    return day


@pytest.fixture
def numbered(db, issue_day):
    """The first number is entered once: 080."""
    from shoponline.returns import numbering

    numbering.set_start(db, 2026, 80, "t")
