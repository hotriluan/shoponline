---
phase: 3
title: "Trang web Kết nối SAP"
status: completed
effort: 1d
---

# Phase 3: Trang web Kết nối SAP

## Bối cảnh

- [routes/robot.py](../../src/shoponline/web/routes/robot.py) và [templates/robot.html](../../src/shoponline/web/templates/robot.html): trang Robot SAP; kiểu render phía server, `require_admin` cho thao tác thay đổi, `flash` + `redirect`.
- [batches.py:158,181](../../src/shoponline/web/routes/batches.py): xếp việc đọc báo cáo với `sap_target`.
- JS hiện có chỉ một khối nhỏ trong `base.html`.

## Yêu cầu

1. `GET /robot/sap-connection` (mọi user xem được; viewer chỉ đọc):
   - Form: hệ thống, client, mục SAP Logon (danh sách chọn lấy từ `saplogon_entries` của heartbeat; nếu danh sách rỗng thì ô nhập chữ), user SAP, ngôn ngữ, số lỗi tối đa, số ngày giữ ảnh.
   - Ô trạng thái: robot đang chạy hay không (`robot_alive`, kèm tên máy và lần thấy cuối); mật khẩu "đã có / chưa có" kèm lệnh cần chạy trên máy robot; cấu hình đã xác nhận hay chưa.
   - Kết quả kiểm tra gần nhất: thời gian, người bấm, kết quả, thông báo lỗi và cách sửa.
2. `POST /robot/sap-connection` (admin): lưu bằng `sap_settings.save`. Nút **Lưu** và **Lưu và kiểm tra**; nút **Kiểm tra** riêng khi không đổi gì. Kiểm tra = `queue.supersede_checks` rồi `queue.enqueue(CHECK_CONNECTION, target hiện tại, dedupe "check_connection", payload {})`.
3. Trong khi việc kiểm tra mới nhất ở trạng thái Chờ hoặc Đang chạy, trang tự tải lại mỗi 3 giây (thẻ `<meta http-equiv="refresh">` có điều kiện, không thêm thư viện JS). Hiển thị:
   - robot không chạy (heartbeat cũ hơn 30 giây): "Robot không chạy — việc kiểm tra sẽ chạy khi robot bật lại";
   - robot đang làm việc khác: "Đang chờ robot xong việc #N".
4. Chặn khi chưa xác nhận: ở `batches.py`, nếu `target_verified` sai thì không xếp việc đọc báo cáo và báo "Đã đổi hệ thống SAP, cần kiểm tra kết nối thành công trước". Nút trên trang lô hiện trạng thái khóa kèm liên kết tới trang Kết nối SAP.
5. Thanh cảnh báo chung (`robot_warning` trong `app.py`) thêm trường hợp "cấu hình SAP chưa được xác nhận". `robot_enabled` dựa trên `sap_settings.target`.
6. Liên kết tới trang mới từ trang Robot SAP và thanh điều hướng.

## Files

- Tạo: `src/shoponline/web/templates/sap_connection.html`, `tests/web/test_sap_connection.py`
- Sửa: `src/shoponline/web/routes/robot.py`, `src/shoponline/web/routes/batches.py`, `src/shoponline/web/app.py`, `src/shoponline/web/templates/robot.html`, `src/shoponline/web/templates/base.html`, `src/shoponline/web/templates/batch_detail.html`

## Các bước

1. Test web (`httpx` TestClient như các test web hiện có): viewer không lưu được (403); dữ liệu sai báo lỗi trên form và không lưu; lưu ghi nhật ký sự kiện; Kiểm tra tạo đúng một việc PENDING và thay việc PENDING cũ; đổi system thì xếp việc đọc báo cáo bị từ chối; robot không chạy thì hiện đúng thông báo.
2. Route và template theo phong cách trang hiện có.
3. Mở trang trên máy dev, kiểm tra hiển thị ở màn hình hẹp.

## Kiểm tra

- `uv run pytest tests/web tests/sapjobs`
- Chạy web cục bộ (dùng cổng `8750` theo `.env`; nếu đang có tiến trình web của dự án thì dùng lại, không mở cổng khác) và bấm thử với robot tắt.

## Rủi ro và lùi lại

- Trang tự tải lại làm mất nội dung form đang gõ: chỉ tự tải lại khi có việc kiểm tra đang chờ, và khi đó form được khóa.
- Lùi: revert commit; bảng `sap_settings` vẫn được robot đọc.
