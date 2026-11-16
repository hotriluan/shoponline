# Brainstorm: chuyển máy chạy thật sang máy Windows 10 64-bit, tự deploy qua GitHub

Ngày: 2026-11-16

## Hiện trạng (đã kiểm tra)

- Cơ chế "push `main` → máy chạy thật tự lấy về và deploy" **đã có và đang chạy**:
  [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml) chạy test trên GitHub, rồi giao job
  cho self-hosted runner có nhãn `shoponline-prod`, runner gọi
  [`update-production.ps1`](../../scripts/windows/update-production.ps1) trong `C:\shoponline`
  (dừng robot/web, sao lưu, fast-forward, `uv sync`, `migrate`, đăng ký tác vụ thiếu, bật lại web/robot).
- Máy `Alkana_IT` hiện vừa là máy phát triển (`c:\dev\shoponline`) vừa là máy chạy thật (`C:\shoponline`).
  Runner `ALKANA_IT-shoponline` đang online với nhãn `shoponline-prod`. Năm tác vụ `shoponline-*` đã đăng ký
  theo kiểu `-AtLogOn` cho tài khoản `luanh`.
- Robot SAP chạy trên chính máy này; mật khẩu `AL17016` nằm trong Credential Manager của `luanh`.
- Các script phụ thuộc đường dẫn cố định: `C:\shoponline` (workflow), `C:\Program Files\PostgreSQL\16\bin`,
  `C:\Program Files\7-Zip\7z.exe`. Máy mới cài theo đúng các đường dẫn này thì không phải sửa script.
- Repo đang **PUBLIC**. Workflow không có trigger `pull_request` và repo bắt buộc duyệt workflow từ fork.
- Việc dựng máy hiện làm tay theo [deployment-guide.md](../../docs/deployment-guide.md) mục 1–5b,
  khoảng mười bước rời rạc.

## Contract

**Outcome:** Máy Windows 10 64-bit mới trở thành máy chạy thật duy nhất (web, PostgreSQL, sao lưu, retention,
robot SAP). Mỗi lần máy phát triển push `main`, GitHub chạy test rồi máy mới tự lấy code và deploy, giống hệt
cách `Alkana_IT` đang làm. `Alkana_IT` chỉ còn là máy phát triển.

**Constraints:**
- Giữ nguyên pipeline hiện có (workflow, nhãn `shoponline-prod`, `update-production.ps1`); máy mới chỉ cần
  đúng các đường dẫn chuẩn.
- Tại mỗi thời điểm chỉ một runner mang nhãn `shoponline-prod` và chỉ một robot dùng `AL17016`.
- Bí mật (mật khẩu DB, khóa phiên, mật khẩu sao lưu, mật khẩu SAP) không đi qua GitHub; nhập trên máy mới.
- Dữ liệu chuyển bằng bản sao lưu `.7z` có sẵn và `restore-db.ps1`.
- Robot cần phiên Windows đăng nhập thật, tiếng Anh, không khóa màn hình (theo robot-machine-setup.md).

**Non-goals:** Docker hoặc container; đổi sang cloud; đổi cấu trúc workflow; cụm nhiều máy chạy thật;
tự động hóa phần cài SAP GUI, Excel, bật scripting phía SAP.

**Acceptance criteria:**
1. Một script dựng máy chạy trên máy Win10 trắng (đã có quyền admin) cài đủ phần mềm, lấy mã, tạo DB,
   đăng ký tác vụ và runner, chỉ dừng lại ở những bước bắt buộc nhập tay.
2. Sau khi chuyển: trên GitHub chỉ còn runner của máy mới mang nhãn `shoponline-prod`; `Alkana_IT` không còn
   chạy `shoponline-web`, `shoponline-robot`, `shoponline-deploy-runner`.
3. Push một commit nhỏ lên `main` → job `deploy` chạy xanh trên runner máy mới, web chạy đúng commit đó.
4. `http://<IP máy mới>:8750/login` mở được từ máy admin trong LAN; dữ liệu cũ (đơn, ánh xạ, người dùng) có đủ.
5. Trang **Kết nối SAP** báo robot chạy trên máy mới, mật khẩu "đã có", nút Kiểm tra thành công với `AEP/300`.
6. Tác vụ `shoponline-backup` chạy tay tạo được file `.7z` ở các thư mục đích; diễn tập khôi phục thành công.

## Phương án

**A. Giữ pipeline hiện có + thêm script dựng máy một lần + quy trình chuyển máy (khuyến nghị).**
Thêm `scripts/windows/setup-production-machine.ps1`: cài Git, PowerShell 7, uv, PostgreSQL 16, 7-Zip, gh bằng
`winget`; clone vào `C:\shoponline`; `uv sync --extra robot`; gọi `create-databases.ps1`; tùy chọn khôi phục một
bản `.7z`; `migrate`; `register-tasks.ps1 -AtLogOn`; mở cổng firewall cho LAN; `install-deploy-runner.ps1`.
Script chạy lại được (bỏ qua bước đã xong). Kèm quy trình cắt chuyển: tắt runner, robot, web cũ → sao lưu cuối →
khôi phục trên máy mới → gỡ runner cũ khỏi repo → push thử.
- Giả định chính: `winget` có trên máy Win10 (App Installer, Win10 1809 trở lên) và máy ra được Internet tới
  GitHub, winget, PyPI.
- Hỏng trước tiên khi: máy bị chính sách công ty chặn winget/Internet. Khi đó script vẫn dùng được nếu cài tay
  phần mềm trước (script chỉ kiểm tra là đã có).

**B. Không dùng runner: tác vụ Task Scheduler cứ 5 phút `git fetch`, thấy commit mới thì deploy.**
- Giả định chính: chấp nhận deploy cả commit chưa qua test, hoặc phải tự gọi API kiểm trạng thái CI.
- Hỏng trước tiên khi: push một commit làm vỡ test; nó lên máy thật mà không ai thấy trên tab Actions.
  Đây là lùi so với cái đang có, nên loại.

**C. Docker Desktop trên Win10.**
- Giả định chính: robot chạy được trong container. Sai: robot điều khiển SAP GUI và Excel trên desktop thật.
  Loại.

## Trade-offs

- A đổi một lần công viết và thử script (cần một máy Win10 trắng để thử) lấy việc dựng máy chỉ còn một lệnh
  cộng vài bước tay. Nếu chỉ dựng máy đúng một lần, viết script vẫn đáng vì tài liệu "Khi máy hỏng" cần dựng
  lại nhanh.
- Giữ một tài khoản Windows `-AtLogOn` + tự đăng nhập (như `Alkana_IT`) đơn giản nhất và không lưu mật khẩu
  Windows trong Task Scheduler; đổi lại web chỉ chạy khi tài khoản đó đăng nhập. Robot vốn đã cần điều này.

## Better approaches

Không có — hướng được yêu cầu (push → máy chạy thật tự lấy về và deploy) chính là cơ chế đã chạy trên
`Alkana_IT` (runner `ALKANA_IT-shoponline` online, workflow `deploy`). Phần thiếu là dựng máy mới và cắt chuyển
an toàn, không phải cơ chế đồng bộ.

## Rủi ro cần xử lý trong plan

- **Hai runner cùng nhãn:** nếu runner cũ chưa gỡ, GitHub giao job cho máy nào rảnh, có thể deploy nhầm máy cũ.
  Gỡ runner cũ ngay trong bước cắt chuyển.
- **Hai robot cùng user SAP:** khóa robot nằm trong PostgreSQL của từng máy, nên hai máy không chặn nhau. Dừng
  và xóa tác vụ robot trên `Alkana_IT` trước khi bật robot máy mới.
- **Windows 10 hết hỗ trợ (22H2, 14/10/2025):** không còn bản vá bảo mật nếu không mua ESU. Máy chứa dữ liệu
  khách và mật khẩu SAP; cần IT xác nhận chấp nhận rủi ro hoặc có ESU.
- **Repo public + self-hosted runner:** hiện đã chặn bằng việc không có `pull_request` và bắt duyệt fork. Nên
  cân nhắc chuyển repo sang private.
- Bước không tự động được: ngôn ngữ Windows tiếng Anh, SAP GUI + scripting, Excel, Autologon, tắt khóa màn hình,
  `gh auth login`, mật khẩu superuser PostgreSQL, giá trị bí mật trong `.env`, `sap-password set`.

## Quyết định của chủ dự án (2026-11-16)

1. Máy mới chạy cả robot SAP.
2. Chuyển dữ liệu hiện tại sang (sao lưu cuối trên `Alkana_IT` → `restore-db.ps1 -AllowProduction` trên máy mới).
3. Một tài khoản Windows tự đăng nhập, mọi tác vụ `-AtLogOn` như `Alkana_IT`.
4. Windows 10 bản tiếng Anh, **không có ESU**: chủ dự án chấp nhận chạy trên hệ điều hành không còn bản vá.
   Bù lại: máy chỉ mở cổng web cho mạng nội bộ, không duyệt web hay đọc mail trên máy đó.

## Bổ sung: chạy ngầm, không hiện cửa sổ PowerShell

**Hiện tượng:** trên `Alkana_IT`, mỗi lần đăng nhập hoặc deploy hiện ba cửa sổ PowerShell (web, robot, runner).

**Nguyên nhân (đã chứng minh):** mọi tác vụ đã chạy `pwsh -WindowStyle Hidden`. `Alkana_IT` là Windows 11,
chưa chọn terminal mặc định (không có `HKCU:\Console\%%Startup`), nên Windows giao mọi cửa sổ console cho
Windows Terminal 1.24. Windows Terminal bỏ qua `-WindowStyle Hidden`. Thử bằng tác vụ tạm cùng kiểu đăng nhập
Interactive:

| Cách chạy | Python chạy | Cửa sổ mới |
|---|---|---|
| `pwsh -WindowStyle Hidden -Command "& uv run ..."` (cách hiện tại) | có | `WindowsTerminal` |
| `uvw.exe run ...` | có | không |
| `conhost.exe --headless <file .cmd>` | có | không |

Trên Windows 10 không có Windows Terminal làm mặc định, cách hiện tại chỉ chớp cửa sổ rồi ẩn. Nhưng vẫn nên dùng
cùng một cách trên cả hai máy.

**Phương án:**
- **A (khuyến nghị): mọi tác vụ chạy qua `conhost.exe --headless`.** Một kiểu khởi chạy cho cả 6 tác vụ:
  `uv run ... web/robot/retention`, `pwsh -File backup-db.ps1`, `run.cmd` của runner.
  Giả định chính: cờ `--headless` của conhost, không có trong tài liệu chính thức, có trên Windows 10 của máy mới.
  Hỏng trước tiên khi: bản Windows 10 quá cũ không có cờ này. Kiểm tra ngay khi chạy script dựng máy (chạy
  một lệnh thử và dừng nếu không được). Nếu hỏng thì cửa sổ hiện ra lại, hệ thống vẫn chạy.
- **B: `uvw.exe` cho ba tác vụ Python, `conhost --headless` cho backup và runner.** `uvw` có trong tài liệu
  của uv, nhưng đổi lại có hai kiểu khởi chạy.
- Loại: chạy tác vụ "khi không đăng nhập" (phiên 0). Cách này cần lưu mật khẩu Windows, và robot cần màn hình thật.

**Việc kèm theo, bắt buộc để chạy ngầm an toàn:**
- **Log của web:** hiện uvicorn chỉ in ra cửa sổ. Ẩn cửa sổ thì mất log, nên thêm file
  `<SHOPONLINE_DATA_DIR>\logs\web.log` xoay vòng như `robot.log`.
- **Cập nhật tác vụ đã có:** `update-production.ps1` gọi `register-tasks.ps1 -OnlyMissing`, nên tác vụ đã đăng
  ký trên `Alkana_IT` giữ nguyên cách chạy cũ. Cần một trong hai: đăng ký lại tác vụ khi lệnh chạy khác bản
  mong muốn (giữ trigger, tài khoản và tùy chọn như `-RetentionApply`), hoặc ghi rõ lệnh đăng ký lại một lần.
  Khuyến nghị: đăng ký lại khi lệnh khác, để push là tự sửa.
- **Pin (phát hiện thêm):** mọi tác vụ đang có `DisallowStartIfOnBatteries=True` và `StopIfGoingOnBatteries=True`.
  Máy laptop rút sạc thì web và robot bị dừng, cắm lại cũng không tự chạy. Nên thêm `-AllowStartIfOnBatteries
  -DontStopIfGoingOnBatteries` cho các tác vụ.

**Acceptance bổ sung:**
7. Sau deploy và sau khi đăng nhập lại, trên `Alkana_IT` (Win11) và máy mới (Win10) không có cửa sổ nào của
   web, robot, runner, backup; web trả lời `/login`, robot hiện "đang chạy", runner online.
8. Lỗi của web ghi vào `logs\web.log`.
9. Push lên `main` tự chuyển các tác vụ cũ trên `Alkana_IT` sang cách chạy ngầm, không phải đăng ký tay.

## Câu hỏi chưa giải quyết

Không còn câu hỏi mở.
