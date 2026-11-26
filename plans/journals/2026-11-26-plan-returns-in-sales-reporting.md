---
title: "Plan: returns in sales reporting"
date: 2026-11-26
summary: "Planned negative ledger rows for returns in the Shop Online file and report views, return labels across modules, and cancelling DO orders that have no invoice"
---

# Plan: returns in sales reporting

## What happened
Asked whether issuing a return document after invoice changes anything else. It does not: the order stays DELIVERED, the Shop Online history file still exports positive rows, and the reports count the order in full. Brainstorm report: plans/reports/brainstorm-261126-1057-returns-in-sales-reporting.md. Plan: plans/261126-0404-returns-in-sales-reporting (6 phases).

Evidence gathered:
- The accountants' history file only grows by pasting rows at the bottom. It has 0 negative rows out of 3,010, so there is no existing convention for returns.
- `returned_value` in the reports excludes VAT while `invoice_value` includes it, so the return rate reads about 8% low.
- Return lines are SAP SO lines with no link to platform order lines; the only shared key is `material_number`.
- An order whose DO was cancelled before billing could neither be returned nor cancelled.

## Decision
- Treat the Shop Online file as an append-only ledger. Each return adds negative rows at marketplace price, dated with the original order date. Voiding a return after its rows were pasted adds reversal rows. Column I holds −1, 0 or +1 on these rows.
- Store the platform-line split once at issue time (`sales_return_sale_line`). The file, the report views and the labels all read from it.
- Do not add a new order status. Labels are derived from the issued return.
- Allow DELIVERED → CANCELLED only while the DO has no invoice.
- Lazada: show the label and a warning, but still allow saving. The all-orders file also gets the negative rows.

## Next steps
Phase 1 (data model, split function, backfill command), then labels and cancel, the Shop Online file, report views, labels in the other modules, docs and acceptance. Tell the accountants about negative rows before the first paste.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
