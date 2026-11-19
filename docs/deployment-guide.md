# Hướng dẫn triển khai lên máy chạy thật

Dành cho người dựng hoặc dựng lại máy chạy thật. Máy phát triển làm theo [README](../README.md).

## 1. Dựng máy bằng script

Máy Windows 10 hoặc 11 64-bit, bật liên tục, cùng mạng nội bộ với admin shop online, có `winget` (App Installer). Tạo một tài khoản Windows thường cho hệ thống. Tài khoản này sở hữu `C:\shoponline`, `.env` và thư mục dữ liệu, chạy mọi tác vụ, và nên tự đăng nhập khi máy khởi động.

Đăng nhập tài khoản đó, mở PowerShell **thường** (không Run as administrator), rồi chạy:

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/hotriluan/shoponline/main/scripts/windows/setup-production-machine.ps1 -OutFile $env:TEMP\setup.ps1
powershell -ExecutionPolicy Bypass -File $env:TEMP\setup.ps1 -Archive <file .7z> -DataSource <thư mục dữ liệu cũ>
```

[`setup-production-machine.ps1`](../scripts/windows/setup-production-machine.ps1) làm lần lượt:

1. Cài Git, PowerShell 7, 7-Zip, GitHub CLI, PostgreSQL 16 và uv bằng `winget`. Mỗi gói cài theo máy hỏi UAC một lần. Bộ cài PostgreSQL hỏi mật khẩu superuser `postgres`: ghi nhớ nó cho bước tạo database.
2. Lấy mã về `C:\shoponline`. Thư mục đã có thì phải sạch, và được fast-forward tới `origin/main`.
3. Chạy tiếp dưới `pwsh`: `uv sync`, tạo database và `.env` ([`create-databases.ps1`](../scripts/windows/create-databases.ps1)), rồi hỏi những dòng `.env` còn thiếu: IP web trong mạng nội bộ, thư mục sao lưu, mật khẩu sao lưu.
4. Giới hạn quyền `.env` và thư mục dữ liệu cho tài khoản này, Administrators và SYSTEM.
5. Chép thư mục dữ liệu cũ (`-DataSource`) bằng `robocopy`. Khôi phục bản sao lưu (`-Archive`) khi database `shoponline` còn trống; database đã có dữ liệu thì không ghi đè.
6. `migrate`, đăng ký các tác vụ ẩn (mục 5), rồi một lần UAC để mở cổng web trên tường lửa (Domain, Private) và tắt chế độ ngủ khi cắm điện. Nếu mạng của máy đang là **Public** (`Get-NetConnectionProfile`), quy tắc này không có tác dụng và máy khác không mở được web: chuyển mạng nội bộ sang Private bằng `Set-NetConnectionProfile -InterfaceAlias <tên> -NetworkCategory Private`.
7. Cài runner deploy (mục 5b; `gh auth login` nếu chưa đăng nhập), bật web và robot.

Cuối cùng script in bảng kiểm tra: mục đã xong, và việc tay còn lại kèm hướng dẫn. Script chạy lại được bất cứ lúc nào: bước đã xong thì bỏ qua, không hỏi lại mật khẩu đã có trong `.env`.

`-Prepare` dựng máy trước ngày chuyển máy chạy thật từ máy cũ sang: không cài runner, và tác vụ robot để Disabled vì robot trên máy cũ còn dùng user SAP.

## 2. Việc tay sau script

Làm theo [robot-machine-setup.md](robot-machine-setup.md) mục 1–2:

- Sysinternals Autologon cho tài khoản hệ thống; tắt khóa màn hình và trình bảo vệ màn hình; đặt độ phân giải cố định.
- Cài SAP GUI cùng phiên bản máy cũ, bật scripting phía máy khách, tạo mục SAP Logon trỏ `AEP`. Cài Microsoft Excel.
- Nếu thư mục sao lưu nằm trên Google Drive: cài Google Drive for desktop và đăng nhập trước khi chạy script.
- `uv run --extra robot shoponline sap-password set`, rồi trang **Robot SAP → Kết nối SAP** → **Kiểm tra**.

## 3. Người dùng và bảng ánh xạ

Chỉ cần khi máy bắt đầu với database trống (không có `-Archive`):

```powershell
uv run shoponline create-user <tên admin> --role admin
uv run shoponline create-user <tên người xem> --role viewer
```

Nhập bảng ánh xạ trên web: trang **Ánh xạ SAP**, chọn sàn, mục **Nhập từ Excel**. Sheet đầu tiên phải có các cột `Tên sản phẩm`, `Tên phân loại`, `Mã SAP`, `Tên SAP`.

## 4. File cấu hình `.env`

Script ghi sẵn các dòng chính. Bảng dưới để tra cứu và sửa tay:

| Biến | Giá trị |
|---|---|
| `SHOPONLINE_WEB_HOST` | Địa chỉ IP nội bộ của máy (để máy khác trong mạng mở được web) |
| `SHOPONLINE_WEB_PORT` | Mặc định `8750`; đổi nếu cổng đã bị chiếm |
| `SHOPONLINE_BACKUP_PASSWORD` | Mật khẩu mã hóa bản sao lưu, lấy từ kho bí mật |
| `SHOPONLINE_BACKUP_DIRS` | Ví dụ `\\fileserver\it\shoponline-backup;G:\My Drive\shoponline-backup` |
| `SHOPONLINE_RESTORE_DATABASE_URL` | Một database tạm để diễn tập khôi phục, không bao giờ là `shoponline`; thêm tay |

Thư mục dữ liệu chứa file sàn, file gửi kế toán có tên và địa chỉ khách, nên chỉ tài khoản hệ thống và quản trị viên đọc được. Mật khẩu sao lưu chỉ nằm trong `.env` của máy chạy thật và trong kho bí mật, không đặt cạnh bản sao lưu.

## 5. Task Scheduler

Chạy trong PowerShell 7 với quyền quản trị:

```powershell
pwsh -ExecutionPolicy Bypass -File scripts\windows\register-tasks.ps1 -User MAYCHU\shoponline -BackupTime 23:00
```

Script dừng lại nếu cổng web đang có tiến trình khác giữ; khi đó dừng tiến trình cũ hoặc đổi `SHOPONLINE_WEB_PORT`, không chạy thêm bản thứ hai. Script đăng ký ba tác vụ:

- `shoponline-web`: chạy `uv run shoponline web` khi máy khởi động, tự chạy lại nếu dừng.
- `shoponline-backup`: chạy `backup-db.ps1` hằng ngày.
- `shoponline-retention`: hằng ngày lúc 23:30 (`-RetentionTime`), xóa file hết dùng và liệt kê dữ liệu khách quá thời hạn lưu vào `<SHOPONLINE_DATA_DIR>\logs\retention.log`. Dữ liệu khách chỉ bị xóa thật khi đăng ký với `-RetentionApply`, sau một tuần xem log (xem [security-and-data-retention.md](security-and-data-retention.md#thời-hạn-lưu)).

Mọi tác vụ chạy ẩn, không mở cửa sổ nào để người khác lỡ tay đóng:

- Script chạy chương trình qua `conhost.exe --headless`. Cách này cần thiết trên Windows 11, nơi Windows Terminal bỏ qua `pwsh -WindowStyle Hidden`.
- Trước khi đăng ký, script thử `conhost --headless` một lần. Máy không qua được bài thử thì script quay về `pwsh -WindowStyle Hidden` và in cảnh báo: tác vụ vẫn chạy, chỉ có thể hiện cửa sổ.
- Tác vụ được phép chạy khi máy dùng pin và không dừng khi rút sạc.

Muốn biết web và robot có đang chạy không, xem cột Status trong Task Scheduler hoặc trang **Robot SAP**. Log của web ở `<SHOPONLINE_DATA_DIR>\logs\web.log` (lỗi và log ứng dụng; truy cập chỉ ghi từ mức WARNING), log của robot ở `logs\robot.log`.

Mở cổng web trên Windows Firewall cho mạng nội bộ (profile Domain hoặc Private), không mở ra Internet.

Robot SAP (phase 5 trở đi) đăng ký riêng bằng `-RobotUser`, sau khi dựng máy theo [robot-machine-setup.md](robot-machine-setup.md).

**Máy chỉ một người đăng nhập** (không có tài khoản `shoponline` riêng): thêm `-AtLogOn` và dùng chính tài khoản đang đăng nhập. Các tác vụ khi đó chạy trong phiên của người dùng mỗi lần đăng nhập, không lưu mật khẩu Windows và không cần quyền quản trị. Đổi lại, web chỉ chạy khi người dùng đó đang đăng nhập.

```powershell
pwsh -ExecutionPolicy Bypass -File scripts\windows\register-tasks.ps1 -User $env:USERDOMAIN\$env:USERNAME -AtLogOn
```

## 5b. Tự động triển khai khi push `main`

[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) chạy test trên GitHub (PostgreSQL 16), sau đó giao bước deploy cho self-hosted runner có nhãn `shoponline-prod` trên máy chạy thật. Runner gọi [`update-production.ps1`](../scripts/windows/update-production.ps1) trong `C:\shoponline`. Script dừng robot và web, sao lưu database, fast-forward tới commit vừa push, chạy `uv sync --frozen --no-dev --extra robot` và `migrate`. Sau đó nó đăng ký các tác vụ còn thiếu cho tài khoản chạy runner (`register-tasks.ps1 -AtLogOn -OnlyMissing`: web, sao lưu, retention, robot), khởi động lại web, chờ trang `/login` trả lời và bật robot. Tác vụ đã có mà lệnh chạy hoặc cài đặt pin khác bản script đang đăng ký thì được cập nhật (log deploy in "Cập nhật cách chạy …"); trigger, tài khoản và chế độ `--apply` của retention được giữ nguyên. Deploy cũng cập nhật như vậy cho tác vụ `shoponline-deploy-runner` (`install-deploy-runner.ps1 -TaskOnly`); runner đang chạy job giữ cách chạy cũ tới lần đăng nhập sau. Robot luôn được bật khi deploy: nó khởi động được cả khi cấu hình SAP chưa đủ, và trang **Kết nối SAP** báo thiếu gì (cấu hình SAP nằm trong database, mật khẩu trong Windows Credential Manager của tài khoản chạy robot; xem [robot-machine-setup.md](robot-machine-setup.md)). Nếu robot thoát ngay sau khi bật, job deploy báo lỗi. Nếu lỗi giữa chừng, script in commit cũ để lùi lại và vẫn cố khởi động web và robot.

Cài runner một lần, bằng tài khoản sở hữu `C:\shoponline` (cần `gh` đăng nhập với quyền admin repo):

```powershell
pwsh -ExecutionPolicy Bypass -File scripts\windows\install-deploy-runner.ps1
```

Script tải runner bản mới nhất, kiểm tra SHA-256, đăng ký vào repo, và tạo tác vụ `shoponline-deploy-runner` chạy khi người dùng đăng nhập. Push lúc runner đang tắt thì job deploy chờ trong hàng đợi cho tới khi runner chạy lại.

Ràng buộc an toàn:

- `C:\shoponline` chỉ được cập nhật qua GitHub. Sửa tay trong thư mục này làm deploy dừng lại.
- Workflow không có trigger `pull_request`. Repo bật chế độ bắt buộc duyệt workflow của mọi người đóng góp bên ngoài (`fork-pr-contributor-approval = all_external_contributors`), nên code từ fork không tự chạy trên máy chạy thật.
- Thay đổi trong `update-production.ps1` chỉ có hiệu lực từ lần deploy kế tiếp, vì runner chạy bản đang có trên đĩa.
- Chạy lại deploy bằng tay: tab Actions, workflow `deploy`, **Run workflow** (hoặc `gh workflow run deploy`). Khi máy đã ở đúng commit, lần chạy này chỉ đăng ký tác vụ còn thiếu hoặc lệch và bật web, robot nếu đang tắt. Dùng nó khi robot cần được bật lại hoặc tác vụ còn thiếu.

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

**Cột Tiền Vô (migration `0009_platform_settlement`).** Lùi tính năng bằng cách revert code, **không** chạy `alembic downgrade` cho 0009: bảng `platform_settlement` còn lại không ảnh hưởng code cũ, và vì file quyết toán gốc đã bị xóa sau khi nhập, bảng là bản duy nhất của dữ liệu. Gỡ một lần nhập sai: sao lưu database, xóa các dòng `platform_settlement` có `import_batch_id` của lần nhập đó (tìm trong `import_batch`, `kind = 'settlement'`), rồi upload lại file đúng.

## Chuyển máy chạy thật sang máy khác

Máy chạy thật hiện tại: `AlkanaDuongPC` (Windows 10, `192.168.18.123`, tài khoản tự đăng nhập `this pc`), chuyển từ `Alkana_IT` ngày 2026-11-16.

Hai điều không được xảy ra cùng lúc:

- **Hai runner nhãn `shoponline-prod`.** GitHub giao job deploy cho runner nào đang rảnh, nên một push có thể lên nhầm máy.
- **Hai robot dùng `AL17016`.** Khóa robot nằm trong database của từng máy, nên hai robot ở hai máy không chặn nhau.

**Chuẩn bị** (máy cũ vẫn chạy): dựng máy mới theo mục 1 với `-Prepare`, `-Archive` là một bản sao lưu mới và `-DataSource` là bản chép thư mục dữ liệu; làm mục 2 trừ bước **Kiểm tra** SAP. Mở web máy mới từ máy admin, nhưng không nhập liệu ở đó.

**Ngày chuyển** (ngoài giờ xử lý đơn):

1. Máy cũ: dừng và Disable theo thứ tự `shoponline-deploy-runner` (dừng cả `Runner.Listener`), `shoponline-robot`, `shoponline-web`. Tab Actions không có job nào đang chạy.
2. Máy cũ: đếm dòng mọi bảng và lưu ra file, chạy tay `backup-db.ps1`, rồi Disable `shoponline-backup` và `shoponline-retention`. Câu đếm, chạy bằng `psql` với role `shoponline_app`:

   ```sql
   SELECT table_name,
          (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM public.%I', table_name), false, true, '')))[1]::text::int AS rows
   FROM information_schema.tables
   WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
   ORDER BY 1;
   ```

3. Máy cũ: gỡ runner khỏi repo, rồi kiểm tra `gh api repos/hotriluan/shoponline/actions/runners` không còn tên máy cũ:

   ```powershell
   $t = gh api -X POST repos/hotriluan/shoponline/actions/runners/remove-token -q .token
   C:\actions-runner\config.cmd remove --token $t
   ```

4. Máy mới: dừng `shoponline-web`, chép lại thư mục dữ liệu bằng `robocopy /E /COPY:DAT`, khôi phục đè bản sao lưu cuối (`restore-db.ps1 -Archive <bản cuối> -TargetSetting SHOPONLINE_DATABASE_URL -AllowProduction`), `uv run --no-dev shoponline migrate`.
5. Máy mới: chạy lại script mục 1 **không** có `-Prepare`. Script cài runner và bật web, robot.
6. Trang **Robot SAP → Kết nối SAP**: robot chạy trên máy mới, mật khẩu "đã có", **Kiểm tra** thành công với `AEP/300/AL17016`.
7. Đếm lại trên máy mới; kết quả phải giống file ở bước 2.
8. Push một commit lên `main`: job `deploy` phải chạy xanh trên runner máy mới. Gửi admin địa chỉ `http://<IP máy mới>:8750`.

Máy cũ chỉ tắt, không xóa: các tác vụ để Disabled, `C:\shoponline`, `C:\actions-runner` và database giữ nguyên làm bản lùi lại. Xóa bản chép dữ liệu tạm sau khi bước 7 khớp, vì nó chứa dữ liệu khách.

**Lùi lại**, khi admin chưa nhập liệu trên máy mới: trên máy mới dừng và Disable mọi tác vụ, gỡ runner bằng `config.cmd remove`. Trên máy cũ Enable năm tác vụ, chạy `install-deploy-runner.ps1`, rồi `Start-ScheduledTask` web và robot. Nếu admin đã nhập liệu trên máy mới, trước đó sao lưu máy mới, khôi phục bản đó vào máy cũ bằng `restore-db.ps1 -AllowProduction` và chép lại thư mục dữ liệu.

## Khi máy hỏng

Admin quay lại làm file Excel bằng tay như trước. Dựng máy mới theo mục 1 và 2, truyền `-Archive` là bản sao lưu gần nhất trong thư mục sao lưu: script khôi phục nó vào database `shoponline` còn trống. Nếu máy cũ có runner, gỡ nó khỏi repo (GitHub → Settings → Actions → Runners) để chỉ còn một runner nhãn `shoponline-prod`.

## Phụ lục: dựng máy tay (máy không có `winget`)

1. Cài Python 3.12 trở lên, [uv](https://docs.astral.sh/uv/), PostgreSQL 16 (chỉ nghe `localhost`, thư mục mặc định), PowerShell 7, 7-Zip, Git và GitHub CLI.
2. Trong PowerShell 7, dưới tài khoản hệ thống:

   ```powershell
   git clone https://github.com/hotriluan/shoponline.git C:\shoponline
   cd C:\shoponline
   uv sync --frozen --no-dev --extra robot
   pwsh -ExecutionPolicy Bypass -File scripts\windows\create-databases.ps1 -Environment prod -WriteEnvFile -DataDir C:\shoponline-data
   ```

3. Bổ sung `.env` theo mục 4 và giới hạn quyền `.env`, thư mục dữ liệu.
4. Khôi phục bản sao lưu nếu có: `pwsh -File scripts\windows\restore-db.ps1 -Archive <file .7z> -TargetSetting SHOPONLINE_DATABASE_URL -AllowProduction`. Sau đó `uv run --no-dev shoponline migrate`.
5. Đăng ký tác vụ theo mục 5, mở cổng web trên tường lửa, cài runner theo mục 5b.