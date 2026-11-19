---
title: Làm Tax Invoice Doc. từ zrsd003 cho file Shop Online
date: 2026-11-19
summary: Phase 1-4 xong và tài liệu đã sửa; còn deploy và chạy thử ZRSD003 trên production
---

# Làm Tax Invoice Doc. từ zrsd003

## What happened
Làm theo plan `plans/261119-0605-zrsd003-tax-invoice-in-history/plan.md`. Thêm bảng `sap_tax_invoice` (migration `0008_sap_tax_invoice`), `read_zrsd003` và `ingest_zrsd003` dùng chung cho upload tay ở Báo cáo SAP và job robot `read_zrsd003`. File lịch sử Shop Online có cột 19 `Tax Invoice Doc.` (định dạng text); đơn có DO mà chưa có hóa đơn bị chặn, và trang có nút xếp robot đọc zrsd003 từ ngày đặt sớm nhất của các đơn chờ tới hôm nay.

Nhập thử `docs/zrsd003.XLSX` trên database test (rollback): giữ 243 dòng (Shopee 179, TikTok 39, Lazada 25), bỏ 407 dòng khách khác, nhập lại không đổi số dòng, DO `1910061168` ra `7914`. Bộ test: 399 passed, `ruff check` sạch.

## Decision
Upsert dùng executemany thay cho một câu INSERT nhiều dòng, để lần đọc đầu trên production với khoảng ngày dài không chạm giới hạn tham số của PostgreSQL. Bước Enter sau Sales Org và Sales Office là helper `confirm` trong `report_screen.py`; test fake SAP kiểm thứ tự ô đã điền tại mỗi lần Enter.

## Next steps
Deploy theo `docs/deployment-guide.md` (sao lưu DB trước migrate), chạy `read_zrsd003` một lần cho khoảng rộng, đối chiếu 3 DO với SAP và ghi biên bản live-check. Nếu ZRSD003 báo câu "không có dữ liệu" khác "No data to display", thêm vào `NO_DATA_TEXT`.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
