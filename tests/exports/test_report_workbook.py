from io import BytesIO

from openpyxl import load_workbook

from shoponline.exports import report_workbook


def _sheet(**changes):
    args = dict(
        sheet_title="Tổng quan",
        filter_line="Từ 01/2026 đến 11/2026",
        notes=["Ghi chú một", "Ghi chú hai"],
        headers=["Tháng", "Giá trị", "Tỷ lệ"],
        rows=[["01/2026", 1234567, 0.125], ["02/2026", None, None]],
        money=["Giá trị"],
        percent=["Tỷ lệ"],
    )
    args.update(changes)
    workbook = report_workbook.build(
        args.pop("sheet_title"), args.pop("filter_line"), args.pop("notes"),
        args.pop("headers"), args.pop("rows"), **args,
    )  # fmt: skip
    return load_workbook(BytesIO(report_workbook.to_bytes(workbook))).active


def test_title_filter_notes_then_the_table():
    sheet = _sheet()

    assert [sheet.cell(row=r, column=1).value for r in range(1, 5)] == [
        "Tổng quan", "Từ 01/2026 đến 11/2026", "Ghi chú một", "Ghi chú hai"
    ]  # fmt: skip
    assert sheet["A6"].value == "Tháng" and sheet["A7"].value == "01/2026"
    assert sheet.max_row == 8


def test_money_and_percent_columns_are_formatted_and_blanks_stay_blank():
    sheet = _sheet()

    assert sheet["B7"].value == 1234567 and sheet["B7"].number_format == "#,##0"
    assert sheet["C7"].number_format == "0.0%"
    assert sheet["B8"].value is None


def test_text_that_looks_like_a_formula_is_written_as_text():
    sheet = _sheet(rows=[["=HYPERLINK(1)", 1, 0.1]])

    assert not str(sheet["A7"].value).startswith("=")
