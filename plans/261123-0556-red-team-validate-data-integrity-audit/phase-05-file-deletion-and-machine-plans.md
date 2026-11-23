---
phase: 5
title: "Phase 5: Dọn file và máy chạy thật (261116-1520, 261113-1012, 261116-0944)"
status: completed
priority: P2
effort: 4h
dependencies: [1]
---

# Phase 5: Dọn file và máy chạy thật

## Overview

Red team và validate `261116-1520-delete-spent-files` đầy đủ (5 phase, 3 lens) vì xóa sớm là nguồn sót dữ liệu. `261113-1012-sap-connection-settings-web` và `261116-0944-win10-production-machine-hidden-tasks` chỉ red team nhẹ: 1 reviewer, lens trùng/sót dữ liệu. Phase này phụ trách phần xóa của luồng 7.

## Files

- Đọc plan: ba thư mục plan trên; journal 2026-11-13 về xóa theo thời hạn, 2026-11-16 về dọn file và chuyển máy
- Đọc mã:
  - Xóa: `src/shoponline/maintenance/retention.py`, `src/shoponline/web/uploads.py`, `src/shoponline/backup/retention.py`, `src/shoponline/backup/maintenance.py`, `src/shoponline/cli.py` (lệnh sweep), `scripts/windows/register-tasks.ps1`
  - Máy và tác vụ: `scripts/windows/{register-tasks,service-control,setup-production-machine,update-production,settings}.ps1`, `.github/workflows/deploy.yml`, `src/shoponline/saprobot/worker.py` (khóa một robot), `src/shoponline/sapjobs/{queue,sap_settings}.py`
- Đọc test: `tests/maintenance/test_retention.py`, `tests/web/test_uploads.py`, `tests/backup/test_naming_retention_schedule.py`, `tests/saprobot/test_worker.py`, `tests/sapjobs/test_queue.py`, `tests/sapjobs/test_sap_settings.py`
- Đọc tài liệu: `docs/security-and-data-retention.md`, `docs/operations-runbook.md`
- Sửa: `plan.md` của ba plan
- Tạo: `plans/reports/data-integrity-audit-261123-<HHmm>-deletion-machine.md`

## Câu hỏi trùng/sót phải trả lời bằng bằng chứng

1. Retention 90 ngày xóa gì (dòng DB, tên khách, file)? Có xóa dữ liệu của đơn **chưa** xuất file lịch sử, chưa có hóa đơn, chưa có tiền vô, hoặc chưa gửi kế toán không? Điều kiện xóa dựa trên trạng thái nào?
2. File upload bị xóa "khi hết dùng": nếu việc nhập lỗi giữa chừng, file có bị xóa trước khi người dùng nhập lại không? File gốc quyết toán hoặc zrsd003 có được giữ đủ lâu để gỡ một lần nhập sai không?
3. Quét file hằng đêm: có xóa file Shop Online đã tải nhưng chưa xác nhận không?
4. Tác vụ hẹn giờ (robot, sweep, sao lưu) chạy hai bản cùng lúc sau khi chuyển máy hoặc khởi động lại: có khóa không? Máy cũ `Alkana_IT` đã tắt hẳn chưa, có khả năng hai máy cùng ghi một DB không?
5. Chuyển máy: 21 bảng khớp số dòng, nhưng bảng thuộc schema `ops` và thư mục dữ liệu (uploads, file đã tạo) có được chuyển đủ không?

## Implementation Steps

1. Đọc và lập bảng tiêu chí ↔ bằng chứng cho `261116-1520`.
2. Red team `261116-1520` với 3 lens cộng lens trùng/sót; phân xử; test tái hiện cho phát hiện High trở lên.
3. Red team nhẹ hai plan còn lại: 1 reviewer, chỉ câu hỏi 4 và 5. Ghi vào từng plan `## Red Team Review` với dòng đầu "Red team nhẹ: chỉ mất/trùng dữ liệu (quyết định 2026-11-23)".
4. Viết SQL cho câu hỏi cần dữ liệu thật (ví dụ: đơn đã bị xóa tên khách mà chưa có dòng `sales_history_exported`; số dòng `generated_file` trỏ tới file không còn trên đĩa, nếu kiểm được bằng lệnh liệt kê chỉ đọc trên máy chạy thật).
5. Cổng duyệt red team với chủ dự án; validate `261116-1520` đầy đủ, hai plan nhẹ chỉ kiểm các tiêu chí liên quan câu hỏi 4 và 5. Ghi `## Validation Log` cho cả ba.
6. Ghi file phát hiện.

## Todo

- [x] Red team đầy đủ `261116-1520`
- [x] Red team nhẹ `261113-1012`, `261116-0944`
- [x] Test tái hiện và SQL
- [x] Cổng duyệt, ghi Red Team Review (3 plan)
- [x] Validate (3 plan, hai plan nhẹ giới hạn phạm vi)
- [x] File phát hiện

## Success Criteria

- 5 câu hỏi đều có câu trả lời kèm bằng chứng.
- Ba plan có các mục mới; hai plan nhẹ ghi rõ phạm vi rút gọn.
- Không xóa, không sửa file nào trên máy chạy thật; chỉ liệt kê.
