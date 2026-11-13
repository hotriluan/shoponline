"""Read zrsd004 (outbound deliveries) for one platform customer and one actual GI date."""

from __future__ import annotations

from shoponline.saprobot.transactions.report_screen import (
    execute,
    export_result,
    fill,
    fill_date,
    open_report,
)
from shoponline.saprobot.worker import JobContext, TransactionResult

SCREEN = "zrsd004"
# Sales organization, as filtered in the recording.
SALES_ORG = "1000"


def run(ctx: JobContext) -> TransactionResult:
    payload = ctx.payload
    open_report(ctx, "ZRSD004")
    fill(ctx, SCREEN, "sales_org", SALES_ORG)
    fill(ctx, SCREEN, "sold_to", payload["sold_to"])
    fill_date(ctx, SCREEN, "gi_date", payload["gi_date"])
    execute(ctx, SCREEN)
    return TransactionResult(file=export_result(ctx, SCREEN))
