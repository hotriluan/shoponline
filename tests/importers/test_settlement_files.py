import pytest
from openpyxl import Workbook

from shoponline.importers.excel_table import FileRejected, parse_money, parse_signed_money
from shoponline.importers.settlement_files import read_settlement_file
from tests.fixtures.build_fixtures import (
    lazada_settlement_file,
    shopee_settlement_file,
    shopee_settlement_row,
    tiktok_settlement_file,
    tiktok_settlement_row,
)


def test_shopee_reads_signed_amounts_and_skips_rows_without_an_order(tmp_path):
    path = shopee_settlement_file(
        tmp_path / "s.xlsx",
        [
            shopee_settlement_row("A1", 90300.0),
            shopee_settlement_row("A2", -2700.0, kind="Tiền ra"),
            shopee_settlement_row("-", -5000.0, kind="Điều chỉnh"),
        ],
    )
    result = read_settlement_file(path)
    assert result.platform == "SHOPEE"
    assert [(r.platform_order_id, r.amount) for r in result.rows] == [("A1", 90300), ("A2", -2700)]
    assert len(result.skipped) == 1


def test_shopee_keeps_only_successful_transactions(tmp_path):
    path = shopee_settlement_file(
        tmp_path / "s.xlsx",
        [shopee_settlement_row("A1", 100.0), shopee_settlement_row("A2", 5.0, status="Đang xử lý")],
    )
    result = read_settlement_file(path)
    assert [r.platform_order_id for r in result.rows] == ["A1"]
    assert len(result.skipped) == 1


def test_shopee_identical_transactions_are_two_rows_with_distinct_keys(tmp_path):
    path = shopee_settlement_file(
        tmp_path / "s.xlsx",
        [shopee_settlement_row("A1", 100.0), shopee_settlement_row("A1", 100.0)],
    )
    keys = [r.line_key for r in read_settlement_file(path).rows]
    assert len(keys) == 2 and len(set(keys)) == 2
    assert keys == [r.line_key for r in read_settlement_file(path).rows]


@pytest.mark.parametrize("summary_rows", [3, 16, 25])
def test_shopee_header_may_sit_at_any_row(tmp_path, summary_rows):
    path = shopee_settlement_file(
        tmp_path / "s.xlsx", [shopee_settlement_row("A1", 1.0)], summary_rows=summary_rows
    )
    assert len(read_settlement_file(path).rows) == 1


def test_tiktok_uses_the_related_order_id_and_reports_other_types(tmp_path):
    path = tiktok_settlement_file(
        tmp_path / "t.xlsx",
        [
            tiktok_settlement_row("111", "198102"),
            tiktok_settlement_row("222", "0"),
            tiktok_settlement_row("333", "-2565"),
            tiktok_settlement_row(
                "999", "50", kind="Điều chỉnh", transaction="ADJ1", related="444"
            ),
            tiktok_settlement_row("555", "10", transaction="TX5", related="555"),
        ],
    )
    result = read_settlement_file(path)
    assert result.platform == "TIKTOK"
    assert [(r.platform_order_id, r.amount) for r in result.rows] == [
        ("111", 198102),
        ("222", 0),
        ("333", -2565),
        ("555", 10),
    ]
    assert result.rows[3].line_key == "TX5"
    assert result.skipped == ["Điều chỉnh: ID ADJ1, đơn liên quan 444"]


@pytest.mark.parametrize("amount", ["", "Infinity", "1E+30", "12.5", "abc"])
def test_rejects_unusable_amounts_with_the_row_number(tmp_path, amount):
    path = tiktok_settlement_file(
        tmp_path / "t.xlsx",
        [tiktok_settlement_row("111", "10"), tiktok_settlement_row("222", amount)],
    )
    with pytest.raises(FileRejected, match="Dòng 3"):
        read_settlement_file(path)


def test_rejects_a_long_order_id_and_a_repeated_tiktok_transaction(tmp_path):
    path = shopee_settlement_file(tmp_path / "s.xlsx", [shopee_settlement_row("X" * 41, 1.0)])
    with pytest.raises(FileRejected, match="Mã đơn dài quá"):
        read_settlement_file(path)
    path = tiktok_settlement_file(
        tmp_path / "t.xlsx", [tiktok_settlement_row("1", "5"), tiktok_settlement_row("1", "6")]
    )
    with pytest.raises(FileRejected, match="lặp"):
        read_settlement_file(path)


def test_rejects_lazada_unknown_files_and_files_without_rows(tmp_path):
    with pytest.raises(FileRejected, match="Lazada"):
        read_settlement_file(lazada_settlement_file(tmp_path / "l.xlsx"))
    other = tmp_path / "o.xlsx"
    wb = Workbook()
    wb.active.title = "Other"
    wb.save(other)
    with pytest.raises(FileRejected, match="Không nhận ra"):
        read_settlement_file(other)
    with pytest.raises(FileRejected, match="không có giao dịch"):
        read_settlement_file(tiktok_settlement_file(tmp_path / "e.xlsx", []))


def test_signed_money_allows_negative_but_not_blank_and_parse_money_is_unchanged():
    assert parse_signed_money("-2700", "x") == -2700
    with pytest.raises(ValueError):
        parse_signed_money("", "x")
    assert parse_money("", "x") == 0
    with pytest.raises(ValueError, match="âm"):
        parse_money("-1", "x")
