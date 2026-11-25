from datetime import datetime
from io import BytesIO

import pytest
from openpyxl import load_workbook

from shoponline.reports import history_import
from tests import sales_history_setup as setup
from tests.history_setup import line, write

PAGES = (
    "/reports",
    "/reports/channels",
    "/reports/products",
    "/reports/provinces",
    "/reports/returns",
)
WINDOW = "from=2026-10&to=2026-11"


@pytest.fixture
def data(db, tmp_path):
    from shoponline.config import Settings

    settings = Settings(database_url="unused", secret_key="s" * 40, data_dir=tmp_path / "data")
    path = write(
        tmp_path / "h.xlsx",
        [line(created="2026-10-05 10:00", month=10, year=2026, paid=500000, city="Kiên Giang")],
    )
    history_import.apply(db, settings, path, "t", skip_backup_check=True)
    setup.report_name(db)
    setup.order(db, "S-1", datetime(2026, 11, 12, 9))
    db.commit()


@pytest.mark.parametrize("page", PAGES)
def test_every_page_opens_for_a_viewer_with_and_without_filters(db, login, data, page):
    viewer = login("viewer")

    assert viewer.get(page).status_code == 200
    assert viewer.get(f"{page}?{WINDOW}&shop=SHOPEE_BD&platform=SHOPEE").status_code == 200


@pytest.mark.parametrize("page", PAGES)
def test_a_signed_out_visitor_is_sent_to_login(app, page):
    from fastapi.testclient import TestClient

    resp = TestClient(app).get(page, follow_redirects=False)

    assert resp.status_code in (303, 401) and "login" in resp.headers.get("location", "login")


def test_the_overview_shows_the_figures_the_chart_and_the_data_note(db, login, data):
    page = login("viewer").get(f"/reports?{WINDOW}").text

    assert "500.000" in page and "120.000" in page
    assert 'id="chart-data"' in page and "chart.umd.min.js" in page
    assert "thiếu đơn từ ngày 01 đến 10/11" in page
    assert "file lịch sử" in page


def test_a_reversed_range_is_explained_and_the_default_is_used(db, login, data):
    page = login("viewer").get("/reports?from=2026-11&to=2026-01").text

    assert "Tháng bắt đầu sau tháng kết thúc" in page


def test_a_range_with_only_history_has_no_invoice_or_money(db, login, data):
    page = login("viewer").get("/reports?from=2026-10&to=2026-10").text

    assert "500.000" in page and "–" in page


def test_excel_download_matches_the_page(db, login, data):
    resp = login("viewer").get(f"/reports?{WINDOW}&format=xlsx")

    assert resp.status_code == 200
    assert "BAO%20CAO%20TONG%20QUAN" in resp.headers["content-disposition"]
    sheet = load_workbook(BytesIO(resp.content)).active
    cells = [[c.value for c in row] for row in sheet.iter_rows()]
    headers = next(i for i, row in enumerate(cells) if row[0] == "Tháng")
    months = [row[0] for row in cells[headers + 1 :]]
    assert months == ["10/2026", "11/2026"]
    assert cells[headers + 1][1] == 500000
    assert any("file lịch sử" in str(row[0]) for row in cells[:headers])


@pytest.mark.parametrize("page", PAGES[1:])
def test_other_pages_download_too(db, login, data, page):
    resp = login("viewer").get(f"{page}?{WINDOW}&format=xlsx")

    assert resp.status_code == 200 and resp.content[:2] == b"PK"


def test_province_page_offers_alias_page_to_admin_only(db, login, data, tmp_path):
    from shoponline.config import Settings

    path = write(
        tmp_path / "h2.xlsx",
        [line(created="2026-10-06 10:00", month=10, year=2026, name="Z", city="Huyện Châu Thành")],
    )
    history_import.apply(
        db,
        Settings(database_url="unused", secret_key="s" * 40, data_dir=tmp_path / "d2"),
        path,
        "t",
        skip_backup_check=True,
    )
    db.commit()

    assert "/province-aliases" in login("admin").get(f"/reports/provinces?{WINDOW}").text
    assert (
        "/province-aliases"
        not in login("viewer")
        .get(f"/reports/provinces?{WINDOW}")
        .text.split("<nav", 1)[-1]
        .split("</nav>", 1)[-1]
    )
