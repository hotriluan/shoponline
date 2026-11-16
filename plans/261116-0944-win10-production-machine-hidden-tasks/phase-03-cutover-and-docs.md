---
phase: 3
title: "Chuyển máy chạy thật và tài liệu"
status: pending
priority: P2
effort: 0.5d
dependencies: [2]
---

# Phase 3: Chuyển máy chạy thật và tài liệu

## Goal

Máy Windows 10 mới thành máy chạy thật duy nhất, mang đủ dữ liệu của `Alkana_IT`, nhận deploy khi push `main`. `Alkana_IT` chỉ còn là máy phát triển, giữ bản cũ đã tắt để lùi lại khi cần. Tài liệu mô tả cách chuyển máy.

## Bối cảnh

- `Alkana_IT` hiện đang:
  - chạy runner `ALKANA_IT-shoponline` (nhãn `shoponline-prod`);
  - có năm tác vụ `shoponline-*` chạy dưới tài khoản `luanh`;
  - giữ mật khẩu `AL17016` trong Credential Manager của `luanh`.
- Cấu hình SAP (hệ thống, client, mục SAP Logon, user) nằm trong database, nên đi theo bản sao lưu. Mật khẩu SAP thì không: phải đặt lại trên máy mới.
- Dữ liệu gồm database `shoponline` (đi theo bản `.7z` của `backup-db.ps1`) và thư mục `SHOPONLINE_DATA_DIR` (file sàn, file xuất, ảnh của robot, log), chép bằng `robocopy`.
- Phần việc trên máy thật do chủ dự án làm, có lập trình viên đi kèm. Mọi lệnh dưới đây chạy trong PowerShell 7.

## Requirements

### A. Chuẩn bị (trước ngày chuyển; `Alkana_IT` vẫn chạy)

1. Máy mới: tạo tài khoản Windows dùng cho hệ thống. Dùng Sysinternals Autologon cho tài khoản này. Tắt khóa màn hình và trình bảo vệ màn hình; đặt độ phân giải cố định.
2. Cài SAP GUI cùng phiên bản (7600.257.1), bật scripting phía máy khách, tạo mục SAP Logon trỏ `AEP`. Cài Microsoft Excel. Làm theo [robot-machine-setup.md](../../docs/robot-machine-setup.md) mục 2.
   - Thư mục sao lưu dùng giống `Alkana_IT`. Nếu `SHOPONLINE_BACKUP_DIRS` có thư mục Google Drive, cài Google Drive for desktop, đăng nhập cùng tài khoản, và kiểm tra đường dẫn thư mục đó có đúng không trước khi chạy script.
   - Nhờ IT đặt IP tĩnh hoặc DHCP reservation cho máy mới, để địa chỉ web gửi cho admin không đổi.
3. Trên `Alkana_IT`:
   - chạy tay `shoponline-backup`; file `.7z` nằm sẵn trong thư mục sao lưu;
   - chép thư mục dữ liệu lên thư mục chia sẻ của công ty: `robocopy <SHOPONLINE_DATA_DIR> \\<chia sẻ>\shoponline-migrate\data /E /COPY:DAT`.

   Giới hạn quyền thư mục `shoponline-migrate` cho chủ dự án, vì nó chứa dữ liệu khách.
4. Máy mới: tải script đầu tiên từ repo public rồi chạy:
   ```powershell
   Invoke-WebRequest https://raw.githubusercontent.com/hotriluan/shoponline/main/scripts/windows/setup-production-machine.ps1 -OutFile $env:TEMP\setup.ps1
   powershell -ExecutionPolicy Bypass -File $env:TEMP\setup.ps1 -Prepare -Archive <file .7z trong thư mục sao lưu> -DataSource \\<chia sẻ>\shoponline-migrate\data
   ```
5. Máy mới: `uv run --extra robot shoponline sap-password set`. Chưa bấm Kiểm tra SAP, vì robot cũ vẫn đang dùng `AL17016`.
6. Từ máy admin: mở `http://<IP máy mới>:8750/login`, đăng nhập được, thấy dữ liệu tới ngày chuẩn bị. Báo admin đây là bản thử: không nhập liệu ở đây.

### B. Ngày chuyển (ngoài giờ xử lý đơn; khoảng 1 giờ)

1. **Đếm dữ liệu trên `Alkana_IT` trước khi dừng:** chạy một câu SQL đếm dòng mọi bảng trong schema `public` và lưu kết quả vào file. Câu lệnh nằm trong mục "Chuyển máy" của tài liệu (Requirement C).
2. **Dừng hẳn `Alkana_IT`**, theo thứ tự: runner, robot, web.
   - `Stop-ScheduledTask` và `Disable-ScheduledTask` cho `shoponline-deploy-runner`. Dừng tiến trình `Runner.Listener` nếu còn.
   - Tiếp theo là `shoponline-robot`, rồi `shoponline-web`. Dừng tiến trình Python của chúng giống `Stop-Robot` và `Stop-Web` trong `update-production.ps1`.
   - Không có job deploy nào đang chạy (tab Actions).
3. **Sao lưu cuối:** chạy `backup-db.ps1` tay trên `Alkana_IT`. Sau đó `Disable-ScheduledTask` cho `shoponline-backup` và `shoponline-retention`.
4. **Gỡ runner cũ khỏi repo:**
   ```powershell
   $t = gh api -X POST repos/hotriluan/shoponline/actions/runners/remove-token -q .token
   C:\actions-runner\config.cmd remove --token $t
   ```
   Kiểm tra lại: `gh api repos/hotriluan/shoponline/actions/runners` không còn `ALKANA_IT-shoponline`.
5. **Máy mới: nạp dữ liệu cuối.**
   - Dừng web: `Stop-ScheduledTask shoponline-web`.
   - Chép phần thư mục dữ liệu đã đổi:
     - trên `Alkana_IT`, chạy lại robocopy ra `\\<chia sẻ>\shoponline-migrate\data`;
     - trên máy mới, `robocopy \\<chia sẻ>\shoponline-migrate\data <DataDir> /E /COPY:DAT`.
   - Khôi phục đè: `restore-db.ps1 -Archive <bản cuối> -TargetSetting SHOPONLINE_DATABASE_URL -AllowProduction`.
   - `uv run --no-dev shoponline migrate`.
6. **Máy mới chạy chính thức:** chạy lại `setup-production-machine.ps1` không có `-Prepare`. Script cài runner (`gh auth login` nếu chưa đăng nhập), bật tác vụ robot, rồi bật web và robot.
7. **Kiểm tra SAP:** trang **Robot SAP → Kết nối SAP**: robot "đang chạy" trên máy mới, mật khẩu "đã có". Bấm **Kiểm tra**, phải thành công với `AEP/300/AL17016`.
8. **So dữ liệu:** chạy lại câu SQL đếm trên máy mới, kết quả phải khớp file của bước 1.
9. **Push thử:** commit tài liệu của phase này lên `main`. Job `deploy` phải chạy trên runner của máy mới và xanh.
10. Gửi admin địa chỉ mới `http://<IP máy mới>:8750`.

### C. Tài liệu (commit ở bước B.9)

- [deployment-guide.md](../../docs/deployment-guide.md): thêm mục "Chuyển máy chạy thật sang máy khác" theo A và B. Gồm:
  - câu SQL đếm dòng;
  - lệnh gỡ runner;
  - cảnh báo hai runner cùng nhãn và hai robot cùng user SAP;
  - cách lùi lại.

  Mục "Khi máy hỏng" dùng `setup-production-machine.ps1`.
- [robot-machine-setup.md](../../docs/robot-machine-setup.md): đổi câu "máy dùng chung hiện tại (tài khoản `luanh`)" thành máy chạy thật Windows 10 mới, dùng một tài khoản tự đăng nhập.
- [security-and-data-retention.md](../../docs/security-and-data-retention.md): ghi rằng máy chạy thật dùng Windows 10 không có ESU, chủ dự án đã chấp nhận rủi ro ngày 2026-11-16, kèm các biện pháp bù:
  - chỉ mở cổng web cho mạng nội bộ;
  - không duyệt web hay đọc mail trên máy;
  - quyền `.env` và thư mục dữ liệu bị giới hạn.

### D. Sau khi chuyển

- `Alkana_IT` **chỉ tắt, giữ lại** (chủ dự án chốt 2026-11-16):
  - các tác vụ `shoponline-*` để Disabled;
  - `C:\shoponline`, `C:\actions-runner` và database `shoponline` giữ nguyên, không xóa.

  Đây là bản lùi lại.
- Xóa thư mục `\\<chia sẻ>\shoponline-migrate` sau khi so dữ liệu khớp (bước B.8), vì nó chứa dữ liệu khách.

## Files to Create / Modify

- Modify: `docs/deployment-guide.md`, `docs/robot-machine-setup.md`, `docs/security-and-data-retention.md`

## Verification

Đối chiếu tiêu chí 1, 5–10 của [plan.md](plan.md#tiêu-chí-hoàn-thành):
- `gh api repos/hotriluan/shoponline/actions/runners` chỉ có runner của máy mới, nhãn `shoponline-prod`, trạng thái online.
- Job `deploy` của commit ở bước B.9 xanh, chạy trên runner máy mới.
- File đếm dòng trước và sau giống hệt nhau.
- Kiểm tra SAP thành công. Robot của máy mới đọc thử được một báo cáo `zrsd004` bằng form "Ra lệnh cho robot".
- Chạy tay `shoponline-backup` trên máy mới: có file `.7z` ở các thư mục đích. Diễn tập khôi phục vào `SHOPONLINE_RESTORE_DATABASE_URL` thành công.
- Khởi động lại máy mới: máy tự đăng nhập, web, robot và runner tự chạy, không có cửa sổ nào hiện.

## Risk & Rollback

- **Lùi lại trước bước B.9 (máy mới chưa nhận dữ liệu thật):**
  - trên `Alkana_IT`, `Enable-ScheduledTask` cho năm tác vụ, chạy lại `install-deploy-runner.ps1` để đăng ký runner, `Start-ScheduledTask` web và robot;
  - trên máy mới, dừng và Disable mọi tác vụ, gỡ runner bằng `config.cmd remove`.
- **Lùi lại sau khi admin đã nhập liệu trên máy mới:** sao lưu trên máy mới, khôi phục bản đó vào `Alkana_IT` bằng `restore-db.ps1 -AllowProduction`, chép lại thư mục dữ liệu, rồi làm như trên.
- **Robot hai nơi:** robot cũ phải Disabled trước khi máy mới chạy chính thức (bước B.2 trước B.6). Nếu thấy hai robot báo về trang Kết nối SAP, dừng robot máy mới ngay.
- **Bước B.4 lỗi** (token hết hạn): gỡ runner trên web GitHub, ở Settings → Actions → Runners. Không bỏ qua bước này.
