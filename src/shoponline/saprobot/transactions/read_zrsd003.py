"""Read zrsd003 (tax invoices) for the platforms' sales office and a billing date range."""

from __future__ import annotations

from shoponline.saprobot.transactions.report_screen import (
    confirm,
    execute,
    export_result,
    fill,
    fill_date,
    open_report,
)
from shoponline.saprobot.worker import JobContext, TransactionResult

SCREEN = "zrsd003"
# Sales organization and sales office of the platforms, as filtered in the recording.
SALES_ORG = "1000"
SALES_OFFICE = "1401"


def run(ctx: JobContext) -> TransactionResult:
    payload = ctx.payload
    open_report(ctx, "ZRSD003")
    fill(ctx, SCREEN, "sales_org", SALES_ORG)
    confirm(ctx)
    fill(ctx, SCREEN, "sales_office", SALES_OFFICE)
    confirm(ctx)
    fill_date(ctx, SCREEN, "billing_date_from", payload["date_from"])
    fill_date(ctx, SCREEN, "billing_date_to", payload["date_to"])
    execute(ctx, SCREEN)
    return TransactionResult(file=export_result(ctx, SCREEN))
