---
title: "Plan: invoice return documents"
date: 2026-11-23
summary: "Planned auto-generated invoice adjustment record and return request from DB, zrsd003 and a PDF-fed invoice-text master"
---

# Plan: invoice return documents

## What happened
Brainstormed and planned the "return after invoice" feature: generate the invoice adjustment record (Word) and REQUEST to RETURN GOODS (Excel) from existing data. Plan: plans/261123-0950-invoice-return-documents (6 phases). Design report: plans/reports/brainstorm-261123-1630-invoice-return-documents.md.

Evidence gathered: zrsd003 is header-level only (invoice no, DO, Net Value (VND), Tax (VND)); sap_tax_invoice does not store amounts yet. The hand-typed sample Word disagreed with the real invoice (item name and unit), so invoice text must come from a source tied to the invoice. pdfplumber reads the Bkav invoice table into clean columns; pypdf merges name and unit.

## Decision
- Master invoice_item_text (material -> invoice name, invoice unit, stock unit), filled from the order's Bkav PDF when a material is missing, editable by hand.
- Amounts from zrsd003 (two new columns), line nets derived from SO lines and balanced to the invoice total; PDF uploads cross-check the calculation.
- Number NNN/MM.YYYY ALK-KH.STMĐT, reset yearly, start number entered once by CLI; one non-void return per order; partial returns allowed.
- Output in black text, .xlsx instead of .xls; partial return shows the full invoice as "before adjustment".
- Return snapshot (buyer name, address) and files kept beyond the 90-day retention.

## Next steps
Phase 1 first: convert templates and prove openpyxl keeps the Excel logo/print setup and docxtpl placeholders stay in single runs. Then data model, PDF reader, core, web, docs.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
