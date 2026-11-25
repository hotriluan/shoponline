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
