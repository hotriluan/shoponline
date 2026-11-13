"""Read zrsd001 (sales orders with PO No) for one platform customer and one document date."""

from __future__ import annotations

from shoponline.saprobot.errors import RobotError
from shoponline.saprobot.transactions.report_screen import (
    execute,
    export_result,
    fill,
    fill_date,
    open_report,
)
from shoponline.saprobot.worker import JobContext, TransactionResult

SCREEN = "zrsd001"
# Online sales office, as filtered in the recording.
SALES_OFFICE = "1401"
SELECTIONS = ("open", "complete")


def run(ctx: JobContext) -> TransactionResult:
    payload = ctx.payload
    selection = payload.get("selection")
    if selection not in SELECTIONS:
        raise RobotError(f"zrsd001: lựa chọn '{selection}' không hợp lệ")
    if payload["date_from"] != payload["date_to"]:
        raise RobotError("zrsd001: robot chỉ đọc một ngày chứng từ mỗi lần")

    open_report(ctx, "ZRSD001")
    fill(ctx, SCREEN, "sales_office", SALES_OFFICE)
    fill_date(ctx, SCREEN, "doc_date", payload["date_from"])
    fill(ctx, SCREEN, "sold_to", payload["sold_to"])
    complete = ctx.screens.find(ctx.gui, SCREEN, "complete")
    if selection == "complete":
        complete.select()
    elif complete.get("selected"):
        raise RobotError("zrsd001: màn hình lọc không mở ở 'Open Sales Order' như bản ghi")
    execute(ctx, SCREEN)
    return TransactionResult(file=export_result(ctx, SCREEN))
