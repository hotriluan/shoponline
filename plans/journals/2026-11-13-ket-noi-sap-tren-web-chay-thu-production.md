---
title: Kết nối SAP trên web đã chạy thử thành công trên Production
date: 2026-11-13
summary: Cấu hình SAP chuyển vào database, robot kiểm tra kết nối AEP/300 thành công, mật khẩu chuyển sang Credential Manager
---

# Kết nối SAP trên web đã chạy thử thành công trên Production

## Chuyện gì đã xảy ra
Đã làm xong bốn phase của `plans/261113-1012-sap-connection-settings-web/` và đưa lên `main` (commit `83d1d94`). Workflow `deploy` chạy xanh; web và robot chạy ở commit mới.

- Cấu hình SAP (hệ thống, client, mục SAP Logon, user, ngôn ngữ, số lỗi tối đa, số ngày giữ ảnh) nằm trong bảng `sap_settings`, sửa trên trang **Robot SAP → Kết nối SAP**. Lần đầu chạy sau nâng cấp, giá trị trong biến môi trường được chép vào database và coi là đã kiểm tra, nên robot đang chạy không bị khóa.
- Việc `check_connection`: robot đăng nhập, đọc hệ thống, client, user của phiên, rồi đăng xuất. Chạy được khi robot tạm dừng, không tính vào bộ đếm lỗi liên tiếp.
- Mật khẩu của `AL17016` được đặt bằng `uv run --extra robot shoponline sap-password set` dưới tài khoản `luanh` và nằm trong Windows Credential Manager.

## Kết quả chạy thử trên Production
- Bấm Kiểm tra: việc #1 xong, `AEP/300`, user `AL17016`, SAP GUI 7600.257.1; trang hiện robot đang chạy trên máy Alkana_IT, mật khẩu "đã có", cấu hình "đã xác nhận".
- Dòng `SHOPONLINE_SAP_PASSWORD` trong `C:\shoponline\.env` (còn sót, dạng văn bản) đã được chủ dự án xóa; robot khởi động lại và kiểm tra vẫn thành công, tức là mật khẩu đọc từ Credential Manager. Biến này không có ở mức User, Machine hay Process của Windows.
- Trường hợp thất bại có chủ đích (mục SAP Logon sai) chưa chạy trên Production; các mã lỗi mới được kiểm bằng test với engine giả. Thông báo nguyên văn của SAP khi sai mật khẩu cũng chưa đối chiếu, vì sai nhiều lần có thể khóa `AL17016`.

## Điều cần nhớ
- Công cụ bảo vệ file chặn việc đọc `.env` và ghi `credentials.py`; hai file mã được chủ dự án cho phép từng lần.
- Phải xóa file sao lưu `.env.bak-before-sap-password-removal` vì nó còn chứa mật khẩu cũ.
- Việc còn lại: thử mục SAP Logon sai trên Production (chọn `QAS server` hoặc gõ tên sai, xem lỗi `connection_not_found`, trả lại mục đúng, kiểm tra lại).

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
