---
title: Implement returns in Shop Online file and reports
date: 2026-11-26
summary: "Return documents now add negative ledger rows to the Shop Online file, reports are net of returns, and labels show across modules"
---

# Implement returns in Shop Online file and reports

## What happened

Implemented plan `plans/261126-0404-returns-in-sales-reporting`. Phases 1 to 5 are done and phase 6's docs are done. The hands-on acceptance on dev data was not run, because dev has no return documents and no document numbering set up; automated tests cover the same scenarios.

- Migration 0018 adds `sales_return_sale_line`, `sales_history_file_return` and `sales_return_history_exported`. Migration 0019 replaces both report views.
- `returns/sale_lines.split` spreads each material's returned quantity over the platform lines with that material. If the share is not a whole number, the return is blocked. `shoponline return-sale-lines backfill` fills in returns issued before this change.
- `states.cancel_order` cancels a DELIVERED order only when its DO has no invoice yet. `transition()` refuses DELIVERED to CANCELLED unless it is called with `invoice_checked=True`, so a future caller cannot skip the invoice check.
- The Shop Online file is now an append-only ledger. A return adds negative rows (ISSUE). Voiding a return after those rows were pasted adds rows that reverse them (VOID). Column I holds a constant −1, 0 or +1. Confirm, unconfirm, delete and retention track return rows the same way they track orders.
- Reports gain a 'return' source. An order is counted while its net quantity in the filter is above zero (a window SUM). `returned_value` now includes VAT, on the same basis as `invoice_value`.
- Return labels appear on the order detail page, the batch page, the Lazada payout page and the accounting run page.

## Surprises

- The plan assumed `/returns/{id}` was admin-only, but any signed-in user can open it. The new labels still give viewers no link, as the plan says.
- During self-review I found that a return with no sale lines would have recorded an empty file entry that could be confirmed as pasted. It is now blocked, with a reason pointing to the backfill command.
- The app's backup is not configured on dev (no `SHOPONLINE_BACKUP_DIRS`), so I backed up dev with `pg_dump` to `backups-local/*.dump`, which git ignores.
- Bash heredocs containing quotes failed in this runner. Writing the patch scripts to the scratchpad worked around it.

## Next steps

- Send the accountants the description of the new row types before the first paste.
- Run the production deploy: back up, migrate, then run the backfill.
- Optionally, issue sample returns on dev to try it by hand.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
