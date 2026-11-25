---
title: "Plan revision: return documents format fidelity"
date: 2026-11-23
summary: "Excel D14 uses SAP name; generated files must match sample formatting 100%"
---

# Plan revision: return documents format fidelity

## What happened
User corrected the plan: Excel REQUEST to RETURN GOODS D14 uses the SAP name; the Word adjustment record keeps the invoice name from the PDF-fed master. Generated files must match the samples in docs/bbdchd 100%% in layout and formatting.

## Decision
Keep .xlsx and black dynamic text (user confirmed). Templates are made by editing the originals in place (Excel converted by Excel itself). Added tests/support/format_compare.py to prove Word paragraph/run/table/section and Excel column/row/merge/style/page-setup/image equality, used in phases 1, 4, 6. Excel COM filling of the original .xls was considered and rejected (needs Excel on the web host).

## Next steps
Phase 1 spike decides whether openpyxl keeps the Excel logo; if not, stop and ask.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
