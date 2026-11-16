---
phase: 2
title: "Script dựng máy chạy thật Windows 10"
status: in-progress
priority: P2
effort: 1d
dependencies: [1]
---

# Phase 2: Script dựng máy chạy thật Windows 10

## Goal

Trên máy Windows 10 64-bit trắng (bản tiếng Anh), một lệnh `setup-production-machine.ps1` dựng xong máy chạy thật: phần mềm, mã nguồn, database (khôi phục từ bản sao lưu), thư mục dữ liệu, tác vụ ẩn, tường lửa và runner. Script chỉ dừng ở những bước bắt buộc nhập tay, và chạy lại được nhiều lần.

## Bối cảnh

- Hiện dựng máy làm tay theo [deployment-guide.md](../../docs/deployment-guide.md) mục 1–5b và [robot-machine-setup.md](../../docs/robot-machine-setup.md). Các script có sẵn được gọi lại, không viết lại:
  - [create-databases.ps1](../../scripts/windows/create-databases.ps1) `-Environment prod -WriteEnvFile -DataDir`: hỏi mật khẩu superuser postgres và mật khẩu app; ghi `.env` chỉ khi chưa có; chạy lại an toàn.
  - [restore-db.ps1](../../scripts/windows/restore-db.ps1) `-Archive -TargetSetting SHOPONLINE_DATABASE_URL -AllowProduction`.
  - `register-tasks.ps1 -AtLogOn` và `-RobotUser` (đã chạy ẩn sau phase 1).
  - [install-deploy-runner.ps1](../../scripts/windows/install-deploy-runner.ps1): cần `gh` đã đăng nhập với quyền admin repo.
- Repo đang public, nên máy mới tải được script đầu tiên từ `raw.githubusercontent.com` trước khi có `git`.
- Windows 10 1809 trở lên có `winget` (App Installer). Windows PowerShell 5.1 có sẵn; `pwsh` 7 chưa có lúc bắt đầu.
- Những việc cần quyền admin: cài phần mềm dạng machine-scope, quy tắc tường lửa, `powercfg`. Những việc khác chạy dưới tài khoản thường để `C:\shoponline` và `.env` thuộc tài khoản chạy tác vụ.

## Requirements

1. **Tạo `scripts/windows/setup-production-machine.ps1`.** Script chạy được trên Windows PowerShell 5.1 ở giai đoạn 1, và tự chạy lại dưới `pwsh` cho giai đoạn 2.
   - Tham số:
     - `-Archive <.7z>`: bản sao lưu để khôi phục;
     - `-DataSource <thư mục>`: thư mục dữ liệu cũ để chép sang;
     - `-DataDir`: mặc định `C:\shoponline-data`;
     - `-RepoUrl`: mặc định `https://github.com/hotriluan/shoponline.git`;
     - `-Prepare`: dựng trước ngày chuyển máy. Không cài runner. Tác vụ robot được đăng ký nhưng để Disabled và không bật, vì robot cũ trên `Alkana_IT` vẫn đang dùng `AL17016`.
2. **Giai đoạn 1: phần mềm và mã.** Mỗi bước kiểm tra "đã có" trước khi làm.
   - Kiểm tra là Windows 64-bit, có `winget`, đang ở tài khoản thường (không phải phiên elevated). Sai thì dừng kèm hướng dẫn.
   - Cài bằng `winget install --exact --id <id> --accept-package-agreements --accept-source-agreements`:
     - `Git.Git`, `Microsoft.PowerShell`, `7zip.7zip`, `GitHub.cli`: các bản machine-scope này mỗi gói hiện UAC một lần;
     - `PostgreSQL.PostgreSQL.16`: bộ cài hỏi mật khẩu superuser; ghi rõ cần nhớ mật khẩu này cho bước tạo database;
     - `astral-sh.uv`: user-scope.

     Sau khi cài, làm mới `PATH` trong phiên.
   - Kiểm tra đường dẫn chuẩn tồn tại: `C:\Program Files\PostgreSQL\16\bin\psql.exe`, `C:\Program Files\7-Zip\7z.exe`.
   - Có `C:\shoponline\.git` thì `git -C C:\shoponline status --porcelain` phải rỗng. Chưa có thì `git clone <RepoUrl> C:\shoponline`.
   - Gọi lại chính bản trong `C:\shoponline\scripts\windows\` bằng `pwsh`, cùng tham số và cờ `-Stage2`.
3. **Giai đoạn 2: hệ thống (`pwsh`, trong repo).**
   1. `Test-HeadlessConsole` (từ phase 1): in "Tác vụ sẽ chạy ẩn" hoặc cảnh báo "sẽ hiện cửa sổ".
   2. `uv sync --frozen --no-dev --extra robot`.
   3. `.env` chưa có: gọi `create-databases.ps1 -Environment prod -WriteEnvFile -DataDir <DataDir>`. Có rồi thì bỏ qua.
   4. Bổ sung vào `.env` những dòng còn thiếu, không sửa dòng đã có:
      - `SHOPONLINE_WEB_HOST`: gợi ý IPv4 LAN của máy, người dùng xác nhận;
      - `SHOPONLINE_BACKUP_DIRS`: hỏi;
      - `SHOPONLINE_BACKUP_PASSWORD`: hỏi bằng `Read-Host -AsSecureString`, ghi vào `.env`, không in ra.
   5. Giới hạn quyền `.env` và `<DataDir>` cho tài khoản hiện tại, `Administrators` và `SYSTEM` (`icacls /inheritance:r /grant:r`).
   6. Có `-DataSource`: `robocopy <DataSource> <DataDir> /E /COPY:DAT /R:2 /W:5`. Mã robocopy ≥ 8 là lỗi.
   7. Có `-Archive` và database `shoponline` chưa có bảng nào: `restore-db.ps1 -Archive <file> -TargetSetting SHOPONLINE_DATABASE_URL -AllowProduction`. Database đã có dữ liệu thì không khôi phục đè, chỉ in hướng dẫn chạy tay.
   8. `uv run --no-dev shoponline migrate`.
   9. `register-tasks.ps1 -User <tài khoản hiện tại> -AtLogOn -OnlyMissing -WebPort <cổng>`, rồi `register-tasks.ps1 -RobotUser <tài khoản hiện tại> -OnlyMissing`.
   10. Một lần UAC cho một khối lệnh elevated:
       - quy tắc tường lửa `shoponline-web`: TCP vào cổng web, profile Domain và Private; có rồi thì bỏ qua;
       - `powercfg /change standby-timeout-ac 0`, `powercfg /change monitor-timeout-ac 0`, `powercfg /change hibernate-timeout-ac 0`.
   11. Không có `-Prepare`: `gh auth status` chưa đăng nhập thì chạy `gh auth login`, rồi `install-deploy-runner.ps1`.
   12. Bật web (`Start-ScheduledTask`) và chờ `/login` trả 200. Có `-Prepare` thì `Disable-ScheduledTask shoponline-robot`. Không có thì `Enable-ScheduledTask`, rồi bật robot.
4. **Cuối script in bảng kiểm tra:** mỗi dòng là ✓ (đã xong) hoặc "việc tay" kèm hướng dẫn ngắn và liên kết tài liệu. Những mục máy tự kiểm được thì tự kiểm, ví dụ có `saplogon.exe` không, `gh auth status`. Các việc tay:
   - cài SAP GUI cùng phiên bản và bật scripting phía máy khách;
   - cài Microsoft Excel;
   - Sysinternals Autologon cho tài khoản này;
   - tắt khóa màn hình và trình bảo vệ màn hình;
   - `uv run --extra robot shoponline sap-password set`;
   - mở trang Kết nối SAP và bấm Kiểm tra.
5. **Không làm:** không lưu mật khẩu nào ngoài `.env` (theo thiết kế hiện có), không tự bật `-RetentionApply`, không tự cài SAP GUI hay Excel.

## Files to Create / Modify

- Create: `scripts/windows/setup-production-machine.ps1`
- Modify: `docs/deployment-guide.md`: mục 1–5 rút gọn thành "chạy script, rồi làm các việc tay". Giữ cách làm tay làm phụ lục ngắn cho máy không có `winget`.

## Tasks & Steps

1. Viết giai đoạn 1 theo cú pháp chạy được trên PowerShell 5.1: không `??`, không `&&`, không toán tử ba ngôi.
2. Viết giai đoạn 2, gọi lại các script có sẵn.
3. Kiểm tra cú pháp cả hai bản PowerShell:
   - `powershell -NoProfile -Command "[ScriptBlock]::Create((Get-Content -Raw ...))"`
   - `pwsh -NoProfile -Command "[ScriptBlock]::Create((Get-Content -Raw ...))"`
4. Không chạy thử trên `Alkana_IT`, vì đây đang là máy chạy thật. Lần chạy thật đầu tiên diễn ra ở phase 3, trên máy mới, trước ngày chuyển, với `-Prepare`.
5. Cập nhật `deployment-guide.md`. Commit, push.

## Verification

- Kiểm tra cú pháp qua trên cả `powershell` 5.1 và `pwsh` 7.
- Trên máy Windows 10 mới (bước đầu của phase 3), chạy với `-Prepare -Archive <bản sao lưu gần nhất> -DataSource <bản chép thư mục dữ liệu>`:
  - script đi hết, bảng kiểm tra cuối chỉ còn các việc tay;
  - chạy lại lần hai: mọi bước in "đã có" hoặc "giữ nguyên", không hỏi lại mật khẩu, không khôi phục đè database.
- `http://<IP máy mới>:8750/login` trả 200 từ máy admin.

## Risk & Rollback

- **Gói `winget` đổi id hoặc phiên bản.** Script dừng ở bước cài kèm tên gói. Cài tay rồi chạy lại; script chỉ kiểm tra là "đã có".
- **PostgreSQL cài vào thư mục khác `16`.** Kiểm tra đường dẫn chuẩn sẽ dừng script. Truyền `-PgBin` cho các script con là việc của bản sau, chỉ làm nếu gặp thật.
- **Chạy nhầm dưới phiên admin.** Script từ chối ngay từ đầu.
- Lùi lại: script không động vào máy nào khác. Trên máy mới, gỡ phần đã cài hoặc cài lại Windows.
