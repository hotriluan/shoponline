# shoponline

Hệ thống nội bộ xử lý đơn sàn TMĐT (Shopee, TikTok, Lazada) cho bộ phận shop online:

1. Admin tải file "chờ giao hàng" của sàn lên web.
2. Hệ thống ánh xạ sản phẩm sang mã SAP và sinh file `ĐƠN HÀNG ONLINE <SÀN> ddmmyy.xlsx` cho sales admin.
3. Sales admin tạo SO và DO trong SAP (chế độ thủ công), rồi admin xác nhận lô.
4. Admin tải `zrsd001` lên: hệ thống lưu cặp mã đơn ↔ số SO và báo các điểm lệch.
5. Admin mở trang **Gửi kế toán**: robot (hoặc file `zrsd004` tải tay) đọc DO của từng sàn và từng ngày goods issue; hệ thống gộp thành một file `SHOP ONLINE ddmmyy.xlsx` có thêm mã đơn, tên khách, địa chỉ, đối chiếu với đơn trên web rồi admin chốt. DO đã chốt không gửi lại.

Bước 4 và 5 có thể do robot SAP làm thay (chỉ đọc báo cáo trên Production, không tạo chứng từ): xem [docs/robot-runbook.md](docs/robot-runbook.md). Ở chế độ thủ công hệ thống không ghi gì vào SAP. Kế hoạch đầy đủ: [plans/261111-0755-shopee-excel-to-sap-order-flow/plan.md](plans/261111-0755-shopee-excel-to-sap-order-flow/plan.md).

## Yêu cầu

- Windows, Python 3.12 trở lên (máy phát triển dùng 3.14), [uv](https://docs.astral.sh/uv/).
- PostgreSQL 16 cài trực tiếp trên Windows, chỉ nghe `localhost`.
- 7-Zip (`C:\Program Files\7-Zip\7z.exe`) cho sao lưu mã hóa.
- `pywin32` (`uv sync --extra robot`) để cất khóa Google Drive trong Windows Credential Manager.

## Dựng môi trường phát triển

```powershell
uv sync --extra robot          # bỏ --extra robot nếu máy không có SAP GUI
pwsh -ExecutionPolicy Bypass -File scripts\windows\create-databases.ps1 -Environment dev -WriteEnvFile
uv run shoponline migrate
uv run shoponline create-user admin --role admin
uv run shoponline web
```

`create-databases.ps1` hỏi mật khẩu superuser `postgres` và đặt mật khẩu cho role `shoponline_app`. Với `-WriteEnvFile` nó ghi file `.env` ở gốc repo (không ghi đè file đã có). Script dùng PowerShell 7 (`pwsh`) vì có chữ tiếng Việt.

## Cấu hình

Đọc từ biến môi trường; nếu có file `.env` ở thư mục đang chạy thì nạp các biến chưa đặt. Danh sách biến: [.env.example](.env.example).

| Biến | Ý nghĩa |
|---|---|
| `SHOPONLINE_DATABASE_URL` | Chuỗi kết nối `postgresql+psycopg://…` |
| `SHOPONLINE_TEST_DATABASE_URL` | Database cho pytest; tên phải kết thúc bằng `_test` |
| `SHOPONLINE_SECRET_KEY` | Khóa ký phiên đăng nhập, ít nhất 32 ký tự |
| `SHOPONLINE_DATA_DIR` | Thư mục ngoài repo chứa file tải lên và file xuất ra |
| `SHOPONLINE_WEB_HOST`, `SHOPONLINE_WEB_PORT` | Địa chỉ và cổng web (mặc định `127.0.0.1:8750`) |
| `SHOPONLINE_BACKUP_PASSWORD` | Mật khẩu mã hóa bản sao lưu (7-Zip AES-256) |
| `SHOPONLINE_BACKUP_DIRS` | Các thư mục nhận bản sao lưu, cách nhau bằng `;` |
| `SHOPONLINE_BACKUP_KEEP_DAYS` | Không còn tác dụng. Giờ sao lưu và số bản giữ đặt ở trang **Sao lưu** trên web |
| `SHOPONLINE_RESTORE_DATABASE_URL` | Database tạm dùng cho diễn tập khôi phục (không bao giờ là database đang chạy) |
| `SHOPONLINE_SAP_SYSTEM`, `SHOPONLINE_SAP_CLIENT` | Hệ thống SAP robot làm việc; để trống thì không xếp việc cho robot |
| `SHOPONLINE_SAP_CONNECTION`, `SHOPONLINE_SAP_USER`, `SHOPONLINE_SAP_PASSWORD`, `SHOPONLINE_SAP_LANGUAGE` | Đăng nhập lại SAP trên máy robot |
| `SHOPONLINE_ROBOT_MAX_FAILURES`, `SHOPONLINE_ROBOT_EVIDENCE_KEEP_DAYS` | Ngưỡng lỗi liên tiếp để robot tự dừng (3); số ngày giữ ảnh lỗi (30) |
| `SHOPONLINE_RETENTION_DAYS` | Số ngày giữ file `zrsd004` tải tay chờ gắn vào đợt (90). Tên, địa chỉ khách được giữ vĩnh viễn |
| `SHOPONLINE_INVOICE_SYMBOL_PATTERN` | Mẫu ký hiệu hóa đơn trên biên bản trả hàng, `{yy}` là hai số cuối năm hóa đơn (`1C{yy}TAL`) |

Bí mật (mật khẩu database, khóa phiên, mật khẩu sao lưu) nằm trong kho bí mật của chủ dự án, không nằm trong repo.

## Lệnh

| Lệnh | Việc |
|---|---|
| `uv run shoponline migrate` | Nâng schema lên bản mới nhất |
| `uv run shoponline create-user <tên> --role admin\|viewer` | Tạo hoặc đặt lại mật khẩu người dùng web |
| `uv run shoponline web` | Chạy web |
| `uv run shoponline robot` | Chạy robot SAP (máy robot, cần `uv sync --extra robot`) |
| `uv run shoponline robot-pause [--reason …]`, `robot-resume` | Tạm dừng, bật lại robot |
| `uv run shoponline retention [--apply]` | Xóa file hết dùng (`--apply` không còn tác dụng; dữ liệu khách được giữ) |
| `uv run shoponline history-import <file.xlsx> [--apply]` | Nạp file `Shop Online 2022-2026` của kế toán để làm báo cáo (mặc định chạy thử; `--apply` đòi bản sao lưu `db` trong 2 giờ, máy phát triển dùng `--skip-backup-check`) |
| `uv run pytest` | Chạy test (test cần database bị bỏ qua khi thiếu `SHOPONLINE_TEST_DATABASE_URL`) |
| `uv run ruff check` | Kiểm tra mã |
| `uv run shoponline backup run --kind db\|app\|full [--no-drive]` | Sao lưu mã hóa ra các thư mục trong `SHOPONLINE_BACKUP_DIRS` và lên Google Drive (mã thoát 0 đủ nơi, 2 một phần, 1 không nơi nào, 3 không lấy được khóa) |
| `uv run shoponline backup run --if-due` | Việc của tác vụ `shoponline-backup` (15 phút một lần): xử lý yêu cầu từ web rồi chạy bản tới lịch |
| `uv run shoponline backup verify <#id\|tên file>` | Kiểm tra mã hóa, `7z t` và SHA-256 |
| `uv run shoponline backup restore <bản> --drill\|--production [--force]` | Diễn tập vào `SHOPONLINE_RESTORE_DATABASE_URL`, hoặc phục hồi hệ thống thật (có bản an toàn và tự lùi lại) |
| `uv run shoponline backup restore <gói> --new-machine`, `backup fetch-latest --kind full --to <thư mục>` | Nạp gói chuyển máy vào máy mới; tải bản mới nhất từ Google Drive |
| `uv run shoponline drive set-client\|connect\|status\|disconnect` | Kết nối Google Drive bằng mã thiết bị (cùng việc với khối **Kết nối Google Drive** trên web) |
| `pwsh -File scripts\windows\backup-db.ps1` | Sao lưu `db` trước deploy (vỏ gọi lệnh trên; `update-production.ps1` dùng nó) |
| `pwsh -File scripts\windows\server-export.ps1 [-Prepare\|-Rollback]` | Chuyển máy chạy thật: xuất gói và nhả máy cũ; xem [deployment-guide.md](docs/deployment-guide.md#chuyển-máy-chạy-thật-sang-máy-khác) |
| `pwsh -File scripts\windows\restore-db.ps1 -Archive <file.7z>` | Khôi phục vào `SHOPONLINE_RESTORE_DATABASE_URL` |
| `pwsh -File scripts\windows\register-tasks.ps1 -User <tài khoản> [-RetentionApply]` | Đăng ký web, sao lưu (mỗi 15 phút), phục hồi (chạy khi web gọi) và dọn file hết dùng trong Task Scheduler (máy chạy thật) |
| `pwsh -File scripts\windows\register-tasks.ps1 -RobotUser <tài khoản>` | Đăng ký robot chạy khi tài khoản robot đăng nhập |
| `uv run python tests/fixtures/build_fixtures.py <thư mục>` | Sinh bộ file mẫu tự dựng để thử web |

## Trả hàng sau hóa đơn

Admin lập phiếu trả hàng từ trang đơn đã giao có hóa đơn: hệ thống cấp số biên bản và sinh Biên bản điều chỉnh hóa đơn (.docx) cùng REQUEST to RETURN GOODS (.xlsx) từ mẫu. Mô-đun `src/shoponline/returns/`; lệnh `shoponline return-number start|show|repair` quản lý số; cấu hình `SHOPONLINE_INVOICE_SYMBOL_PATTERN`. Xem `docs/system-architecture.md` và `docs/daily-operations.md`.

## Cấu trúc

```
src/shoponline/
  config.py  cli.py
  db/          engine, session, models
  domain/      đơn chung, trạng thái, ánh xạ, ngày goods issue, giá trị SO
  importers/   file Shopee, TikTok, Lazada, zrsd001, zrsd004, bảng ánh xạ
  exports/     file ĐƠN HÀNG ONLINE, file gửi kế toán (một hoặc nhiều nguồn zrsd004)
  accounting/  sổ DO đã gửi kế toán, đợt xuất, đối chiếu và chốt
  reconcile/   nối số SO, báo cáo lệch, nhập file báo cáo SAP (dùng chung cho tải lên và robot)
  sapjobs/     hàng đợi việc SAP trong PostgreSQL, công tắc dừng robot
  saprobot/    robot SAP GUI Scripting: lớp chặn T-code, phiên, thanh trạng thái, popup, ảnh lỗi, vòng lặp
  maintenance/ dọn file hết dùng
  backup/      sao lưu mã hóa, lịch, xoay vòng, Google Drive, khôi phục, chuyển máy
  web/         FastAPI + Jinja2
config/        ID phần tử màn hình SAP và danh sách popup đã biết (từ bản ghi recorder)
migrations/    Alembic
scripts/windows/  tạo database, sao lưu, Task Scheduler
tests/         dữ liệu test tự dựng trong tests/fixtures
```

Kiến trúc: [docs/system-architecture.md](docs/system-architecture.md). Bảo mật và thời hạn lưu: [docs/security-and-data-retention.md](docs/security-and-data-retention.md).

Vận hành và triển khai: [docs/deployment-guide.md](docs/deployment-guide.md), [docs/daily-operations.md](docs/daily-operations.md), [docs/operations-runbook.md](docs/operations-runbook.md) (xử lý sự cố), [docs/robot-machine-setup.md](docs/robot-machine-setup.md), [docs/robot-runbook.md](docs/robot-runbook.md).
