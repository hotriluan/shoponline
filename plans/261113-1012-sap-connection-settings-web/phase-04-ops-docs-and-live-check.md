---
phase: 4
title: "Deploy, tài liệu và chạy thử trên Production"
status: in-progress
effort: 0.5d
---

# Phase 4: Deploy, tài liệu và chạy thử trên Production

## Bối cảnh

- [update-production.ps1:39,103-117](../../scripts/windows/update-production.ps1): robot chỉ được bật khi env có `SHOPONLINE_SAP_CONNECTION`, `SHOPONLINE_SAP_USER`, `SHOPONLINE_SAP_PASSWORD`.
- Tài liệu: [robot-machine-setup.md](../../docs/robot-machine-setup.md) mục 3 và 5, [security-and-data-retention.md](../../docs/security-and-data-retention.md) mục "User SAP của robot" và "Bí mật", [deployment-guide.md](../../docs/deployment-guide.md), [robot-runbook.md](../../docs/robot-runbook.md), [.env.example](../../.env.example).

## Yêu cầu

1. `update-production.ps1`: bỏ điều kiện ba biến env; luôn bật robot (robot giờ khởi động được khi cấu hình chưa đủ và báo trên web). Giữ kiểm tra "robot thoát ngay sau khi bật thì deploy lỗi".
2. `.env.example`: ghi rõ các biến SAP chỉ là giá trị ban đầu, sau khi chạy thì sửa trên web; bỏ `SHOPONLINE_SAP_PASSWORD` khỏi mẫu và trỏ tới `shoponline sap-password set`.
3. Tài liệu:
   - robot-machine-setup: bảng cấu hình chuyển sang trang Kết nối SAP; bước đặt mật khẩu bằng `sap-password set` dưới tài khoản chạy robot; mục Kiểm tra dùng nút Kiểm tra.
   - security: mật khẩu nằm trong Windows Credential Manager của tài khoản chạy robot; web không đọc được; đổi mật khẩu thì chạy lại lệnh.
   - robot-runbook: bảng mã lỗi kiểm tra kết nối và cách sửa; quy tắc "đổi hệ thống phải kiểm tra trước".
   - deployment-guide: robot luôn được bật khi deploy.
4. Chạy thử trên máy thật sau deploy:
   1. Dưới tài khoản `luanh`: `uv run shoponline sap-password set`, rồi xóa `SHOPONLINE_SAP_PASSWORD` khỏi biến môi trường người dùng sau khi kiểm tra thành công (bước xóa do chủ dự án làm).
   2. Trang Kết nối SAP: thấy robot đang chạy, mật khẩu đã có, danh sách mục SAP Logon có `SAP PRODUCTION GROUP ALKANA`.
   3. Bấm Kiểm tra: thành công với `AEP/300 user AL17016`.
   4. Chọn tạm một mục SAP Logon không trỏ `AEP` hoặc gõ tên sai: thấy lỗi đúng loại; trả lại giá trị đúng và kiểm tra lại thành công.
   5. Ghi lại nguyên văn thông báo SAP khi sai mật khẩu nếu chủ dự án đồng ý thử (lưu ý: sai nhiều lần sẽ khóa user `AL17016`; chỉ thử một lần).

## Files

- Sửa: `scripts/windows/update-production.ps1`, `.env.example`, `docs/robot-machine-setup.md`, `docs/security-and-data-retention.md`, `docs/robot-runbook.md`, `docs/deployment-guide.md`

## Kiểm tra

- `uv run pytest` và `uv run ruff check` thoát mã 0 trước khi đẩy.
- Deploy qua workflow `deploy`; job xanh; trang `/login` trả lời; robot chạy.
- Các bước chạy thử ở mục 4 đều đạt; ghi kết quả vào journal.

## Rủi ro và lùi lại

- Deploy làm robot dừng nếu cấu hình DB lỗi: dòng `sap_settings` được tạo từ env cũ và coi là đã xác nhận, nên robot đang chạy không bị khóa.
- Lùi: lùi về commit cũ theo hướng dẫn trong log deploy; `alembic downgrade` về `0004`; giữ `SHOPONLINE_SAP_PASSWORD` trong env cho tới khi bước 4.3 đạt.
