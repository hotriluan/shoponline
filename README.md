# shoponline

Hệ thống nội bộ xử lý đơn sàn TMĐT (Shopee, TikTok) cho bộ phận shop online:

1. Admin tải file "chờ giao hàng" của sàn lên web.
2. Hệ thống ánh xạ sản phẩm sang mã SAP và sinh file `ĐƠN HÀNG ONLINE <SÀN> ddmmyy.xlsx` cho sales admin.
3. Sales admin tạo SO và DO trong SAP (chế độ thủ công), rồi admin xác nhận lô.
4. Admin tải `zrsd001` lên: hệ thống lưu cặp mã đơn ↔ số SO và báo các điểm lệch.
5. Admin tải `zrsd004` lên: hệ thống chèn mã đơn, tên khách, địa chỉ và xuất `SHOP ONLINE ddmmyy.xlsx` gửi kế toán.

Bước 4 và 5 có thể do robot SAP làm thay (chỉ đọc báo cáo, chưa tạo chứng từ): xem [docs/robot-runbook.md](docs/robot-runbook.md). Ở chế độ thủ công hệ thống không ghi gì vào SAP. Kế hoạch đầy đủ: [plans/261111-0755-shopee-excel-to-sap-order-flow/plan.md](plans/261111-0755-shopee-excel-to-sap-order-flow/plan.md).

## Yêu cầu

- Windows, Python 3.12 trở lên (máy phát triển dùng 3.14), [uv](https://docs.astral.sh/uv/).
- PostgreSQL 16 cài trực tiếp trên Windows, chỉ nghe `localhost`.
- 7-Zip (`C:\Program Files\7-Zip\7z.exe`) cho sao lưu mã hóa.

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
| `SHOPONLINE_BACKUP_KEEP_DAYS` | Số ngày giữ bản sao lưu (mặc định 30) |
| `SHOPONLINE_RESTORE_DATABASE_URL` | Database dùng cho diễn tập khôi phục |
| `SHOPONLINE_SAP_SYSTEM`, `SHOPONLINE_SAP_CLIENT` | Hệ thống SAP robot làm việc; để trống thì không xếp việc cho robot |
| `SHOPONLINE_SAP_CONNECTION`, `SHOPONLINE_SAP_USER`, `SHOPONLINE_SAP_PASSWORD`, `SHOPONLINE_SAP_LANGUAGE` | Đăng nhập lại SAP trên máy robot |
| `SHOPONLINE_ROBOT_MAX_FAILURES`, `SHOPONLINE_ROBOT_EVIDENCE_KEEP_DAYS` | Ngưỡng lỗi liên tiếp để robot tự dừng (3); số ngày giữ ảnh lỗi (30) |

Bí mật (mật khẩu database, khóa phiên, mật khẩu sao lưu) nằm trong kho bí mật của chủ dự án, không nằm trong repo.

## Lệnh

| Lệnh | Việc |
|---|---|
| `uv run shoponline migrate` | Nâng schema lên bản mới nhất |
| `uv run shoponline create-user <tên> --role admin\|viewer` | Tạo hoặc đặt lại mật khẩu người dùng web |
| `uv run shoponline web` | Chạy web |
| `uv run shoponline robot` | Chạy robot SAP (máy robot, cần `uv sync --extra robot`) |
| `uv run shoponline robot-pause [--reason …]`, `robot-resume` | Tạm dừng, bật lại robot |
| `uv run pytest` | Chạy test (test cần database bị bỏ qua khi thiếu `SHOPONLINE_TEST_DATABASE_URL`) |
| `uv run ruff check` | Kiểm tra mã |
| `pwsh -File scripts\windows\backup-db.ps1` | Sao lưu mã hóa ra các thư mục trong `SHOPONLINE_BACKUP_DIRS` |
| `pwsh -File scripts\windows\restore-db.ps1 -Archive <file.7z>` | Khôi phục vào `SHOPONLINE_RESTORE_DATABASE_URL` |
| `pwsh -File scripts\windows\register-tasks.ps1 -User <tài khoản>` | Đăng ký web và sao lưu trong Task Scheduler (máy chạy thật) |
| `pwsh -File scripts\windows\register-tasks.ps1 -RobotUser <tài khoản>` | Đăng ký robot chạy khi tài khoản robot đăng nhập |
| `uv run python tests/fixtures/build_fixtures.py <thư mục>` | Sinh bộ file mẫu tự dựng để thử web |

## Cấu trúc

```
src/shoponline/
  config.py  cli.py
  db/          engine, session, models
  domain/      đơn chung, trạng thái, ánh xạ, ngày goods issue, giá trị SO
  importers/   file Shopee, TikTok, zrsd001, zrsd004, bảng ánh xạ
  exports/     file ĐƠN HÀNG ONLINE, file gửi kế toán
  reconcile/   nối số SO, báo cáo lệch, nhập file báo cáo SAP (dùng chung cho tải lên và robot)
  sapjobs/     hàng đợi việc SAP trong PostgreSQL, công tắc dừng robot
  saprobot/    robot SAP GUI Scripting: phiên, thanh trạng thái, popup, ảnh lỗi, vòng lặp
  web/         FastAPI + Jinja2
config/        ID phần tử màn hình SAP và danh sách popup đã biết (từ bản ghi recorder)
migrations/    Alembic
scripts/windows/  tạo database, sao lưu, Task Scheduler
tests/         dữ liệu test tự dựng trong tests/fixtures
```

Vận hành và triển khai: [docs/deployment-guide.md](docs/deployment-guide.md), [docs/daily-operations.md](docs/daily-operations.md), [docs/robot-machine-setup.md](docs/robot-machine-setup.md), [docs/robot-runbook.md](docs/robot-runbook.md).
