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
5. Chép thư mục dữ liệu cũ (`-DataSource`) bằng `robocopy`. Khôi phục bản sao lưu (`-Archive`) khi database `shoponline` còn trống; database đã có dữ liệu thì không ghi đè. (Chuyển máy dùng `-Bundle` thay cho hai tham số này, sau `migrate`.)
6. `migrate`, đăng ký các tác vụ ẩn (mục 5), rồi một lần UAC để mở cổng web trên tường lửa (Domain, Private) và tắt chế độ ngủ khi cắm điện. Nếu mạng của máy đang là **Public** (`Get-NetConnectionProfile`), quy tắc này không có tác dụng và máy khác không mở được web: chuyển mạng nội bộ sang Private bằng `Set-NetConnectionProfile -InterfaceAlias <tên> -NetworkCategory Private`.
7. Cài runner deploy (mục 5b; `gh auth login` nếu chưa đăng nhập), bật web và robot.

Cuối cùng script in bảng kiểm tra: mục đã xong, và việc tay còn lại kèm hướng dẫn. Script chạy lại được bất cứ lúc nào: bước đã xong thì bỏ qua, không hỏi lại mật khẩu đã có trong `.env`.

`-Prepare` dựng máy trước ngày chuyển máy chạy thật từ máy cũ sang: không cài runner, và tác vụ robot để Disabled vì robot trên máy cũ còn dùng user SAP.

`-Bundle <file | drive:latest>` thay cho `-Archive` và `-DataSource` khi chuyển máy: nạp gói do `server-export.ps1` tạo (database, tài khoản web và lịch sao lưu, thư mục dữ liệu, dòng `.env` còn thiếu), so số dòng với manifest, và từ chối cài runner hoặc bật robot khi GitHub còn một runner nhãn `shoponline-prod` khác. `drive:latest` hỏi Client ID, Secret của OAuth client Google (cùng project máy cũ), kết nối Drive bằng mã thiết bị rồi tải bản `full` mới nhất. Xem [Chuyển máy chạy thật](#chuyển-máy-chạy-thật-sang-máy-khác).

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
| `SHOPONLINE_BACKUP_DIRS` | Thư mục nhận bản sao lưu, ví dụ `\\fileserver\it\shoponline-backup;D:\backup`. Google Drive không khai ở đây mà kết nối trên trang **Sao lưu** (mục 6b) |
| `SHOPONLINE_RESTORE_DATABASE_URL` | Một database tạm để diễn tập khôi phục, không bao giờ là `shoponline`; thêm tay (cần tạo database này bằng quyền `postgres`: role ứng dụng không có quyền tạo database) |

`SHOPONLINE_BACKUP_KEEP_DAYS` không còn tác dụng: giờ sao lưu và số bản giữ đặt trên trang **Sao lưu**.

Thư mục dữ liệu chứa file sàn, file gửi kế toán có tên và địa chỉ khách, nên chỉ tài khoản hệ thống và quản trị viên đọc được. Mật khẩu sao lưu chỉ nằm trong `.env` của máy chạy thật và trong kho bí mật, không đặt cạnh bản sao lưu.

## 5. Task Scheduler

Chạy trong PowerShell 7 với quyền quản trị:

```powershell
pwsh -ExecutionPolicy Bypass -File scripts\windows\register-tasks.ps1 -User MAYCHU\shoponline
```

Script dừng lại nếu cổng web đang có tiến trình khác giữ; khi đó dừng tiến trình cũ hoặc đổi `SHOPONLINE_WEB_PORT`, không chạy thêm bản thứ hai. Script đăng ký các tác vụ:

- `shoponline-web`: chạy `uv run shoponline web` khi máy khởi động, tự chạy lại nếu dừng.
- `shoponline-backup`: chạy `uv run shoponline backup run --if-due` **mỗi 15 phút** (tối đa 3 giờ một lần chạy, không chạy chồng). Nó làm các yêu cầu admin bấm trên web, rồi chạy bản tới lịch. Giờ chạy đặt trên trang **Sao lưu**, không cần đăng ký lại. `-BackupTime` không còn tác dụng.
- `shoponline-restore`: không có lịch; chạy khi admin bấm phục hồi hệ thống thật trên web (`backup process-queue --restore`).
- `shoponline-retention`: hằng ngày lúc 12:30 (`-RetentionTime`), dọn file hết dùng, ghi vào `<SHOPONLINE_DATA_DIR>\logs\retention.log`. Dữ liệu khách được giữ vĩnh viễn; `-RetentionApply` không còn tác dụng (xem [security-and-data-retention.md](security-and-data-retention.md#thời-hạn-lưu)).

Mọi tác vụ chạy ẩn, không mở cửa sổ nào để người khác lỡ tay đóng:

- Script chạy chương trình qua `conhost.exe --headless`. Cách này cần thiết trên Windows 11, nơi Windows Terminal bỏ qua `pwsh -WindowStyle Hidden`.
- Trước khi đăng ký, script thử `conhost --headless` một lần. Máy không qua được bài thử thì script quay về `pwsh -WindowStyle Hidden` và in cảnh báo: tác vụ vẫn chạy, chỉ có thể hiện cửa sổ.
- Tác vụ được phép chạy khi máy dùng pin và không dừng khi rút sạc.

Muốn biết web và robot có đang chạy không, xem cột Status trong Task Scheduler hoặc trang **Robot SAP**. Log của web ở `<SHOPONLINE_DATA_DIR>\logs\web.log` (lỗi và log ứng dụng; truy cập chỉ ghi từ mức WARNING), log của robot ở `logs\robot.log`.

Web, `shoponline-backup`, `shoponline-restore` và lệnh `uv run shoponline drive ...` phải chạy dưới **cùng một tài khoản Windows**: Client Secret và refresh token của Google Drive nằm trong Windows Credential Manager của tài khoản đó. Chế độ `-AtLogOn` đáp ứng điều này; với tài khoản riêng (`-User MAYCHU\shoponline`) thì chạy `drive connect` bằng chính tài khoản đó.

`register-tasks.ps1 -OnlyMissing` (deploy gọi mỗi lần) giữ trigger của mọi tác vụ có sẵn, trừ `shoponline-backup`: nếu nó còn trigger hằng ngày cũ thì được đổi sang lặp 15 phút. Lùi tính năng này: chạy lại `register-tasks.ps1` **không** có `-OnlyMissing` từ commit trước (trả trigger hằng ngày), và `Unregister-ScheduledTask shoponline-restore`.

Mở cổng web trên Windows Firewall cho mạng nội bộ (profile Domain hoặc Private), không mở ra Internet.

Robot SAP (phase 5 trở đi) đăng ký riêng bằng `-RobotUser`, sau khi dựng máy theo [robot-machine-setup.md](robot-machine-setup.md).

**Máy chỉ một người đăng nhập** (không có tài khoản `shoponline` riêng): thêm `-AtLogOn` và dùng chính tài khoản đang đăng nhập. Các tác vụ khi đó chạy trong phiên của người dùng mỗi lần đăng nhập, không lưu mật khẩu Windows và không cần quyền quản trị. Đổi lại, web chỉ chạy khi người dùng đó đang đăng nhập.

```powershell
pwsh -ExecutionPolicy Bypass -File scripts\windows\register-tasks.ps1 -User $env:USERDOMAIN\$env:USERNAME -AtLogOn
```

## 5b. Tự động triển khai khi push `main`

[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) chạy test trên GitHub (PostgreSQL 16), sau đó giao bước deploy cho self-hosted runner có nhãn `shoponline-prod` trên máy chạy thật. Runner gọi [`update-production.ps1`](../scripts/windows/update-production.ps1) trong `C:\shoponline`. Script từ chối chạy khi đang có phục hồi hoặc chuyển máy, rồi dừng robot và web, sao lưu database (bản `db` chỉ ở máy chủ, không lên Drive; mã thoát 0 hoặc 2 thì đi tiếp, 1 hoặc 3 thì dừng), tạm tắt tác vụ sao lưu và phục hồi, fast-forward tới commit vừa push, chạy `uv sync --frozen --no-dev --extra robot` và `migrate`. Sau đó nó đăng ký các tác vụ còn thiếu cho tài khoản chạy runner (`register-tasks.ps1 -AtLogOn -OnlyMissing`: web, sao lưu, retention, robot), khởi động lại web, chờ trang `/login` trả lời và bật robot. Tác vụ đã có mà lệnh chạy hoặc cài đặt pin khác bản script đang đăng ký thì được cập nhật (log deploy in "Cập nhật cách chạy …"); trigger, tài khoản và chế độ `--apply` của retention được giữ nguyên. Deploy cũng cập nhật như vậy cho tác vụ `shoponline-deploy-runner` (`install-deploy-runner.ps1 -TaskOnly`); runner đang chạy job giữ cách chạy cũ tới lần đăng nhập sau. Robot luôn được bật khi deploy: nó khởi động được cả khi cấu hình SAP chưa đủ, và trang **Kết nối SAP** báo thiếu gì (cấu hình SAP nằm trong database, mật khẩu trong Windows Credential Manager của tài khoản chạy robot; xem [robot-machine-setup.md](robot-machine-setup.md)). Nếu robot thoát ngay sau khi bật, job deploy báo lỗi. Nếu lỗi giữa chừng, script in commit cũ để lùi lại và vẫn cố khởi động web và robot.

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
2. Trang **Sao lưu** → **Sao lưu ngay** → Database: dòng "Đang chạy" hiện trong bảng, rồi thành "Thành công"; file `.7z` xuất hiện ở mọi thư mục đích và dòng cam cảnh báo sao lưu hết.
3. Kết nối Google Drive (mục 6b), rồi sao lưu lại với ô "Lưu thêm 1 bản lên Google Drive": cột Google Drive báo "Đã lên Drive (MD5 khớp)".
4. Diễn tập khôi phục: dòng của bản vừa tạo → **Phục hồi…** → Diễn tập (cần `SHOPONLINE_RESTORE_DATABASE_URL`). Số dòng phải khớp manifest. Dòng lệnh: `uv run shoponline backup restore <bản> --drill`. Bản sao lưu cũ làm bằng `backup-db.ps1` trước đây (không có manifest) vẫn diễn tập được, chỉ không so được số dòng; `restore-db.ps1 -Archive <file .7z>` vẫn dùng như trước.

## 6b. Kết nối Google Drive

Cần một lần, bởi người có Gmail cá nhân sẽ giữ các bản sao lưu (bản sao lưu phụ thuộc tài khoản đó; xem [security-and-data-retention.md](security-and-data-retention.md#bí-mật)):

1. Trang **Sao lưu** → khối **Kết nối Google Drive** → **Hướng dẫn tạo OAuth Client (4 bước)**: tạo project, bật Google Drive API, consent screen loại External với scope `drive.file` rồi **Publish to production** (để ở Testing thì kết nối mất sau 7 ngày), tạo OAuth client ID loại **TVs and Limited Input devices**. Cất Client ID và Secret vào kho bí mật.
2. **Bước A**: dán Client ID và Secret, **Lưu**. Secret chỉ nằm trong Windows Credential Manager và không hiện lại.
3. **Bước B**: **Kết nối bằng mã thiết bị**, mở `google.com/device` trên máy bất kỳ, nhập mã, đồng ý. Trang hiện "Đã kết nối: <email>"; thư mục `shoponline-backup` được tạo đúng một lần.
4. **Kiểm tra kết nối** báo hoạt động, quyền bị thu hồi, hoặc thư mục bị xóa. **Ngắt kết nối** thu hồi quyền phía Google; file trên Drive còn nguyên.

Không dùng web: `uv run --extra robot shoponline drive set-client --client-id <id>`, rồi `drive connect`, `drive status --check`, `drive disconnect`.

## 7. Sao lưu và phục hồi hằng ngày

- **Lịch mặc định:** `db` mỗi ngày 16:30, `full` thứ Sáu 16:30 (ngay sau bản `db` cùng ngày), `app` chỉ khi bấm tay, cộng một bản `db` trước mỗi deploy. Sao lưu không dừng web hay robot nên chạy được trong giờ làm việc. Giờ và ngày sửa trên trang **Sao lưu**.
- **Giữ lại:** `db` 15 bản, `app` 15 bản, `full` tối đa 30 ngày (đặt được 7–90), như nhau ở máy chủ và Drive. Bản mới tới nơi nào thì nơi đó mới dọn bản cũ.
- **Bản của người khác gửi, hay bản từ máy cũ:** **Tải lên bản sao lưu** (tối đa 1 GB, chỉ file `.7z` của hệ thống này, phải mở được bằng mật khẩu sao lưu); file sai mật khẩu, bị sửa hay không mã hóa bị từ chối và xóa ngay.
- **Phục hồi:** xem [operations-runbook.md](operations-runbook.md#phục-hồi-dữ-liệu). Phục hồi thật chạy qua tác vụ `shoponline-restore`; lần đầu trên máy thật, kiểm tra tiến trình web quyền thường có chạy được `schtasks /Run` cho tác vụ đăng ký bằng quyền quản trị không. Nếu không, yêu cầu nằm lại và trang báo "tác vụ phục hồi không chạy" sau 2 phút: bấm chạy tay tác vụ trong Task Scheduler hoặc dùng dòng lệnh.

## Phiếu trả hàng: việc một lần khi bật

- Nhập số của biên bản đầu tiên, lấy từ người dùng: ô **Số bắt đầu** ở đầu trang Phiếu trả hàng (admin, một lần duy nhất), hoặc `uv run shoponline return-number start <số>`; `return-number show` để xem. Số thử trên máy phát triển không mang sang.
- Ký hiệu hóa đơn suy ra từ biến `SHOPONLINE_INVOICE_SYMBOL_PATTERN` (mặc định `1C{yy}TAL`, `yy` là hai số cuối năm hóa đơn); sai mẫu thì ứng dụng không khởi động.
- Hóa đơn nhập trước khi có cột tiền thì thiếu tiền: đọc lại zrsd003 của các tháng có hóa đơn cần trả.
- **Không `downgrade` migration `0012` khi đã có phiếu**: bảng bị xóa thì số đã in có thể bị cấp lại. Khôi phục bản sao lưu cũ thì chạy `uv run shoponline return-number repair` rồi so với số cao nhất đã in.

## Báo cáo quản lý: việc một lần khi bật

Làm theo thứ tự, trên máy chạy thật (migration `0013` đến `0016`):

1. Chỉ đọc: kiểm đơn hiện có đều sau 2026-11-11 (`SELECT min(ordered_at) FROM sales_order`) và mọi đơn Shopee thuộc shop đang bán. Lệch thì dừng và xem lại [plan](../plans/261125-0621-management-reporting-module/plan.md).
2. Sao lưu `db` (`pwsh -File scripts\windows\backup-db.ps1`); bản này cũng là bản `history-import --apply` đòi trong 2 giờ.
3. Deploy như thường; `migrate` chạy `0013` đến `0016`.
4. Chạy lại `scripts\windows\register-tasks.ps1` để tác vụ dọn file không còn `--apply`.
5. Đưa file lịch sử lên `C:\shoponline-data\incoming\` (file chứa tên và số điện thoại khách, không để trong cây mã nguồn; `docs/**/*.xlsx` đã bị `.gitignore` loại).
6. `shoponline history-import "C:\shoponline-data\incoming\<file>"` (chạy thử), đọc báo cáo, rồi thêm `--apply`. Không dùng `--skip-backup-check` ở production. Sau khi nạp, so số dòng và tổng `Customer paid` theo năm với báo cáo chạy thử rồi xóa bản trong `incoming\` (lệnh đã giữ một bản trong `exports\history\`).
7. Mở **Quy đổi tỉnh** và khai các tên huyện còn lại; mở `/reports` kiểm số liệu.
8. Tạo tài khoản cho quản lý: `shoponline create-user <tên> --role viewer`.

Lùi: revert code, không `alembic downgrade` khi đã có dữ liệu nhập tay hoặc lịch sử; hai view và bảng `history_sale_line` không ảnh hưởng code cũ.

## Cập nhật phiên bản

Khi đã cài runner (mục 5b), chỉ cần push lên `main`. Cập nhật tay, khi không có runner (nhớ tạm tắt `shoponline-backup` nếu nó đang chạy, vì nó giữ file trong `.venv`):

```powershell
Stop-ScheduledTask shoponline-web
cd C:\shoponline
git pull
uv sync
pwsh -File scripts\windows\backup-db.ps1   # sao lưu trước khi đổi schema (mã thoát 0 hoặc 2 mới đi tiếp)
uv run shoponline migrate
Start-ScheduledTask shoponline-web
```

**Cột Tiền Vô (migration `0009_platform_settlement`).** Lùi tính năng bằng cách revert code, **không** chạy `alembic downgrade` cho 0009: bảng `platform_settlement` còn lại không ảnh hưởng code cũ, và vì file quyết toán gốc đã bị xóa sau khi nhập, bảng là bản duy nhất của dữ liệu. Gỡ một lần nhập sai: sao lưu database, xóa các dòng `platform_settlement` có `import_batch_id` của lần nhập đó (tìm trong `import_batch`, `kind = 'settlement'`), rồi upload lại file đúng.

## Chuyển máy chạy thật sang máy khác

Máy chạy thật hiện tại: `AlkanaDuongPC` (Windows 10, `192.168.18.123`, tài khoản tự đăng nhập `this pc`), chuyển từ `Alkana_IT` ngày 2026-11-16.

Hai điều không được xảy ra cùng lúc:

- **Hai runner nhãn `shoponline-prod`.** GitHub giao job deploy cho runner nào đang rảnh, nên một push có thể lên nhầm máy.
- **Hai robot dùng `AL17016`.** Khóa robot nằm trong database của từng máy, nên hai robot ở hai máy không chặn nhau.

Việc chuyển gói thành hai lệnh dùng chung một bản `full` (database, tài khoản web và lịch sao lưu, thư mục dữ liệu, `.env` không có mật khẩu sao lưu), lưu ở máy chủ và trên Google Drive. Credential Manager không đi theo bản sao lưu, nên trên máy mới phải nhập lại **cùng** Client ID và Secret rồi kết nối lại Drive (cùng project thì thấy lại mọi bản cũ), và đặt lại mật khẩu SAP bằng `sap-password set`.

**Chuẩn bị** (máy cũ vẫn chạy):

1. Máy cũ: `pwsh -File scripts\windows\server-export.ps1 -Prepare` tạo một bản `full` (nguồn "Chuyển máy") và in đường dẫn ở máy chủ cùng tên trên Drive. Không dừng gì.
2. Máy mới: dựng theo mục 1 với `-Bundle <đường dẫn | drive:latest> -Prepare`. Không cài runner, robot để Disabled. Mở web máy mới từ máy admin để xem, nhưng không nhập liệu ở đó.

**Ngày chuyển** (ngoài giờ xử lý đơn):

1. Máy cũ: `pwsh -File scripts\windows\server-export.ps1`. Dừng ngay ở bước lỗi và in bước kế tiếp. Các bước: không có job Actions đang chạy → dừng và Disable runner, robot, web, sao lưu, phục hồi → bản `full` cuối **phải tới cả máy chủ lẫn Google Drive** → Disable retention → gỡ runner khỏi repo và kiểm GitHub không còn runner của máy này → ghi `released.json` vào thư mục dữ liệu.
2. Máy mới: `setup-production-machine.ps1 -Bundle drive:latest` (không `-Prepare`). Script cài công cụ, `migrate`, kết nối Drive, tải bản `full` mới nhất, nạp gói và so số dòng với manifest (lệch thì dừng trước khi cài runner), kiểm tra GitHub không còn runner nhãn `shoponline-prod` nào khác (kể cả offline), rồi cài runner và bật web, robot.
3. Làm các việc tay in ở bảng kiểm tra cuối: Autologon, SAP GUI, `sap-password set`, trang **Robot SAP → Kết nối SAP** bấm **Kiểm tra** (robot cũ đã tắt). Đăng nhập web bằng tài khoản cũ và xem trang **Sao lưu**.
4. Push một commit lên `main`: job `deploy` phải chạy xanh trên runner máy mới. Gửi admin địa chỉ `http://<IP máy mới>:8750`.

Máy cũ chỉ tắt, không xóa: các tác vụ để Disabled, `C:\shoponline`, `C:\actions-runner` và database giữ nguyên làm bản lùi lại. Xóa bản chép dữ liệu tạm sau khi máy mới ổn, vì nó chứa dữ liệu khách.

**Lùi lại**, khi admin chưa nhập liệu trên máy mới: dừng và Disable mọi tác vụ trên máy mới, gỡ runner của nó (`config.cmd remove`), rồi trên máy cũ `pwsh -File scripts\windows\server-export.ps1 -Rollback`: lệnh từ chối nếu GitHub còn runner nhãn `shoponline-prod` của máy khác, rồi Enable lại tác vụ, cài lại runner, bật web và robot. Nếu admin đã nhập liệu trên máy mới, trước đó sao lưu máy mới (bản `full`) và nạp vào máy cũ bằng `backup restore <bản> --production`, hoặc `--new-machine` trên một cài đặt trống.

## Khi máy hỏng

Admin quay lại làm file Excel bằng tay như trước. Trên máy mới: `setup-production-machine.ps1 -Bundle drive:latest`, nhập Client ID và Secret từ kho bí mật; script dùng bản `full` mới nhất trên Drive (dữ liệu sau bản đó mất; không có sao lưu liên tục). Script dừng ở bước kiểm runner khi GitHub còn runner cũ. Máy cũ đã hỏng nên không chạy được `server-export.ps1`: gỡ runner cũ ở GitHub (Settings → Actions → Runners), và **rào máy cũ trước khi bật nó lên lần nào nữa** (rút mạng, đăng nhập, Disable mọi tác vụ `shoponline-*`), vì nếu máy cũ bật lên với runner và robot còn nguyên, deploy và robot sẽ chạy ở hai nơi. Sau đó chạy lại script.

Không có Google Drive hay Gmail đó nữa: dùng bản `full` trong thư mục sao lưu ở ổ mạng công ty (`-Bundle <đường dẫn>`).

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