---
title: "Triển khai chạy thật trên máy phát triển, tự deploy qua GitHub"
date: 2026-11-12
summary: C:\shoponline clone từ GitHub, chạy bằng Task Scheduler khi đăng nhập; push main thì GitHub test rồi self-hosted runner trên máy tự cập nhật
---

# Triển khai chạy thật qua GitHub

## Đã xảy ra
- Commit và push phần robot đang dở, rồi clone `hotriluan/shoponline` vào `C:\shoponline`, tách khỏi thư mục dev `C:\dev\shoponline`.
- Database `shoponline` tạo bằng `create-databases.ps1`, dữ liệu ở `C:\shoponline-data`. Sao lưu tạm vào `C:\shoponline-backup` trên chính máy này. Web chỉ nghe `127.0.0.1:8750`. Admin web: `luan`.
- Thêm `-AtLogOn` cho `register-tasks.ps1`: web và sao lưu chạy trong phiên của người dùng khi đăng nhập, không lưu mật khẩu Windows, không cần quyền quản trị.
- Thêm `.github/workflows/deploy.yml`, `update-production.ps1` và `install-deploy-runner.ps1`. Runner `shoponline-prod` chạy dưới dạng tác vụ khi đăng nhập. Repo bật duyệt bắt buộc workflow của người đóng góp bên ngoài vì repo đang public.

## Lỗi gặp khi triển khai
- `.gitignore` có `exports/` nên ignore luôn `src/shoponline/exports/`. Package này chưa từng lên GitHub; máy dev vẫn chạy được vì có file cục bộ. Job test trên GitHub chặn được bản thiếu package. Đã sửa thành `/exports/`.
- `create-databases.ps1 -Environment prod` ghi chuỗi kết nối tới database `s`: biểu thức `if` trả về mảng một phần tử, PowerShell tự mở thành chuỗi, nên `$databases[0]` lấy ký tự đầu. Đã bọc bằng `@()`.
- `Stop-ScheduledTask` chỉ dừng tiến trình pwsh bọc ngoài; Python của venv (launcher và tiến trình con) vẫn giữ cổng. Đường dẫn file thực thi là `C:\Python314\python.exe`, nên không lọc theo đường dẫn được. `update-production.ps1` giờ dừng các tiến trình có command line `<repo>\.venv\Scripts\shoponline.exe web`.

## Giới hạn hiện tại
- Web, sao lưu và runner chỉ chạy khi `luanh` đang đăng nhập.
- Bản sao lưu nằm cùng ổ đĩa với database. Cần thêm ổ mạng hoặc Google Drive vào `SHOPONLINE_BACKUP_DIRS`.
- Mật khẩu sao lưu là chuỗi ngẫu nhiên chỉ có trong `C:\shoponline\.env`; cần chép sang kho bí mật.
- Server dev và bản chạy thật cùng mặc định cổng 8750; chạy server dev thì phải đổi cổng.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
