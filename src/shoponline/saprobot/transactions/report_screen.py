"""Steps shared by the two report reads: open the report, run it, export the result to Excel.

Follows the recorder scripts of 2026-11-12, kept outside git because they hold real customer
data. Dates are typed into the filter field in the SAP user's format instead of picking them in
the F4 calendar the recording used.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from shoponline.saprobot.errors import NoReportData, RobotError
from shoponline.saprobot.worker import JobContext

# Status bar text after F8 when nothing matches; SAP stays on the filter screen.
NO_DATA_TEXT = "no data to display"
# ALV context menu "Spreadsheet...", as recorded; allowed in guard.ALLOWED_CONTEXT_MENU_ITEMS.
SPREADSHEET_EXPORT = "&XXL"


def open_report(ctx: JobContext, tcode: str) -> None:
    ctx.gui.start_transaction(tcode)
    ctx.step()


def fill(ctx: JobContext, screen: str, element: str, value: str) -> None:
    ctx.screens.set_text(ctx.gui, screen, element, value)


def fill_date(ctx: JobContext, screen: str, element: str, iso_day: str) -> None:
    fill(ctx, screen, element, ctx.screens.date_text(date.fromisoformat(iso_day)))


def execute(ctx: JobContext, screen: str) -> None:
    """Press Execute (F8 button); no matching rows ends the read as NoReportData."""
    ctx.screens.press(ctx.gui, screen, "execute")
    message = ctx.step()
    if NO_DATA_TEXT in message.text.lower():
        raise NoReportData(f"{screen.upper()}: SAP không có dữ liệu với bộ lọc này")


def export_result(ctx: JobContext, screen: str) -> Path:
    """Export the ALV result as the admin does (right click → Spreadsheet) into ctx.work_dir.

    The file is the same one an admin uploads. SAP asks for the format ("Select Spreadsheet",
    answered from config/sap_popups.yaml) unless "Always Use Selected Format" was ticked; the
    Save As, SAP GUI Security and Excel windows that follow are answered by ctx.desktop.
    """
    target = (ctx.work_dir / f"{screen}-job-{ctx.job_id}.xlsx").resolve()
    target.unlink(missing_ok=True)  # a retried job must not stop at "replace the file?"
    grid = ctx.screens.find(ctx.gui, screen, "result_grid")
    grid.set_current_cell(0, ctx.screens.id(screen, "result_column"))
    grid.open_context_menu()
    save = ctx.desktop.start_save(target)
    try:
        grid.select_context_menu_item(SPREADSHEET_EXPORT)
        ctx.step()
        save.wait()
    finally:
        save.cancel()
    ctx.step()
    if not target.is_file() or target.stat().st_size == 0:
        raise RobotError(f"{screen.upper()}: SAP không tạo file xuất {target.name}")
    return target
