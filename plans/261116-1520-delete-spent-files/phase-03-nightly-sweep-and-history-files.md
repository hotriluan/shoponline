---
phase: 3
title: "Quét file hằng đêm, file Shop Online, log retention"
status: completed
---

# Phase 03: Quét file hằng đêm, file Shop Online, log retention

Quyết định của chủ dự án (2026-11-16): lượt quét file xóa thật ngay, không chờ `--apply`; file Shop Online bị xóa khi mọi đơn trong file đã được xác nhận.

## Quy tắc giữ (một nơi duy nhất)

Đặt trong [retention.py](../../src/shoponline/maintenance/retention.py), dùng chung cho xóa ngay (phase 01, 02) và quét đêm:

| Thư mục | Giữ khi |
|---|---|
| `uploads/` | zrsd004 của đợt `OPEN` (nguồn hoặc file robot đọc); zrsd004 upload tay chưa thuộc đợt `OPEN`/`FINALIZED` và chưa quá `retention_days` |
| `exports/` | file kế toán mà một đợt trỏ tới (`accounting_run.generated_file_id`); file Shop Online còn ít nhất một đơn chưa được xác nhận (`sales_history_file_order` không có trong `sales_history_exported`) |
| `robot-work/job-N` | việc chưa `DONE` và thư mục chưa quá `evidence_keep_days` |
| `robot-evidence/` | chưa quá `evidence_keep_days` (dùng `evidence.prune` sẵn có) |

File không có quy tắc nào giữ và có thời điểm sửa cũ hơn 1 giờ thì bị xóa. Mốc 1 giờ tránh file đang được ghi trước khi commit.

## Files

- Sửa: [retention.py](../../src/shoponline/maintenance/retention.py): thay mốc 90 ngày cho file bằng quy tắc giữ ở trên; tách phần file khỏi phần dữ liệu khách.
- Sửa: [cli.py](../../src/shoponline/cli.py) `_cmd_retention`: luôn xóa file theo quy tắc giữ; `--apply` chỉ còn quyết việc xóa tên và địa chỉ khách. Ghi `retention.log` qua `RotatingFileHandler` như các log khác (không còn `open("a")`).
- Sửa: [sales_history.py](../../src/shoponline/web/routes/sales_history.py) `confirm_file`: sau commit, gọi hàm xóa của retention cho các file Shop Online đã được xác nhận hết (cả file khác có cùng đơn). Thông báo "File đã bị xóa theo thời hạn lưu" đổi thành "File đã bị xóa sau khi xác nhận đã dán".
- Không đổi `register-tasks.ps1`: tác vụ `shoponline-retention` đang chạy `shoponline retention` hằng đêm, nay lệnh đó tự xóa file.
- Test: `tests/maintenance/test_retention.py`, `tests/web/` (trang Shop Online), `tests/test_cli_logging.py`.

## Steps

1. Viết hàm quy tắc giữ trả về tập đường dẫn được giữ cho từng thư mục; `_kept_files` cũ gộp vào đây.
2. Quét: liệt kê file trong bốn thư mục, bỏ file được giữ hoặc mới hơn 1 giờ, xóa phần còn lại, xóa thư mục `job-N` rỗng. Ghi số lượng vào `retention.log` và `event_log`.
3. `_cmd_retention`: quét file luôn chạy thật; phần khách vẫn chỉ liệt kê nếu không có `--apply`.
4. `confirm_file`: xóa file đã xác nhận hết.
5. Test: mỗi dòng của bảng quy tắc (giữ và xóa); file mồ côi bị xóa; file mới hơn 1 giờ còn; không có `--apply` thì `customer_info` không đổi nhưng file vẫn bị xóa; `retention.log` xoay vòng.

## Validation

```
uv run pytest tests/maintenance tests/web tests/test_cli_logging.py
uv run ruff check
```

## Risk và rollback

- Đây là lần đầu lệnh hằng đêm xóa thật trên production. Trước khi deploy, chạy tay một lượt trên bản sao dữ liệu hoặc đọc kỹ danh sách bằng test; sau deploy đọc `retention.log` sáng hôm sau.
- Thay đổi hành vi công khai: `shoponline retention` không có `--apply` nay vẫn xóa file. Ghi rõ trong tài liệu (phase 05).
- Rollback: revert commit. File đã xóa không lấy lại được.
