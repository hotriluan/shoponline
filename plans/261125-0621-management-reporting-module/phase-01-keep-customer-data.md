---
phase: 1
title: "Giữ dữ liệu khách vĩnh viễn"
status: completed
priority: P1
effort: "3h"
dependencies: []
---

# Phase 1: Giữ dữ liệu khách vĩnh viễn

## Goal

Hệ thống không còn xóa tên và địa chỉ khách (`customer_info`) theo thời hạn; việc xóa file hết dùng vẫn chạy như cũ.

## Bối cảnh

- Kiểm tra ngày 2026-11-25 (đã kiểm lại trực tiếp trên máy chạy thật, <!-- Updated: Validation Session 2 - số liệu production thay cho số dev -->`AlkanaDuongPC`, `C:\shoponline`): database chạy thật chưa từng xóa dữ liệu khách. Tác vụ `shoponline-retention` (trạng thái Ready) chạy `retention` không có `--apply`. `event_log` có 7 dòng `retention_*`, tất cả là `retention_files` (dọn file, từ 17/11 đến 25/11), không có `retention_purge`. Có 181 đơn và 181 dòng `customer_info`, không có dòng nào mồ côi. 23 đơn chưa có tên khách (Shopee 16, TikTok 7); vì không có sự kiện xóa nên đây là đơn nạp từ file thiếu tên, không phải do retention. Không có gì phải khôi phục.
- Phần xóa nằm ở `find_expired` và `apply` trong [retention.py](../../src/shoponline/maintenance/retention.py); lệnh ở `_cmd_retention` trong [cli.py](../../src/shoponline/cli.py).
- `settings.retention_days` còn dùng trong `kept_files` (thời gian giữ file `zrsd004` tải tay chờ gắn vào đợt), nên biến `SHOPONLINE_RETENTION_DAYS` vẫn giữ, chỉ đổi ý nghĩa.
- `register-tasks.ps1` giữ lại tham số `retention --apply` của tác vụ đã có. Vì vậy `--apply` phải vẫn được chấp nhận để tác vụ cũ không lỗi.

## Files to Create / Modify

- Modify: `src/shoponline/maintenance/retention.py`: bỏ `RetentionPlan`, `find_expired`, `apply` và đoạn docstring "Customer data"; thêm một câu nói rõ dữ liệu khách được giữ vĩnh viễn (chốt 2026-11-25).
- Modify: `src/shoponline/cli.py`: `_cmd_retention` chỉ dọn file. `--apply` vẫn được nhận, không làm gì thêm và ghi một dòng log "--apply không còn tác dụng: dữ liệu khách được giữ". Sửa help của tham số.
- Modify: `scripts/windows/register-tasks.ps1`: tác vụ luôn đăng ký `retention` không có `--apply`; switch `-RetentionApply` vẫn nhận nhưng in cảnh báo không còn tác dụng; bỏ đoạn giữ lại `retention --apply` từ tác vụ cũ; sửa dòng tóm tắt `$retentionMode`.
- Modify: `src/shoponline/config.py`: comment của `retention_days` chỉ còn nói về file.
- Modify: `tests/maintenance/test_retention.py`, `tests/test_cli_logging.py`: bỏ test xóa dữ liệu khách; thêm test `retention --apply` để nguyên `customer_info` (kể cả đơn cũ hơn thời hạn và đơn `CANCELLED`).
- Modify (tài liệu, sửa ngay trong phase này để không lệch với code): `docs/security-and-data-retention.md`, `README.md` (bảng biến và bảng lệnh), `docs/operations-runbook.md`, `docs/deployment-guide.md`; rà thêm `scripts/windows/server-export.ps1` và `update-production.ps1` xem có nhắc chế độ xóa dữ liệu khách không.

## Tasks & Steps

- [x] Gỡ phần xóa dữ liệu khách trong `retention.py`, giữ nguyên `kept_files`, `sweep_files`, `discard_unused`, `foreign_paths`.
- [x] Sửa `_cmd_retention`: log chỉ còn phần file; `--apply` thành no-op có log.
- [x] Sửa `register-tasks.ps1` như trên.
- [x] Sửa test.
- [x] Sửa tài liệu. `security-and-data-retention.md` ghi: "Chốt ngày 2026-11-25: tên, địa chỉ khách giữ vĩnh viễn để phục vụ báo cáo quản lý theo khách và tỉnh. Quyết định của chủ dự án; lưu ý Nghị định 13/2023." `SHOPONLINE_RETENTION_DAYS` chỉ còn là số ngày giữ file `zrsd004` tải tay chờ gắn.
- [ ] Trên máy chạy thật, sau deploy: chạy `register-tasks.ps1` lại (tác vụ đang Disabled thì giữ Disabled) để tham số khớp.

## Verification

- `uv run pytest tests/maintenance tests/test_cli_logging.py`
- `uv run ruff check`
- Grep `find_expired|retention_purge|customer_orders` trong `src/` không còn kết quả.

## Risk

- Lệnh chạy tay cũ `retention --apply` vẫn chạy và chỉ dọn file. Đây là hành vi mong muốn, không phá tác vụ cũ.

## Kết quả (2026-11-25)

Đã làm: bỏ `RetentionPlan`, `find_expired`, `apply` khỏi `retention.py`; `_cmd_retention` chỉ dọn file và `--apply` là no-op có log; `register-tasks.ps1` luôn đăng ký `retention` không `--apply`; sửa test và tài liệu (`security-and-data-retention.md`, README, runbook, deployment-guide, system-architecture, daily-operations). Thêm một thay đổi ngoài kế hoạch: thông báo từ chối "Gỡ xác nhận" trong `web/routes/sales_history.py` không còn nói "đã bị xóa theo thời hạn lưu". Còn lại: chạy lại `register-tasks.ps1` trên máy chạy thật sau deploy (việc của chủ dự án).
