---
title: Kế hoạch cấu hình và kiểm tra kết nối SAP trên web
date: 2026-11-13
summary: Lập kế hoạch đưa cấu hình SAP lên web và thêm việc check_connection do robot chạy
---

# Kế hoạch cấu hình và kiểm tra kết nối SAP trên web

## Chuyện gì đã xảy ra
Cấu hình SAP đang nằm trong `.env` và biến môi trường của máy robot. Đổi giá trị phải sửa file, khởi động lại, và chỉ biết đúng sai khi có việc thật. Đã lập kế hoạch `plans/261113-1012-sap-connection-settings-web/` gồm 4 phase: bảng `sap_settings` và heartbeat; robot đọc mật khẩu từ Windows Credential Manager và chạy việc `check_connection`; trang web Kết nối SAP; deploy, tài liệu và chạy thử trên `AEP`/300.

Điểm mấu chốt: web không gọi SAP trực tiếp được, vì SAP GUI Scripting chỉ chạy trong phiên Windows có màn hình của robot. Nút Kiểm tra vì vậy xếp một việc vào hàng đợi `sap_job` có sẵn.

## Quyết định (chủ dự án, 2026-11-13)
- Mật khẩu ở lại máy robot (Credential Manager, đặt bằng `shoponline sap-password set`); web chỉ thấy đã có hay chưa có.
- `check_connection` chạy được khi robot tạm dừng; lỗi kiểm tra không tăng bộ đếm lỗi và không tự tạm dừng robot.
- Đổi SYSTEM hoặc CLIENT thì phải kiểm tra thành công trước khi web xếp việc đọc báo cáo và trước khi robot nhận việc đó.

## Bước tiếp theo
Chạy `/ak-cook` theo plan, bắt đầu từ phase 1. Cần đối chiếu mã thông báo SAP cho trường hợp sai mật khẩu trên `AEP` ở phase 4.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
