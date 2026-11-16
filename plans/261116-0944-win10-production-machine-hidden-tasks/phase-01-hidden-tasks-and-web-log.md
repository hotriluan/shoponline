---
phase: 1
title: "Chạy ngầm mọi tác vụ, log web, chạy khi dùng pin"
status: in-progress
priority: P2
effort: 0.5d
dependencies: []
---

# Phase 1: Chạy ngầm mọi tác vụ, log web, chạy khi dùng pin

## Goal

Web, robot, runner, sao lưu và retention chạy không hiện cửa sổ, trên Windows 11 lẫn Windows 10. Lỗi của web được ghi vào file. Tác vụ không dừng khi rút sạc. Push lên `main` tự sửa các tác vụ đã đăng ký trên máy chạy thật.

## Bối cảnh (đã kiểm tra 2026-11-16)

- Mọi tác vụ hiện chạy `pwsh -NoProfile -WindowStyle Hidden ...`:
  - [register-tasks.ps1](../../scripts/windows/register-tasks.ps1) đăng ký web, sao lưu, retention và robot;
  - [install-deploy-runner.ps1](../../scripts/windows/install-deploy-runner.ps1) đăng ký `shoponline-deploy-runner`.
- `Alkana_IT` là Windows 11, chưa chọn terminal mặc định (không có `HKCU:\Console\%%Startup`), có Windows Terminal 1.24. Windows giao console cho Windows Terminal, và Windows Terminal bỏ qua `-WindowStyle Hidden`, nên cửa sổ vẫn hiện.
- Kết quả thử bằng tác vụ tạm, cùng kiểu đăng nhập Interactive:

  | Cách chạy | Kết quả |
  |---|---|
  | `pwsh -WindowStyle Hidden` | hiện cửa sổ `WindowsTerminal` |
  | `uvw.exe run` | không cửa sổ, Python chạy |
  | `conhost.exe --headless <file .cmd>` | không cửa sổ, Python con chạy |

- `conhost.exe --headless cmd /c "exit 37"` trả mã 0: `conhost` không chuyển mã thoát của tiến trình con.
- Các tác vụ đang có `DisallowStartIfOnBatteries=True` và `StopIfGoingOnBatteries=True`. `Alkana_IT` là laptop.
- `register-tasks.ps1 -OnlyMissing` (do `update-production.ps1` gọi mỗi lần deploy) bỏ qua tác vụ đã có. Vì vậy đổi lệnh chạy không tới được máy đang chạy.
- Robot có `<data>\logs\robot.log` ([cli.py:71-83](../../src/shoponline/cli.py)). Web chỉ gọi `uvicorn.run(...)` với cấu hình log mặc định của uvicorn: log ra stderr, logger `uvicorn` không đẩy lên root ([cli.py:49-56](../../src/shoponline/cli.py)).

## Requirements

1. **Hàm dùng chung trong [settings.ps1](../../scripts/windows/settings.ps1):**
   - `Test-HeadlessConsole`:
     - chạy `conhost.exe --headless cmd.exe /c echo ok> "<file tạm>"` bằng `Start-Process -Wait`;
     - trả `$true` khi file đánh dấu xuất hiện với nội dung `ok`, rồi xóa file.
   - `New-HiddenTaskAction -Execute <exe> -Argument <args> -WorkingDirectory <dir>`:
     - khi `Test-HeadlessConsole` đúng: trả action `conhost.exe` với `--headless "<exe>" <args>`;
     - khi sai: trả action `pwsh -NoProfile -WindowStyle Hidden -Command "& '<exe>' <args>"` như hiện nay và in cảnh báo một lần.

     Kết quả kiểm tra được nhớ trong biến script, nên chỉ chạy một lần mỗi lần gọi script.
   - `New-TaskSettings`: thêm `-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries` vào các cài đặt hiện có. Ba bộ cài đặt (web, hằng ngày, robot) và bộ của runner dùng hàm này.
2. **[register-tasks.ps1](../../scripts/windows/register-tasks.ps1):**
   - Web, robot, retention: action là `uv.exe` trực tiếp, đối số `run --no-dev [--extra robot] shoponline <lệnh>`, qua `New-HiddenTaskAction`. Không còn lớp `pwsh` bọc ngoài.
   - Sao lưu: `New-HiddenTaskAction -Execute pwsh -Argument "-NoProfile -ExecutionPolicy Bypass -File backup-db.ps1"`.
   - **`-OnlyMissing` thành "thiếu hoặc lệch".** `Test-TaskWanted` so lệnh chạy (`Execute`, `Arguments`) và hai cờ pin của tác vụ đang có với bản mong muốn:
     - giống nhau: in "Đã có …, giữ nguyên";
     - khác nhau: in "Cập nhật cách chạy …" và đăng ký lại, giữ trigger hiện có.
   - Retention: khi `-OnlyMissing` và tác vụ đang có chứa `retention --apply`, bản mong muốn cũng giữ `--apply`. Không bao giờ tự bật hoặc tắt chế độ xóa thật.
   - Robot: đăng ký lại vì lệch được phép kể cả khi robot đang chạy. Định nghĩa mới áp dụng từ lần khởi động sau, và Task Scheduler không chạy bản thứ hai. Lệnh đăng ký mới (không `-OnlyMissing`) vẫn từ chối khi robot đang chạy, như hiện nay.
3. **[install-deploy-runner.ps1](../../scripts/windows/install-deploy-runner.ps1):** dùng `New-HiddenTaskAction -Execute "$RunnerDir\run.cmd"` và `New-TaskSettings`. Tách phần đăng ký tác vụ runner thành tham số `-TaskOnly`:
   - với `-TaskOnly`: không cần `gh`, không tải runner;
   - chỉ đăng ký lại khi lệch và không gọi `Start-ScheduledTask`.
4. **[update-production.ps1](../../scripts/windows/update-production.ps1):** `Register-MissingTasks` gọi thêm `install-deploy-runner.ps1 -TaskOnly`. Runner đang chạy job không bị dừng; cửa sổ của nó mất từ lần đăng nhập sau.
   Lưu ý: thay đổi trong file này chỉ áp dụng từ lần deploy thứ hai. Lần đầu, bản cũ trên đĩa vẫn gọi `register-tasks.ps1 -OnlyMissing`, nhưng đó đã là bản mới sau `git merge`, nên web, robot, sao lưu và retention được sửa ngay từ lần đầu.
5. **Log web ([cli.py](../../src/shoponline/cli.py)):**
   - Tách hàm `_setup_logging(settings, file_name)` từ đoạn cấu hình log của robot: tạo `<data>\logs`, `StreamHandler` cộng `RotatingFileHandler` 5 MB × 10, UTF-8. `_cmd_robot` dùng `robot.log`, `_cmd_web` dùng `web.log`.
   - `_cmd_web` gọi `uvicorn.run(..., log_config=None)` để log uvicorn đẩy về root, và đặt logger `uvicorn.access` ở mức WARNING.
6. **Tài liệu:**
   - [deployment-guide.md](../../docs/deployment-guide.md) mục 5 và 5b: tác vụ chạy ẩn qua `conhost --headless` (quay về cách cũ khi máy không hỗ trợ), deploy tự sửa tác vụ lệch, cho phép chạy khi dùng pin.
   - [operations-runbook.md](../../docs/operations-runbook.md): log web ở `<SHOPONLINE_DATA_DIR>\logs\web.log`; không còn cửa sổ để xem, muốn biết web và robot có chạy không thì xem Task Scheduler hoặc trang Robot SAP.

## Files to Create / Modify

- Modify: `scripts/windows/settings.ps1`, `scripts/windows/register-tasks.ps1`, `scripts/windows/install-deploy-runner.ps1`, `scripts/windows/update-production.ps1`
- Modify: `src/shoponline/cli.py`
- Create: `tests/test_cli_logging.py`
- Modify: `docs/deployment-guide.md`, `docs/operations-runbook.md`

## Tasks & Steps

1. Viết ba hàm trong `settings.ps1`. Chạy thử `Test-HeadlessConsole` tay trên `Alkana_IT`: phải trả `$true` và không để lại file tạm.
2. Sửa `register-tasks.ps1`: action, settings, so sánh lệch, giữ `--apply`.
3. Sửa `install-deploy-runner.ps1` (`-TaskOnly`) và `update-production.ps1`.
4. Sửa `cli.py` và viết `tests/test_cli_logging.py`:
   - `_setup_logging` tạo file log trong `tmp_path` và ghi được một dòng;
   - `_cmd_web` gọi `uvicorn.run` với `log_config=None` (monkeypatch `uvicorn.run` và `load_settings`).
5. Cập nhật hai tài liệu.
6. Commit theo conventional commit, push `main`. Theo dõi job deploy.

## Verification

- `uv run pytest -q` và `uv run ruff check` thoát mã 0.
- Kiểm tra cú pháp từng script: `pwsh -NoProfile -Command "[ScriptBlock]::Create((Get-Content -Raw <file>)) | Out-Null"`.
- Sau deploy trên `Alkana_IT`:
  - `Get-ScheduledTask shoponline-* | % { $_.Actions[0].Execute }` cho `conhost.exe` ở web, robot, sao lưu, retention.
  - `Settings.DisallowStartIfOnBatteries` là `False` ở mọi tác vụ.
  - Nếu retention đã có `--apply` thì vẫn còn.
- Đăng xuất rồi đăng nhập lại `Alkana_IT`:
  - không có cửa sổ PowerShell hay Windows Terminal nào của shoponline;
  - `http://<host>:8750/login` trả 200, trang Robot SAP báo robot "đang chạy", runner online trên GitHub;
  - `logs\web.log` có dòng khởi động của uvicorn.
- Rút sạc 2 phút: web vẫn trả lời, robot vẫn chạy.
- Chạy tay `shoponline-backup`: file `.7z` mới xuất hiện, không có cửa sổ.

## Risk & Rollback

- Bài kiểm tra headless có thể sai trên máy lạ. Khi đó action quay về `pwsh -WindowStyle Hidden`: tác vụ vẫn chạy, chỉ hiện cửa sổ.
- So sánh lệch quá nhạy có thể làm tác vụ bị đăng ký lại ở mọi lần deploy. Vô hại, nhưng log deploy sẽ báo "Cập nhật cách chạy" lặp lại; sửa phép so sánh nếu thấy.
- Lùi lại: `git revert` commit rồi push. `-OnlyMissing` của bản cũ không đổi lại action đã đăng ký, nên chạy tay `register-tasks.ps1 -User <tài khoản> -AtLogOn` và `-RobotUser <tài khoản>` để đăng ký lại.
