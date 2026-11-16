---
title: Làm phase 1 và 2 — chạy ngầm tác vụ và script dựng máy
date: 2026-11-16
summary: "Hai commit cục bộ (9f6a31e, 6704eb8): tác vụ chạy qua conhost --headless, deploy tự sửa tác vụ lệch, web.log, setup-production-machine.ps1; push bị chặn, chờ chủ dự án push"
---

# Làm phase 1 và 2: chạy ngầm tác vụ và script dựng máy

## Đã làm
- `settings.ps1` có thêm `Test-HeadlessConsole` (dùng file đánh dấu), `New-HiddenTaskAction`, `New-TaskSettings` (cho chạy khi dùng pin) và `Test-TaskMatches`.
- `register-tasks.ps1 -OnlyMissing` giờ trả về một trong ba kết quả: thiếu (new), lệch (update) hoặc giữ (keep). Tác vụ lệch được cập nhật bằng `Set-ScheduledTask` để giữ trigger và tài khoản. `--apply` của retention được giữ. Kiểm tra cổng web chỉ chặn khi đăng ký mới.
- `install-deploy-runner.ps1 -TaskOnly` được gọi trong `update-production.ps1`, nhưng chỉ có hiệu lực từ lần deploy thứ hai.
- `cli.py` có thêm `_setup_logging`; web ghi vào `web.log`, `log_config=None`, và access log chỉ ghi từ mức WARNING.
- Có `setup-production-machine.ps1`, lưu UTF-8 kèm BOM để Windows PowerShell 5.1 đọc đúng tiếng Việt. Một số byte UTF-8 (0x93, 0x94) bị 5.1 đọc thành dấu nháy kép.

## Bài học
- Dưới pytest, `logging.basicConfig` không làm gì vì pytest đã gắn handler vào root. Phải gắn handler trực tiếp, nếu không test kiểm tra file log sẽ qua dù không ghi được gì.
- Tool Bash trong phiên này gộp `\\` trong heredoc thành `\`. Vì vậy `\r` trong đường dẫn biến thành ký tự CR. Khi sửa file có dấu `\`, nên dùng Write/Edit hoặc PowerShell.

## Còn lại
- Push `main` rồi xem job deploy. Đăng xuất và đăng nhập lại để kiểm tra không còn cửa sổ nào; kiểm tra lúc rút sạc.
- Phase 3 làm trên máy thật.
