from datetime import date
from io import BytesIO

from openpyxl import load_workbook

from shoponline.exports.accounting_workbook import (
    INSERTED,
    CustomerLine,
    build_accounting_workbook,
)
from tests.fixtures.build_fixtures import ZRSD004_HEADERS, zrsd004_file, zrsd004_row

CUSTOMERS = {
    "210000001": CustomerLine("2611110AAAAAAA", "Người Một", "Phường Một, Tỉnh Thử, Việt Nam"),
    "210000002": CustomerLine("587000000000000001", None, "Phường Hai, Tỉnh Thử, Việt Nam"),
}


def _lookup(so_number, _sold_to):
    return CUSTOMERS.get(so_number, CustomerLine(None, None, None))


def _source(tmp_path):
    return zrsd004_file(
        tmp_path / "z4.xlsx",
        [
            zrsd004_row("1900000001", "210000001", "100000003"),
            zrsd004_row("1900000001", "210000001", "100000004", line_item=20),
            zrsd004_row("1900000002", "210000002", "100000001", 2, sold_to="1200001146"),
            zrsd004_row("1900000003", "210000003", "100000001", gi_date=date(2026, 11, 13)),
        ],
    )


def _rows(wb):
    return [[c.value for c in row] for row in wb.worksheets[0].iter_rows()]


def test_inserts_three_columns_and_keeps_everything_else(tmp_path):
    source = _source(tmp_path)
    original = _rows(load_workbook(source))
    result = build_accounting_workbook(source, _lookup)
    buffer = BytesIO()
    result.workbook.save(buffer)
    out = _rows(load_workbook(BytesIO(buffer.getvalue())))

    so_index = ZRSD004_HEADERS.index("SO Reference")
    assert out[0][so_index + 1 : so_index + 4] == list(INSERTED)
    assert len(out) == len(original)  # total rows kept
    for before, after in zip(original, out, strict=True):
        assert after[: so_index + 1] + after[so_index + 4 :] == before
    assert out[1][so_index + 1 : so_index + 4] == [
        "2611110AAAAAAA", "Người Một", "Phường Một, Tỉnh Thử, Việt Nam",
    ]
    assert out[3][so_index + 1] == "587000000000000001"
    assert out[-1][so_index + 1 : so_index + 4] == [None, None, None]
    assert result.file_name == "SHOP ONLINE 131126.xlsx"


def test_warns_about_missing_values(tmp_path):
    result = build_accounting_workbook(_source(tmp_path), _lookup)
    text = "\n".join(result.warnings)
    assert "SO 210000002" in text and "tên khách" in text
    assert "SO 210000003" in text and "mã đơn" in text
    assert "SO 210000001" not in text


def test_fills_existing_columns_instead_of_inserting_twice(tmp_path):
    first = build_accounting_workbook(_source(tmp_path), _lookup)
    again_path = tmp_path / "again.xlsx"
    first.workbook.save(again_path)
    second = build_accounting_workbook(again_path, _lookup)
    header = [c.value for c in second.workbook.worksheets[0][1]]
    assert header.count("mã đơn hàng") == 1
    assert len(header) == len(ZRSD004_HEADERS) + 3
