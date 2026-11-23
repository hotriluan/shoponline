---
title: "Phase 1: Gói A — dọn file an toàn"
status: completed
priority: P1
effort: 1d
dependencies: []
---

# Phase 1: Gói A — dọn file an toàn

## Overview

Làm cho tác vụ xóa file đêm (`shoponline retention --apply`) chỉ xóa khi chắc chắn, và không xóa file kế toán đã gửi. Gói này phải xong **trước khi bật `--apply` trên production**.

Bằng chứng: [báo cáo dọn file](../reports/data-integrity-audit-261123-1320-deletion-machine.md), các mục D1–D7, và Red Team Review trong plan `261116-1520`.

## Phát hiện trong gói

| Mã | Mức | Vấn đề | Mã nguồn | Sửa đề xuất |
|---|---|---|---|---|
| D1 | Medium | Đường dẫn tuyệt đối trong DB so với `SHOPONLINE_DATA_DIR` hiện tại: DB khôi phục lên máy có thư mục dữ liệu khác thì quy tắc giữ không khớp file nào và mọi file quá 1 giờ bị xóa | `maintenance/retention.py` (hàm quét file) | Trước khi xóa, nếu có dòng `generated_file`/`import_batch` trỏ ra ngoài thư mục dữ liệu hiện tại thì dừng, báo lỗi và không xóa gì |
| D2 | Medium | File kế toán cũ không thuộc đợt nào (sinh trước khi có đợt) không có quy tắc giữ, lượt quét đầu xóa chúng; đó là bản đã gửi kế toán của sổ nền | `retention.py:155-157` | Giữ mọi `generated_file.kind = accounting_file` không bị đợt nào hủy hoặc gỡ chốt; chỉ xóa file của đợt `CANCELLED`/`REVOKED` theo quy tắc hiện có |
| D3 | Medium | File kế toán đã chốt chỉ nằm trong `exports/`; sao lưu hằng ngày `db` không chứa, chỉ bản `full` hằng tuần: mất ổ giữa hai bản `full` thì mất tới 6 ngày file | `backup/schedule.py:15`, `backup/archive.py:3-10` | **Quyết định chủ dự án** (xem dưới) |
| D4 | Medium | Lệnh quét đêm không đọc `maintenance.json`, không tạm dừng khi khôi phục hoặc deploy: khôi phục bản `db` rồi quét sẽ xóa file mới hơn bản đó | `retention.py` (điểm vào lệnh), cơ chế `maintenance.json` của `backup/restore.py` | Lệnh thoát sớm (mã thoát 0, ghi log) khi `maintenance.json` đang bật |
| D5 | Medium | "Gỡ xác nhận" file lịch sử sau khi tên khách đã bị xóa làm đơn bị chặn mãi vì "Thiếu tên khách" | `web/routes/sales_history.py:414-432`, `retention.py:103-105` | Từ chối gỡ xác nhận (kèm lý do) khi tên khách của đơn nào trong file đã bị xóa |
| D7 | Low | `path.stat()` sau `is_file()`: file biến mất giữa hai lệnh làm cả lượt quét dừng | `retention.py:229-231` | Bắt `FileNotFoundError`, bỏ qua file đó, tiếp tục |
| D6 | Low | `discard_unused` không có thời gian ân hạn: hai upload cùng nội dung gần như cùng lúc dùng chung `<sha256>.xlsx`, một bên báo "không có file" | `retention.py:186-205`, `web/uploads.py:49-53` | Làm nếu dưới 30 phút (dùng `GRACE` như lượt quét); nếu không thì chấp nhận rủi ro, ghi sổ tay |

### Quyết định D3 (chủ dự án chọn phương án 1, 2026-11-23)

- **Phương án 1 (đề xuất):** thêm file kế toán đã chốt (`generated_file.kind = accounting_file` của đợt `FINALIZED`) vào bản `db` hằng ngày. File nhỏ; đổi nội dung của một loại sao lưu (cần cập nhật `docs/` sao lưu).
- **Phương án 2:** chấp nhận hở tối đa 6 ngày, ghi vào tài liệu vận hành. Không đổi mã; rủi ro là mất ổ đúng lúc.
- Phụ thuộc vào giả định: mất ổ đĩa dữ liệu và cùng lúc chưa có bản `full` mới là hiếm. Hết đúng khi tần suất chốt kế toán tăng hoặc ổ không có dự phòng.

## Files

- Sửa: `src/shoponline/maintenance/retention.py`, `src/shoponline/web/routes/sales_history.py`; nếu chọn phương án 1: `src/shoponline/backup/archive.py` (và `schedule.py` nếu cần)
- Test: `tests/maintenance/test_retention.py`, `tests/web/test_sales_history_routes.py`, `tests/backup/` (nếu chọn phương án 1)
- Tài liệu (chỉ khi hành vi đổi): `docs/security-and-data-retention.md`, `docs/deployment-guide.md`

## Implementation Steps

1. Viết test tái hiện cho D1, D2, D4, D5, D7 (dùng thư mục dữ liệu tạm; không bao giờ chạy trên dữ liệu thật). Xác nhận fail.
2. Sửa D1, D2, D4, D5, D7 theo bảng. Mọi thay đổi theo hướng giữ lại hoặc dừng sớm.
3. Chốt quyết định D3 với chủ dự án rồi làm theo phương án đã chọn.
4. D6: đo thời gian; làm hoặc ghi chấp nhận rủi ro.
5. Chạy `uv run pytest tests/maintenance tests/backup -q`, rồi `tests/web/test_sales_history_routes.py`, từng bộ một; `ruff` sạch.
6. Cập nhật bảng theo dõi và tài liệu chỉ ở chỗ hành vi đổi. Commit.

## Todo

- [x] Test tái hiện D1, D2, D4, D5, D7 (fail trước khi sửa)
- [x] Sửa D1, D2, D4, D5, D7
- [x] Chốt D3 với chủ dự án và làm
- [x] Quyết D6
- [x] Test từng bộ một và `ruff` sạch
- [x] Cập nhật bảng theo dõi, tài liệu, commit

## Success Criteria

- Mỗi phát hiện có trạng thái cuối. Test của D1, D2, D4, D5, D7 fail trước và pass sau.
- `shoponline retention` không xóa gì khi đường dẫn DB không thuộc thư mục dữ liệu hoặc khi bảo trì đang bật.
- File kế toán không thuộc đợt nào không bị xóa.
- Ghi nhận trong báo cáo rằng gói A xong, mở đường cho việc bật `--apply`.

## Risk

- **Sửa sai làm xóa nhiều hơn:** đã chọn các sửa thiên về giữ lại; test chạy trên thư mục tạm; không chạy `--apply` thật trong lúc làm.
- **D2 giữ quá nhiều file:** chấp nhận; file kế toán nhỏ, và xóa muộn an toàn hơn xóa nhầm.

## Rollback

Mỗi thay đổi là một commit riêng; revert commit nếu gây lỗi. Không có thay đổi schema.
