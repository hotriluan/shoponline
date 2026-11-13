# Dựng máy chạy robot SAP

Dành cho chủ dự án và IT khi chuẩn bị máy cho robot đọc báo cáo SAP (phase 5). Máy web và database làm theo [deployment-guide.md](deployment-guide.md); robot chạy trên cùng máy đó, trong phiên Windows của một tài khoản riêng.

Robot chỉ đọc hai báo cáo `ZRSD001` và `ZRSD004` trên Production `AEP`, client `300`. Dự án không dùng QA.

## Điều kiện trước

- Văn bản chấp thuận của cấp trên và IT cho robot thao tác SAP.
- User SAP `AL17016` trên `AEP`/300, chỉ dành cho robot. Không dùng `BASIS01` hay user của người: mật khẩu user Basis sẽ nằm trên máy robot, và robot sẽ nhận nhầm phiên do người mở nếu cùng user.
- `AL17016` hiện mở được `VA02` (kiểm ngày 2026-11-12), tức là role phía SAP rộng hơn hai báo cáo. Hàng rào phía robot là lớp chặn T-code trong mã ([robot-runbook.md](robot-runbook.md#lớp-chặn-t-code)). Khuyến nghị IT thu role về chỉ `ZRSD001` và `ZRSD004`; đây là lớp bảo đảm thêm, không phải điều kiện.
- Cổng G1 của chế độ thủ công đã đạt (xem [plan](../plans/261111-0755-shopee-excel-to-sap-order-flow/plan.md)).

## 1. Tài khoản Windows của robot

Robot điều khiển SAP GUI nên cần màn hình đăng nhập thật, không chạy nền như `web`.

1. Tạo tài khoản Windows riêng, ví dụ `saprobot`, không có quyền quản trị.
2. Cho tài khoản đọc thư mục mã nguồn, đọc `.env`, và ghi vào thư mục dữ liệu (`SHOPONLINE_DATA_DIR`). Robot ghi file báo cáo, ảnh chụp màn hình và nhật ký vào đó; `web` đọc lại.
3. Bật tự đăng nhập tài khoản này khi máy khởi động (Sysinternals Autologon, mật khẩu được mã hóa trong LSA).
4. Tắt khóa màn hình, trình bảo vệ màn hình và chế độ ngủ của tài khoản; đặt độ phân giải cố định.
5. Không ngắt phiên bằng cách đóng cửa sổ Remote Desktop: phiên bị khóa thì SAP GUI Scripting không chạy. Thoát Remote Desktop bằng `tscon` về console, hoặc dùng màn hình thật hoặc màn hình ảo. Việc này cần thử ở bước chạy thử trên Production (robot chỉ đọc nên an toàn).

## 2. SAP GUI

1. Cài cùng phiên bản SAP GUI với máy ghi recorder.
2. Phía máy khách: SAP GUI Options → Accessibility & Scripting → Scripting: bật scripting, bỏ chọn hai ô "Notify when a script attaches to SAP GUI" và "Notify when a script opens a connection".
3. Phía máy chủ: Basis bật tham số `sapgui/user_scripting` cho `AEP`.
4. Trong SAP Logon tạo một mục trỏ đúng `AEP`. Tên mục này là `SHOPONLINE_SAP_CONNECTION`.
5. Ngôn ngữ đăng nhập cố định, giống lúc ghi recorder. Robot nhận diện cửa sổ theo tiêu đề tiếng Anh ("Save As", "SAP GUI Security", "Select Spreadsheet"), nên ngôn ngữ đăng nhập và ngôn ngữ Windows là tiếng Anh. Định dạng ngày của `AL17016` là `DD.MM.YYYY` (`formats.date` trong `config/sap_screens.yaml`).
6. Cài Microsoft Excel. SAP mở file vừa xuất bằng Excel, rồi robot đóng cửa sổ đó.
7. Không đặt luật SAP GUI Security "Deny" cho thư mục `<SHOPONLINE_DATA_DIR>\robot-work`. Robot tự bấm Allow cho đúng file nó vừa xuất. Có thể thêm luật "Allow" cho thư mục này để SAP không hỏi.
8. Đăng nhập `AL17016` một lần, xuất thử một báo cáo bằng tay ra Excel, chọn "Excel (in Office 2007 XLSX Format)" và tick "Always Use Selected Format". Nếu không tick, robot vẫn trả lời được hộp chọn định dạng.

## 3. Cấu hình

Robot đọc cùng `.env` với `web`. Thêm:

| Biến | Đặt ở | Ý nghĩa |
|---|---|---|
| `SHOPONLINE_SAP_SYSTEM`, `SHOPONLINE_SAP_CLIENT` | `.env` của `web` | Hệ thống và client của việc mới, ở dự án này là `AEP` và `300`. Để trống thì web không xếp việc cho robot. |
| `SHOPONLINE_SAP_CONNECTION` | máy robot | Tên mục SAP Logon dùng khi phải đăng nhập lại |
| `SHOPONLINE_SAP_USER` | máy robot | User SAP của robot: `AL17016` |
| `SHOPONLINE_SAP_PASSWORD` | máy robot, từ kho bí mật | Mật khẩu user robot; không ghi vào database hay nhật ký |
| `SHOPONLINE_SAP_LANGUAGE` | máy robot | Ngôn ngữ đăng nhập, ví dụ `EN` (không bắt buộc) |
| `SHOPONLINE_ROBOT_MAX_FAILURES` | cả hai | Số việc lỗi liên tiếp thì robot tự dừng (mặc định 3) |
| `SHOPONLINE_ROBOT_EVIDENCE_KEEP_DAYS` | cả hai | Số ngày giữ ảnh chụp màn hình lỗi (mặc định 30) |

Thao tác đọc `zrsd001` và `zrsd004` đã được viết từ bản ghi recorder. Đặt `SHOPONLINE_SAP_SYSTEM` khi máy robot đã sẵn sàng và mục Kiểm tra bên dưới đã qua.

Robot so hệ thống, client và user của phiên đang mở với việc trước khi làm (`AEP`, `300`, `AL17016`). Không khớp thì robot từ chối việc và tự tạm dừng.

Danh sách T-code và phím robot được dùng nằm cứng trong mã ([guard.py](../src/shoponline/saprobot/guard.py)), không nằm trong `.env` hay `config/`. Sửa cấu hình không nới được danh sách này.

## 4. Cài và đăng ký

```powershell
cd C:\shoponline
uv sync --extra robot
uv run shoponline migrate
pwsh -ExecutionPolicy Bypass -File scripts\windows\register-tasks.ps1 -RobotUser MAYCHU\saprobot
```

Tác vụ `shoponline-robot` chạy `uv run shoponline robot` khi `saprobot` đăng nhập. Task Scheduler không chạy bản thứ hai. Robot cũng giữ một khóa trong PostgreSQL, nên robot thứ hai (kể cả trên máy khác) thoát ngay với mã 3.

## 5. Kiểm tra

Trước lần chạy đầu tiên trên Production:

1. `uv run pytest tests/saprobot` thoát mã 0. Bộ test này gồm test lớp chặn T-code.
2. Chủ dự án xác nhận danh sách T-code được phép trong `guard.py` khớp bản ghi recorder (mục [Lớp chặn T-code](robot-runbook.md#lớp-chặn-t-code)).

Sau đó:

1. Đăng nhập `saprobot`, mở SAP Logon, đăng nhập `AEP` client `300` bằng `AL17016`.
2. Mở trang **Robot SAP** trên web: thấy hệ thống đích và trạng thái "Đang bật".
3. Nhật ký robot nằm ở `<SHOPONLINE_DATA_DIR>\logs\robot.log`.

Cách vận hành hằng ngày và xử lý sự cố: [robot-runbook.md](robot-runbook.md).
