# Bảo mật và thời hạn lưu dữ liệu

Dành cho người quản trị hệ thống và chủ dự án. Kiến trúc: [system-architecture.md](system-architecture.md).

## Hệ thống giữ những gì

| Dữ liệu | Ở đâu | Nhạy cảm |
|---|---|---|
| Tên, địa chỉ khách theo mã đơn | bảng `customer_info` | Có: dữ liệu cá nhân |
| File sàn, file `zrsd001`/`zrsd004`, file gửi kế toán | `SHOPONLINE_DATA_DIR\uploads`, `exports`, `robot-work` | Có: tên, địa chỉ, tên nhân viên bán hàng |
| Ảnh màn hình SAP khi robot lỗi | `SHOPONLINE_DATA_DIR\robot-evidence` | Có thể có |
| Đơn, dòng hàng, số SO, số DO, ánh xạ SKU | các bảng còn lại | Không có dữ liệu cá nhân |
| Nhật ký sự kiện | bảng `event_log` | Không: mã nguồn cấm ghi tên, địa chỉ vào đây |
| Bản sao lưu database | ổ mạng công ty, Google Drive | Có, mã hóa AES-256 |

## Thời hạn lưu

Chốt ngày 2026-11-13: **90 ngày**, đổi bằng `SHOPONLINE_RETENTION_DAYS`.

Lệnh `shoponline retention` ([retention.py](../src/shoponline/maintenance/retention.py)):

- Xóa dòng `customer_info` không đổi trong 90 ngày, **trừ** khi đơn tương ứng chưa xong (chưa có trong `zrsd004`, tức chưa có file gửi kế toán, và chưa hủy). Dòng nhập tay theo mã đơn không có trong hệ thống thì xóa theo tuổi.
- Xóa file trong `uploads`, `exports`, `robot-work` có thời điểm sửa cũ hơn 90 ngày. Tải lại đúng một file cũ thì thời hạn của file đó tính lại từ đầu.
- Giữ đơn, dòng hàng, số SO, số DO: không phải dữ liệu cá nhân, và cần để nhập lại file cũ không tạo đơn trùng.
- Ghi một dòng `retention_purge` vào `event_log` (chỉ số lượng).

Ảnh màn hình robot có thời hạn riêng, mặc định 30 ngày (đặt ở trang Kết nối SAP); robot tự xóa.

Bản sao lưu giữ 30 ngày (`SHOPONLINE_BACKUP_KEEP_DAYS`), nên dữ liệu đã xóa còn trong bản sao lưu tối đa 30 ngày nữa.

### Bật xóa thật

1. `register-tasks.ps1` đăng ký tác vụ `shoponline-retention` chạy 23:30 hằng ngày ở chế độ **chỉ liệt kê**, ghi vào `<SHOPONLINE_DATA_DIR>\logs\retention.log`.
2. Trong một tuần, người quản trị đọc log: chỉ có đơn đã gửi kế toán hoặc đã hủy, và file quá hạn.
3. Đăng ký lại với `-RetentionApply` (thêm cùng các tham số đã dùng lần đầu, ví dụ `-AtLogOn`):

   ```powershell
   pwsh -ExecutionPolicy Bypass -File scripts\windows\register-tasks.ps1 -User <tài khoản> -RetentionApply
   ```

Chạy tay: `uv run shoponline retention` để xem, `uv run shoponline retention --apply` để xóa. Việc xóa không đảo được; muốn lấy lại thì phải khôi phục bản sao lưu.

## Quyền truy cập

- PostgreSQL chỉ nghe `localhost`. Ứng dụng dùng role `shoponline_app`, không dùng `postgres`.
- Web chỉ mở cho mạng nội bộ (Windows Firewall profile Domain hoặc Private). Người dùng web có vai trò `admin` (thay đổi dữ liệu, bật robot) hoặc `viewer` (chỉ xem).
- `.env` và `SHOPONLINE_DATA_DIR` chỉ cho tài khoản chạy hệ thống, tài khoản robot và quản trị viên.

## User SAP của robot

- `AL17016` trên `AEP`/300, kiểu **Service** (đổi ngày 2026-11-12): mật khẩu không hết hạn, và SAP không báo đăng nhập trùng.
- `AL17016` có quyền sửa SO (`VA02`). Chủ dự án chọn giữ nguyên quyền ngày 2026-11-12. Phía robot, lớp chặn T-code là hàng rào duy nhất ([robot-runbook.md](robot-runbook.md#lớp-chặn-t-code)).
- Vì vậy phải bảo vệ máy robot:
  - Mật khẩu SAP chỉ nằm trong Windows Credential Manager của tài khoản chạy robot (đặt bằng `shoponline sap-password set`). Web và database không giữ và không đọc được nó; web chỉ thấy robot báo "đã có / chưa có". Biến `SHOPONLINE_SAP_PASSWORD` chỉ còn là đường dự phòng và nên bỏ đi. Không đặt mật khẩu trong `.env` dùng chung với web.
  - Các cấu hình còn lại (hệ thống, client, mục SAP Logon, user, ngôn ngữ) nằm trong database và chỉ `admin` sửa được trên web; mỗi lần đổi ghi vào nhật ký sự kiện (ai, trường nào, giá trị cũ và mới).
  - Tài khoản `saprobot` không dùng cho việc khác và không có quyền quản trị Windows.
  - Không ai đăng nhập SAP bằng tay với `AL17016`.
  - Remote Desktop vào máy robot chỉ cho người quản trị.
  - Máy đặt nơi có kiểm soát người ra vào.
- Định kỳ (gợi ý: hằng tháng) xem nhật ký đăng nhập của `AL17016` bằng `RSUSR200` hoặc `SM20`, tìm đăng nhập không đến từ máy robot.
- Đổi mật khẩu khi có người rời vai trò vận hành hoặc nghi lộ mật khẩu. SAP nhớ 5 mật khẩu gần nhất nên không dùng lại được. Sau khi đổi trong SAP, chạy lại `shoponline sap-password set` trên máy robot.

## Bí mật

| Bí mật | Nằm ở |
|---|---|
| Mật khẩu database, khóa phiên web | `.env` của máy chạy thật; kho bí mật của chủ dự án |
| Mật khẩu mã hóa sao lưu | `.env` của máy chạy thật; kho bí mật. Không đặt cạnh bản sao lưu |
| Mật khẩu `AL17016` | Windows Credential Manager của tài khoản chạy robot; kho bí mật |

Repo không chứa bí mật nào. `.gitignore` loại `.env` và `docs/sap-recordings/` (bản ghi recorder có dữ liệu khách thật). Trước khi bàn giao, quét lịch sử git một lần, ví dụ bằng `gitleaks detect`.

## Khi một người rời vai trò vận hành

1. Khóa tài khoản web: `uv run shoponline create-user <tên> --role viewer` rồi đặt một mật khẩu ngẫu nhiên không báo cho ai.
2. Đổi những bí mật họ từng biết theo bảng trên. Đổi mật khẩu sao lưu thì bản sao lưu cũ vẫn mở bằng mật khẩu cũ; giữ mật khẩu cũ trong kho bí mật cho tới khi các bản đó hết hạn.
3. Gỡ quyền Remote Desktop vào máy chạy thật.
