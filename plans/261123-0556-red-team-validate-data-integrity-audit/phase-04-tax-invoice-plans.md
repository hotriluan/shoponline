---
phase: 4
title: "Phase 4: Hóa đơn zrsd003 (261119-0605, 261119-0854)"
status: completed
priority: P1
effort: 4h
dependencies: [1]
---

# Phase 4: Hóa đơn zrsd003

## Overview

Red team và validate hai plan về Tax Invoice bằng cách soi mã: `261119-0605-zrsd003-tax-invoice-in-history` (6 phase, 4 lens) và `261119-0854-month-pick-zrsd003-read` (2 phase, 2 lens). Phase này phụ trách luồng 5 (hóa đơn).

## Files

- Đọc plan: hai thư mục plan trên; `plans/reports/brainstorm-261119-1208-zrsd003-tax-invoice-in-history.md`; các journal ngày 2026-11-19 về zrsd003
- Đọc mã: `src/shoponline/saprobot/transactions/read_zrsd003.py`, `src/shoponline/importers/sap_reports.py` (phần zrsd003), `src/shoponline/sapjobs/report_requests.py`, `src/shoponline/web/routes/sales_history.py` (khoảng đọc, chặn đơn chờ hóa đơn), `src/shoponline/web/routes/sap_reports.py` (upload tay), model `SapTaxInvoice`, `migrations/versions/0008_sap_tax_invoice.py`
- Đọc test: `tests/importers/test_zrsd003.py`, `tests/saprobot/test_report_reads.py`, `tests/web/test_sales_history_routes.py`
- Đọc mẫu: `docs/zrsd003.XLSX` (chỉ xem tên cột và kiểu dữ liệu; không chép dữ liệu khách)
- Sửa: `plan.md` của hai plan
- Tạo: `plans/reports/data-integrity-audit-261123-<HHmm>-tax-invoice.md`

## Câu hỏi trùng/sót phải trả lời bằng bằng chứng

1. `sap_tax_invoice` khóa theo `delivery`. Một DO có hai hóa đơn (hủy rồi xuất lại, hoặc xuất tách) thì giữ hóa đơn nào? Có thể giữ nhầm hóa đơn đã hủy không? zrsd003 có cột trạng thái hoặc hóa đơn hủy không?
2. Upload tay và robot cùng ghi một DO: bên nào thắng, và có ghi đè hóa đơn đúng bằng hóa đơn sai không?
3. Khoảng đọc `min(ngày 1 của tháng, ngày đặt sớm nhất của đơn tồn)` → hôm nay: có đơn nào có hóa đơn nằm ngoài khoảng này không (ví dụ hóa đơn xuất trước ngày đặt, hoặc DO của tháng trước còn tồn mà không thuộc đơn chờ)? zrsd003 không lọc theo khách: dòng của khách ngoài ba sàn có bị ghi vào bảng không, và có hại không?
4. Khóa chống trùng việc đọc theo khoảng ngày (`report_requests.py`): hai khoảng chồng nhau có tạo hai việc đọc không, và có hại không?
5. Một đơn có nhiều DO: cột 19 lấy hóa đơn của DO nào? Đơn có một DO đã có hóa đơn và một DO chưa có thì có bị coi là đủ không?

## Implementation Steps

1. Đọc và lập bảng tiêu chí ↔ bằng chứng cho hai plan.
2. Red team `261119-0605` (4 lens) và `261119-0854` (2 lens), cộng lens trùng/sót; phân xử.
3. Test tái hiện cho phát hiện High trở lên; viết SQL cho câu hỏi cần dữ liệu thật (ví dụ: DO trong `sap_so_ref` của đơn đã xác nhận mà không có dòng `sap_tax_invoice`; hóa đơn có `delivery` không khớp DO nào của ba sàn).
4. Cổng duyệt red team, ghi `## Red Team Review` vào từng plan.
5. Validate cả hai plan; với `261119-0854`, tiêu chí "kiểm production chờ deploy" ghi VERIFIED nếu journal hoặc production có bằng chứng lần đọc thật, nếu không thì ghi UNVERIFIED. Ghi `## Validation Log`.
6. Ghi file phát hiện.

## Todo

- [x] Bảng tiêu chí ↔ bằng chứng (2 plan)
- [x] Red team và phân xử
- [x] Test tái hiện và SQL
- [x] Cổng duyệt, ghi Red Team Review
- [x] Validate và ghi Validation Log
- [x] File phát hiện

## Success Criteria

- 5 câu hỏi đều có câu trả lời kèm bằng chứng.
- Hai plan có các mục mới; không có thay đổi mã.
