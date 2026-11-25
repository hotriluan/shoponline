import json
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from shoponline.exports.return_request_workbook import render
from tests.exports.return_fixtures import line, sales_return
from tests.support.format_compare import compare_xlsx, xlsx_expected, xlsx_format

BASELINE = json.loads(
    (Path(__file__).resolve().parents[1] / "support" / "template_baseline.json").read_text("utf-8")
)["xlsx"]
SAP_NAME = "V-09 REDDISH CLAY 2004 VN-0.8L"


def sheet(data: bytes):
    return load_workbook(BytesIO(data))["RRG ENGLISH"]


def test_one_line_return_fills_the_sample_cells():
    ws = sheet(render(sales_return()))
    assert ws["H6"].value == "Shopee"
    assert (ws["C14"].value, ws["D14"].value) == (1, SAP_NAME)
    assert (ws["N14"].value, ws["P14"].value, ws["AL14"].value) == (1, "PC", "KHÁCH HỦY ĐƠN")
    assert ws["B15"].value.startswith("Note : Batch No")
    assert ws["AW2"].value == "No" and ws["AW3"].value == "Date"  # left for the people to fill
    assert ws.print_area == "'RRG ENGLISH'!$B$1:$BI$31"


def test_returned_goods_use_the_other_reason_label():
    ws = sheet(render(sales_return(reason_kind="RETURN")))
    assert ws["AL14"].value == "KHÁCH TRẢ HÀNG"


def test_the_item_name_is_the_sap_name_not_the_invoice_name():
    ws = sheet(render(sales_return([line(name="TÊN TRÊN HÓA ĐƠN")])))
    assert ws["D14"].value == SAP_NAME


def test_a_two_line_return_pushes_the_note_and_print_area_down_by_one_row():
    second = line(2)
    second.sap_name = "SAP LÓT"
    second.stock_unit = "CAN"
    second.return_qty = 3
    ws = sheet(render(sales_return([line(1), second])))
    assert (ws["C15"].value, ws["D15"].value) == (2, "SAP LÓT")
    assert (ws["N15"].value, ws["P15"].value) == (3, "CAN")
    assert ws["B16"].value.startswith("Note : Batch No") and ws["B15"].value is None
    assert ws["B17"].value == "*) Atthace Test Result"
    assert ws.print_area == "'RRG ENGLISH'!$B$1:$BI$32"
    heights = {r: ws.row_dimensions[r].height for r in (14, 15, 19, 27, 28)}
    assert heights == {14: 49.5, 15: 49.5, 19: 6.0, 27: 12.75, 28: 12.75}


def test_only_returned_lines_become_rows():
    ws = sheet(render(sales_return([line(1, ret=0), line(2, qty=2, ret=1, net=55555)])))
    assert ws["C14"].value == 1 and ws["N14"].value == 1
    assert ws["B15"].value.startswith("Note : Batch No")


@pytest.mark.parametrize("text", ["=1+1", "+cmd|calc", "-2+3", "@SUM(A1)"])
def test_item_names_that_look_like_formulas_are_written_as_text(text):
    item = line()
    item.sap_name = text
    ws = sheet(render(sales_return([item], platform_name=text)))
    assert ws["D14"].data_type == "s" and ws["D14"].value == text
    assert ws["H6"].data_type == "s" and ws["H6"].value == text


def _differences(sales, extra):
    return compare_xlsx(xlsx_expected(BASELINE, extra_rows=extra), xlsx_format(render(sales)))


def test_the_filled_sheet_has_the_sample_format_for_one_line():
    assert _differences(sales_return(), 0) == []


def test_the_filled_sheet_has_the_sample_format_for_two_and_three_lines():
    two = sales_return([line(1), line(2)])
    three = sales_return([line(1), line(2), line(3)])
    assert _differences(two, 1) == []
    assert _differences(three, 2) == []


def test_no_picture_or_drawing_part_is_written():
    assert xlsx_format(render(sales_return()))["forbidden_parts"] == []
