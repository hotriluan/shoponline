---
phase: 5
title: "Trang hệ thống và đăng nhập"
status: completed
priority: P2
effort: "6h"
dependencies: [1]
---

# Phase 5: Trang hệ thống và đăng nhập

## Goal

Làm lại các trang Robot SAP, Kết nối SAP, Sao lưu (5 template) và trang đăng nhập, và gỡ 26 `style=""` nội tuyến còn lại.

## Files (phase này sở hữu)

- Modify: `templates/robot.html`, `templates/sap_connection.html`, `templates/backup.html`, `templates/backup_list.html`, `templates/backup_drive.html`, `templates/backup_drive_files.html`, `templates/backup_restoring.html`, `templates/login.html`, `templates/pager.html`, `templates/table_tools.html` (chỉ class/markup của thanh công cụ; không đổi logic JS)

## Steps

1. **Đăng nhập:** layout một cột căn giữa, tên sản phẩm, nhãn trên ô, nút rộng toàn khung, thông báo lỗi ngay trên form; bỏ `style` nội tuyến của ô mật khẩu.
2. **Robot SAP:** đầu trang là card trạng thái (Đang chạy / Tạm dừng / Chưa xác nhận kết nối) có công tắc bật/tắt (admin); form "Ra lệnh cho robot" và hàng đợi bên dưới; trạng thái việc dùng `status_badge` (`j-*`).
3. **Kết nối SAP:** card cấu hình và card kiểm tra kết nối với kết quả thành alert.
4. **Sao lưu:** card tổng quan cho mỗi nơi lưu (máy chủ, Drive) có lần gần nhất và độ tuổi; danh sách bản sao lưu dùng bảng mới; nút phục hồi là `danger` và giữ nguyên xác nhận hiện có; trang đang phục hồi có tiến trình rõ. Gỡ 22 `style=""` trong các file backup.
5. **Pager và table_tools:** chỉnh markup thanh tìm kiếm và phân trang theo component mới; giữ class `tt-*` mà JS dùng để chọn phần tử.

## Verification

- `uv run pytest tests/web/test_backup_page.py tests/web/test_robot_web.py tests/web/test_sap_connection.py tests/web/test_session_epoch.py -q` xanh.
- `grep -rn 'style="' src/shoponline/web/templates` không còn kết quả (sau khi phase 3–5 xong).

## Risks

- Trang phục hồi và trạng thái sao lưu có thể thăm dò bằng JS theo id. Giữ nguyên id và endpoint `/status`.
