---
phase: 4
title: "Trang xuất file và xác nhận"
status: completed
priority: P1
effort: "5h"
dependencies: [2, 3]
---

# Phase 4: Trang xuất file và xác nhận

## Goal
Trang "File Shop Online" hiện các đơn chờ xuất và đơn bị chặn, cho tải file khi không còn đơn bị chặn, và cho admin xác nhận hay gỡ xác nhận từng file đã tải.

## Bối cảnh
- Tải file đã lưu: [batches.py:118-140](../../src/shoponline/web/routes/batches.py) dùng `save_generated` rồi `FileResponse`, quyền `current_user`.
- `save_generated` ([uploads.py:59](../../src/shoponline/web/uploads.py)) trả `GeneratedFile` đã flush, tên file trên đĩa có hậu tố ngẫu nhiên.
- `today_vn()` ở [clock.py](../../src/shoponline/clock.py); `log_event` ở [states.py:47](../../src/shoponline/domain/states.py).
- Trang Khách hàng sửa tên và địa chỉ: `/customers?platform=<sàn>&missing=true` ([customers.py](../../src/shoponline/web/routes/customers.py)).
- Phase 2 đã sửa `app.py` và `base.html`; phase này sửa tiếp hai file đó.

## Files to Create / Modify
- Create: `src/shoponline/web/routes/sales_history.py`.
- Create: `src/shoponline/web/templates/sales_history.html`.
- Modify: `src/shoponline/web/app.py`: thêm module vào tuple router.
- Modify: `src/shoponline/web/templates/base.html`: mục menu "File Shop Online".
- Create: `tests/web/test_sales_history_routes.py`.

## Tasks & Steps
1. `GET /sales-history?until=` (mọi người đăng nhập): mặc định `until = today_vn()`. Gọi `collect_rows`, hiện số đơn và số dòng chờ xuất, và bảng đơn bị chặn (sàn, mã đơn, ngày đặt, lý do). Mỗi lý do có link sửa: thiếu tên hoặc địa chỉ tới `/customers?platform=…&missing=true`, thiếu tên báo cáo tới `/report-names?missing=true`. <!-- Updated: Validation Session 1 - pending orders, no date_from -->
2. Nút "Tải file" chỉ hiện khi không có đơn bị chặn và có ít nhất một dòng.
3. `GET /sales-history/file?until=` (`current_user`): gọi lại `collect_rows`; còn đơn bị chặn hoặc không có dòng thì chuyển về trang kèm thông báo. Ngược lại dựng workbook, lưu bằng `save_generated(kind="sales_history")`, ghi một dòng `sales_history_file_order` cho mỗi đơn trong `order_ids`, commit, trả `FileResponse` với `history_file_name(today_vn())`.
4. Bảng "File đã tải" trên trang: 20 file `sales_history` gần nhất (thời gian, người tải, số đơn, trạng thái: chưa xác nhận / đã xác nhận N đơn), link tải lại file đã lưu (`FileResponse` theo `stored_path`, không dựng lại).
5. `POST /sales-history/files/{file_id}/confirm` (`require_admin`): thêm dòng `sales_history_exported` cho các đơn của file chưa được xác nhận (`INSERT … ON CONFLICT DO NOTHING`), ghi `log_event(kind="sales_history_confirmed", detail={"file_id", "confirmed", "skipped"})`, flash "Đã xác nhận N đơn, bỏ qua M đơn đã xác nhận ở file khác". <!-- Updated: Validation Session 1 - confirm step -->
6. `POST /sales-history/files/{file_id}/unconfirm` (`require_admin`): xóa các dòng `sales_history_exported` có `generated_file_id` bằng file đó, ghi `log_event(kind="sales_history_unconfirmed", detail={"file_id", "removed"})`.
7. Không ghi tên khách hay địa chỉ vào `event_log`.
8. Test:
   - trang mặc định dùng hôm nay; có đơn bị chặn thì không có nút và route file chuyển hướng;
   - đủ dữ liệu thì tải được file, tên file đúng, có `generated_file` kind `sales_history` và đúng số dòng `sales_history_file_order`;
   - xác nhận: lần xuất sau không còn các đơn đó; xác nhận file thứ hai chứa cùng đơn báo bỏ qua; gỡ xác nhận đưa đơn trở lại;
   - viewer tải được file; viewer POST xác nhận hoặc gỡ xác nhận bị chuyển hướng và không dòng nào đổi.

## Verification
- `uv run pytest tests/web/test_sales_history_routes.py`
- `uv run pytest` và `uv run ruff check`

## Risk & Rollback
- Dữ liệu đổi giữa lúc xem trước và lúc tải: route file tính lại từ đầu, và danh sách đơn của file được ghi theo đúng nội dung file.
- Quên xác nhận: đơn xuất lại ở lần sau; bảng "File đã tải" hiện file chưa xác nhận.
- Lùi lại: gỡ router và mục menu; các bảng sổ để nguyên không ảnh hưởng gì.
