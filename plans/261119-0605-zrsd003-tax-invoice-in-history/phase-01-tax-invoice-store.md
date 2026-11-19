---
phase: 1
title: "Bảng hóa đơn và bộ nhập zrsd003"
status: completed
priority: P2
effort: "4h"
dependencies: []
---

# Phase 1: Bảng hóa đơn và bộ nhập zrsd003

## Goal
Lưu số hóa đơn của các DO thuộc khách SAP của sàn, qua một hàm nhập dùng chung cho upload tay và robot.

## Context
- `docs/zrsd003.XLSX`: sheet `Sheet1`, header dòng 1, 16 cột: `Billing Type`, `Sales Office`, `Sloc`, `Billing Date`, `Billing Doc.`, `OD Doc.`, `Tax Invoice Doc.`, `Bill-to`, `Name`, `VAT Reg. No.`, `Tax Classification`, `Exch. Rate-Acct.`, `Doc. Currency`, `Net Value`, `Net Value (VND)`, `Tax (VND)`. 650 dòng, 650 `OD Doc.` khác nhau, không có dòng tổng.
- Khuôn có sẵn: `read_zrsd004` (`importers/sap_reports.py:111`), `ingest_zrsd004` (`reconcile/report_ingest.py`), migration mới nhất `migrations/versions/0007_sales_history.py`.

## Files to Create / Modify
- Modify: `src/shoponline/db/models.py` — thêm `SapTaxInvoice`.
- Create: `migrations/versions/0008_sap_tax_invoice.py`.
- Modify: `src/shoponline/importers/sap_reports.py` — `ZRSD003_REQUIRED`, `TaxInvoiceRow`, `read_zrsd003`.
- Modify: `src/shoponline/reconcile/report_ingest.py` — `ingest_zrsd003` (cập nhật docstring module).
- Modify: `src/shoponline/maintenance/retention.py` — docstring: zrsd003 đọc một lần lúc nhập.
- Create: `tests/importers/test_zrsd003.py` (hoặc thêm vào test sap_reports hiện có nếu có).

## Tasks & Steps
1. Model `SapTaxInvoice` (`sap_tax_invoice`): `delivery` String(20) PK; `tax_invoice_doc` String(20); `billing_doc` String(20); `billing_date` Date; `bill_to` String(20); `import_batch_id` FK `import_batch.id` nullable; `updated_at` như `SapSoRef`.
2. Migration `0008_sap_tax_invoice` tạo bảng; downgrade drop bảng.
3. `read_zrsd003(source)`: `read_table(required=("Billing Type", "Billing Date", "OD Doc.", "Tax Invoice Doc.", "Bill-to"))`; bỏ dòng thiếu `OD Doc.`; chỉ nhận `Billing Type == "ZBA1"`; dòng thiếu `Tax Invoice Doc.` hoặc ngày sai thì gom lỗi và `FileRejected`; file không còn dòng nào thì `FileRejected("File zrsd003 không có hóa đơn nào")`. Giữ các mã dạng text (không ép số).
4. `ingest_zrsd003(session, record, actor)`: đọc file, lấy tập `PlatformSetting.sap_customer`, giữ dòng có `bill_to` thuộc tập đó, upsert theo `delivery` (`insert … on_conflict_do_update`), ghi `record.new_count`/`updated_count`, trả `TaxInvoiceImport(kept, skipped_other_customers, new, updated)`. Không lưu `Name`, `VAT Reg. No.`, giá trị tiền.
5. Test: đọc file mẫu (copy vào `tests/fixtures` chỉ các dòng sàn + vài dòng khách giả, không đưa tên khách thật vào git); lọc Bill-to; upsert lần hai không tạo trùng và cập nhật số hóa đơn đổi; thiếu cột bị từ chối; dòng không phải ZBA1 bị bỏ.

## Verification
- `uv run pytest tests/importers tests/reconcile -q`
- `uv run alembic upgrade head` rồi `downgrade -1` trên DB dev (sao lưu trước).

## Risks
- Fixture không được chứa tên/MST khách doanh nghiệp thật: dựng fixture bằng openpyxl trong test.
