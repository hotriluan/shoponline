---
phase: 5
title: "Tài liệu và chạy thử production"
status: in-progress
priority: P2
effort: "2h"
dependencies: [2, 3, 4]
---

# Phase 5: Tài liệu và chạy thử production

## Goal
Tài liệu vận hành nói đúng luồng mới; robot đọc ZRSD003 thật một lần trên production và file lịch sử ra cột 19 đúng.

## Files to Create / Modify
- Modify: `docs/daily-operations.md` — mục "Xuất dòng cho file Shop Online": 19 cột, đơn chờ hóa đơn, nút robot, upload tay dự phòng.
- Modify: `docs/robot-runbook.md` — ZRSD003: bộ lọc, điều kiện variant mặc định (Exist/SD), xử lý khi job FAILED vì câu "không có dữ liệu" khác.
- Modify: `docs/security-and-data-retention.md` — zrsd003 chứa dữ liệu khách doanh nghiệp, chỉ lưu dòng sàn, file gốc xóa ngay.
- Modify: `docs/system-architecture.md` — bảng `sap_tax_invoice` và job `read_zrsd003`, nếu tài liệu liệt kê bảng/job.
- Create: `plans/reports/live-check-<timestamp>-zrsd003-tax-invoice.md` — biên bản chạy thử.

## Tasks & Steps
1. Đọc từng tài liệu trước khi sửa; chỉ sửa phần bị ảnh hưởng.
2. Deploy theo `docs/deployment-guide.md` (script deploy sao lưu DB trước `migrate`).
3. Trên production: xếp zrsd003 từ ngày đặt sớm nhất của đơn chờ tới hôm nay; ghi số dòng giữ, số dòng bỏ qua.
4. So 3 DO bất kỳ với SAP (VF03 / ZRSD003 trên màn hình); tải file lịch sử nháp, kiểm cột 19.
5. Nếu gặp câu "không có dữ liệu" khác, chụp và thêm vào `NO_DATA_TEXT` thành phase sửa riêng.

## Verification
- Biên bản có số liệu thật, ảnh hoặc mô tả đối chiếu 3 DO.
