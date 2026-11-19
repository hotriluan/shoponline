"""History lists are searched and paged on the server, so old rows stay reachable."""

import re

from shoponline.db.models import AccountingRun, ImportBatch
from shoponline.web.pagination import Page


def _runs(db, count, created_by="lan"):
    runs = [AccountingRun(status="FINALIZED", created_by=created_by) for _ in range(count)]
    db.add_all(runs)
    db.flush()
    return runs


def _run_links(html):
    return set(re.findall(r'href="/accounting/runs/(\d+)"', html))


def test_first_page_holds_default_size_and_links_to_the_rest(db, login):
    runs = _runs(db, 30)
    html = login("viewer").get("/accounting").text
    assert len(_run_links(html)) == 25
    assert str(runs[-1].id) in _run_links(html)
    assert str(runs[0].id) not in _run_links(html)
    assert "Hiển thị 1–25 trong 30 dòng" in html


def test_second_page_reaches_older_rows(db, login):
    runs = _runs(db, 30)
    html = login("viewer").get("/accounting?page=2").text
    assert _run_links(html) == {str(r.id) for r in runs[:5]}


def test_search_finds_rows_beyond_the_first_page(db, login):
    _runs(db, 30, created_by="lan")
    old = _runs(db, 1, created_by="minh")[0]
    _runs(db, 30, created_by="lan")
    html = login("viewer").get("/accounting?q=MINH").text
    assert _run_links(html) == {str(old.id)}
    assert "1 dòng khớp" in html


def test_search_without_match_explains_and_offers_a_reset(db, login):
    _runs(db, 3)
    html = login("viewer").get("/accounting?q=khong-co").text
    assert "Không có dòng nào khớp" in html and "xóa tìm kiếm" in html


def test_page_size_and_bad_parameters_are_tolerated(db, login):
    _runs(db, 12)
    client = login("viewer")
    assert len(_run_links(client.get("/accounting?size=10").text)) == 10
    assert len(_run_links(client.get("/accounting?size=7").text)) == 12  # unknown size: default
    assert len(_run_links(client.get("/accounting?page=abc&size=x").text)) == 12
    assert len(_run_links(client.get("/accounting?page=99&size=10").text)) == 2  # clamped to last


def test_like_wildcards_in_the_search_are_literal(db, login):
    _runs(db, 3, created_by="lan")
    html = login("viewer").get("/accounting?q=%25").text
    assert _run_links(html) == set()


def test_pager_links_keep_the_other_query_parameters():
    page = Page(items=[], page=2, size=10, total=40, q="abc", keep=[("status", "FAILED")])
    assert page.url(3) == "?status=FAILED&q=abc&size=10&page=3"
    assert page.url(1, "") == "?status=FAILED&size=10"
    assert page.numbers() == [1, 2, 3, 4]
    assert Page([], 1, 10, 100, "").numbers() == [1, 2, None, 10]


def test_sap_report_imports_are_paged_and_searchable(db, login):
    db.add_all(
        ImportBatch(
            kind="zrsd001",
            file_name=f"file-{i}.xlsx",
            sha256=f"{i:064d}",
            stored_path="x",
            imported_by="lan",
        )
        for i in range(15)
    )
    db.flush()
    client = login("viewer")
    html = client.get("/sap-reports").text
    assert html.count("file-") == 15  # default size 25 shows all
    html = client.get("/sap-reports?q=file-14").text
    assert "file-14.xlsx" in html and "file-3.xlsx" not in html


def test_every_paged_page_accepts_search_and_paging_parameters(login):
    client = login("admin")
    for url in (
        "/batches?q=11/11/2026&size=10&page=2",
        "/customers?platform=TIKTOK&missing=true&q=an&page=3",
        "/robot?status=DONE&q=zrsd&size=50",
        "/sales-history?q=abc&page=2",
        "/sap-reports?q=x",
    ):
        resp = client.get(url)
        assert resp.status_code == 200, url
