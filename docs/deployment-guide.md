# Hướng dẫn triển khai lên máy chạy thật

Dành cho người dựng hoặc dựng lại máy chạy thật. Máy phát triển làm theo [README](../README.md).

## 1. Chuẩn bị máy

Máy Windows riêng, bật liên tục, cùng mạng nội bộ với admin shop online. Cài:

- Python 3.12 trở lên (máy phát triển đang dùng 3.14) và [uv](https://docs.astral.sh/uv/).
- PostgreSQL 16, cài trực tiếp trên Windows, chỉ nghe `localhost` (mặc định của bộ cài).
- PowerShell 7 (`pwsh`) và 7-Zip.
- Git, để lấy mã nguồn.

Tạo một tài khoản Windows riêng cho hệ thống (ví dụ `shoponline`). Tài khoản này sở hữu thư mục mã nguồn, thư mục dữ liệu và chạy các tác vụ trong Task Scheduler.

## 2. Lấy mã và cài phụ thuộc

```powershell
git clone <địa chỉ repo> C:\shoponline
cd C:\shoponline
uv sync
```

Thêm `--extra robot` khi máy có SAP GUI và đã tới giai đoạn robot (phase 5 trở đi).

## 3. Database và file cấu hình

```powershell
pwsh -ExecutionPolicy Bypass -File scripts\windows\create-databases.ps1 -Environment prod -WriteEnvFile -DataDir D:\shoponline-data
```

Script liệt kê database đang có trên máy chủ và hỏi xác nhận trước khi tạo `shoponline` cùng role `shoponline_app`. Nó ghi `C:\shoponline\.env` với chuỗi kết nối, khóa phiên ngẫu nhiên và thư mục dữ liệu.

Mở `.env` và bổ sung:

| Biến | Giá trị |
|---|---|
| `SHOPONLINE_WEB_HOST` | Địa chỉ IP nội bộ của máy (để máy khác trong mạng mở được web) |
| `SHOPONLINE_WEB_PORT` | Mặc định `8750`; đổi nếu cổng đã bị chiếm |
| `SHOPONLINE_BACKUP_PASSWORD` | Mật khẩu mã hóa bản sao lưu, lấy từ kho bí mật |
| `SHOPONLINE_BACKUP_DIRS` | Ví dụ `\\fileserver\it\shoponline-backup;G:\My Drive\shoponline-backup` |
| `SHOPONLINE_RESTORE_DATABASE_URL` | Một database tạm để diễn tập khôi phục, không bao giờ là `shoponline` |

Giới hạn quyền của `.env` và thư mục dữ liệu chỉ cho tài khoản `shoponline` và quản trị viên. Thư mục dữ liệu chứa file sàn, file gửi kế toán có tên và địa chỉ khách.

Mật khẩu sao lưu chỉ nằm trong `.env` của máy chạy thật và trong kho bí mật, không đặt cạnh bản sao lưu.

## 4. Schema và người dùng

```powershell
uv run shoponline migrate
uv run shoponline create-user <tên admin> --role admin
uv run shoponline create-user <tên người xem> --role viewer
```

Nhập bảng ánh xạ trên web: trang **Ánh xạ SAP**, chọn sàn, mục **Nhập từ Excel**. Sheet đầu tiên phải có các cột `Tên sản phẩm`, `Tên phân loại`, `Mã SAP`, `Tên SAP`.

## 5. Task Scheduler

Chạy trong PowerShell 7 với quyền quản trị:

```powershell
pwsh -ExecutionPolicy Bypass -File scripts\windows\register-tasks.ps1 -User MAYCHU\shoponline -BackupTime 23:00
```

Script dừng lại nếu cổng web đang có tiến trình khác giữ; khi đó dừng tiến trình cũ hoặc đổi `SHOPONLINE_WEB_PORT`, không chạy thêm bản thứ hai. Script đăng ký ba tác vụ:

- `shoponline-web`: chạy `uv run shoponline web` khi máy khởi động, tự chạy lại nếu dừng.
- `shoponline-backup`: chạy `backup-db.ps1` hằng ngày.
- `shoponline-retention`: hằng ngày lúc 23:30 (`-RetentionTime`), liệt kê dữ liệu khách và file quá thời hạn lưu vào `<SHOPONLINE_DATA_DIR>\logs\retention.log`. Chỉ xóa thật khi đăng ký với `-RetentionApply`, sau một tuần xem log (xem [security-and-data-retention.md](security-and-data-retention.md#thời-hạn-lưu)).

Mở cổng web trên Windows Firewall cho mạng nội bộ (profile Domain hoặc Private), không mở ra Internet.

Robot SAP (phase 5 trở đi) đăng ký riêng bằng `-RobotUser`, sau khi dựng máy theo [robot-machine-setup.md](robot-machine-setup.md).

**Máy chỉ một người đăng nhập** (không có tài khoản `shoponline` riêng): thêm `-AtLogOn` và dùng chính tài khoản đang đăng nhập. Các tác vụ khi đó chạy trong phiên của người dùng mỗi lần đăng nhập, không lưu mật khẩu Windows và không cần quyền quản trị. Đổi lại, web chỉ chạy khi người dùng đó đang đăng nhập.

```powershell
pwsh -ExecutionPolicy Bypass -File scripts\windows\register-tasks.ps1 -User $env:USERDOMAIN\$env:USERNAME -AtLogOn
```

## 5b. Tự động triển khai khi push `main`

[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) chạy test trên GitHub (PostgreSQL 16), sau đó giao bước deploy cho self-hosted runner có nhãn `shoponline-prod` trên máy chạy thật. Runner gọi [`update-production.ps1`](../scripts/windows/update-production.ps1) trong `C:\shoponline`. Script dừng robot và web, sao lưu database, fast-forward tới commit vừa push, chạy `uv sync --frozen --no-dev --extra robot` và `migrate`. Sau đó nó đăng ký các tác vụ còn thiếu cho tài khoản chạy runner (`register-tasks.ps1 -AtLogOn -OnlyMissing`: web, sao lưu, retention, robot), khởi động lại web, chờ trang `/login` trả lời và bật robot. Tác vụ đã có được giữ nguyên, kể cả tùy chọn như `-RetentionApply`. Robot chỉ được bật khi cấu hình có đủ `SHOPONLINE_SAP_CONNECTION`, `SHOPONLINE_SAP_USER`, `SHOPONLINE_SAP_PASSWORD`; thiếu biến nào thì log deploy nêu tên biến đó. Nếu robot thoát ngay sau khi bật, job deploy báo lỗi. Nếu lỗi giữa chừng, script in commit cũ để lùi lại và vẫn cố khởi động web và robot.

Cài runner một lần, bằng tài khoản sở hữu `C:\shoponline` (cần `gh` đăng nhập với quyền admin repo):

```powershell
pwsh -ExecutionPolicy Bypass -File scripts\windows\install-deploy-runner.ps1
```

Script tải runner bản mới nhất, kiểm tra SHA-256, đăng ký vào repo, và tạo tác vụ `shoponline-deploy-runner` chạy khi người dùng đăng nhập. Push lúc runner đang tắt thì job deploy chờ trong hàng đợi cho tới khi runner chạy lại.

Ràng buộc an toàn:

- `C:\shoponline` chỉ được cập nhật qua GitHub. Sửa tay trong thư mục này làm deploy dừng lại.
- Workflow không có trigger `pull_request`. Repo bật chế độ bắt buộc duyệt workflow của mọi người đóng góp bên ngoài (`fork-pr-contributor-approval = all_external_contributors`), nên code từ fork không tự chạy trên máy chạy thật.
- Thay đổi trong `update-production.ps1` chỉ có hiệu lực từ lần deploy kế tiếp, vì runner chạy bản đang có trên đĩa.
- Chạy lại deploy bằng tay: tab Actions, workflow `deploy`, **Run workflow** (hoặc `gh workflow run deploy`). Khi máy đã ở đúng commit, lần chạy này chỉ đăng ký tác vụ còn thiếu và bật web, robot nếu đang tắt. Dùng nó sau khi điền cấu hình SAP cho robot.

## 6. Kiểm tra sau khi triển khai

1. Mở `http://<IP máy>:8750` từ máy admin, đăng nhập được.
2. Chạy tay tác vụ `shoponline-backup` trong Task Scheduler; kiểm tra file `.7z` xuất hiện ở cả hai thư mục đích và web không còn dòng cảnh báo sao lưu.
3. Diễn tập khôi phục một bản sao lưu vào database tạm:

   ```powershell
   pwsh -File scripts\windows\restore-db.ps1 -Archive <đường dẫn file .7z>
   ```

   Script đọc database đích từ `SHOPONLINE_RESTORE_DATABASE_URL` và từ chối ghi vào `shoponline` nếu thiếu `-AllowProduction`.

## Cập nhật phiên bản

Khi đã cài runner (mục 5b), chỉ cần push lên `main`. Cập nhật tay, khi không có runner:

```powershell
Stop-ScheduledTask shoponline-web
cd C:\shoponline
git pull
uv sync
pwsh -File scripts\windows\backup-db.ps1   # sao lưu trước khi đổi schema
uv run shoponline migrate
Start-ScheduledTask shoponline-web
```

## Khi máy hỏng

Admin quay lại làm file Excel bằng tay như trước. Dựng máy mới theo mục 1 đến 5, rồi khôi phục bản sao lưu gần nhất vào `shoponline` bằng `restore-db.ps1 -AllowProduction`, với `SHOPONLINE_RESTORE_DATABASE_URL` trỏ tới database thật.
