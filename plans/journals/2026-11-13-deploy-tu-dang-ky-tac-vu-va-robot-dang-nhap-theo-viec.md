---
title: "Deploy tự đăng ký tác vụ, robot đăng nhập SAP theo việc"
date: 2026-11-13
summary: Mỗi lần deploy qua GitHub tự đăng ký tác vụ còn thiếu và bật robot khi đủ cấu hình; robot chỉ đăng nhập SAP khi có việc và đăng xuất ngay sau đó
---

# Deploy tự đăng ký tác vụ, robot đăng nhập theo việc

## Trạng thái máy chạy thật trước khi làm
- `C:\shoponline` ở `ac9b46f`, runner `shoponline-prod` online. Có `shoponline-web`, `shoponline-backup`, `shoponline-deploy-runner`. Chưa có `shoponline-retention`, `shoponline-robot`.
- Chủ dự án xác nhận `.env` chưa có các biến SAP của robot.

## Deploy
- `update-production.ps1` dừng robot trước `uv sync` (robot giữ file pywin32), sau `migrate` gọi `register-tasks.ps1 -AtLogOn -OnlyMissing` cho tài khoản chạy runner, rồi bật web và robot. Tác vụ đã có giữ nguyên để không mất tùy chọn như `-RetentionApply`.
- Robot chỉ bật khi đủ `SHOPONLINE_SAP_CONNECTION`, `SHOPONLINE_SAP_USER`, `SHOPONLINE_SAP_PASSWORD`; thiếu thì log nêu tên biến. Robot thoát ngay sau khi bật thì job deploy lỗi.
- Runner chạy bản script đang có trên đĩa, nên thay đổi này có hiệu lực từ lần deploy sau lần đưa nó xuống máy. Khi máy đã ở đúng commit, chạy lại workflow chỉ sửa tác vụ và bật web, robot.

## Robot đăng nhập theo việc
- Chủ dự án muốn robot không giữ phiên SAP: đăng nhập khi có việc, xong là đăng xuất.
- Đăng xuất bằng `GuiConnection.CloseConnection`, lệnh scripting chứ không phải T-code, nên danh sách T-code được phép trong `guard.py` không đổi. Đăng xuất cả khi việc lỗi, sau khi đã chụp ảnh.
- Chỉ đăng xuất phiên đã qua `ensure_session`, tức phiên của `AL17016` trên đúng hệ thống. Phiên của người khác dẫn tới `WrongSystem` trước khi robot giữ phiên nào, nên không bao giờ bị đóng.
- Khi khởi động, sau khi giữ khóa một-robot, robot đăng xuất phiên `AL17016` còn sót. Bước này không tự mở SAP Logon; SAP Logon không chạy nghĩa là không có phiên nào.
- Khi cần đăng nhập mà SAP Logon chưa chạy, robot tự mở `saplogon.exe` và chờ tối đa 60 giây.
- Mục SAP Logon trỏ `AEP` trên máy này tên là `SAP PRODUCTION GROUP ALKANA`.

## Kiểm chứng
- 7 test mới với SAP GUI giả: đăng nhập rồi đăng xuất cho một việc, việc lỗi vẫn đăng xuất sau khi chụp ảnh, không đóng phiên của người khác, dọn phiên sót chỉ đóng phiên của robot, tự mở SAP Logon. Toàn bộ 162 test đạt. Hai script PowerShell qua parser, chưa chạy thật trước lần deploy.
- Chưa chạy trên SAP thật: `CloseConnection` trên AEP cần kiểm ở lần chạy thử đầu.
