# Bảo mật và thời hạn lưu dữ liệu

Dành cho người quản trị hệ thống và chủ dự án. Kiến trúc: [system-architecture.md](system-architecture.md).

## Hệ thống giữ những gì

| Dữ liệu | Ở đâu | Nhạy cảm |
|---|---|---|
| Tên, địa chỉ khách theo mã đơn | bảng `customer_info` | Có: dữ liệu cá nhân |
| File sàn, file quyết toán Shopee/TikTok, file `zrsd001`/`zrsd003`/`zrsd004`, file gửi kế toán, file dòng Shop Online, tới khi hết dùng | `SHOPONLINE_DATA_DIR\uploads`, `exports`, `robot-work` | Có: tên, địa chỉ, tên nhân viên bán hàng; `zrsd003` có tên và mã số thuế khách doanh nghiệp; file quyết toán Shopee có tên đăng nhập người bán, file TikTok có sheet lịch sử rút tiền với tài khoản ngân hàng đã che |
| Ảnh màn hình SAP khi robot lỗi | `SHOPONLINE_DATA_DIR\robot-evidence` | Có thể có |
| Đơn, dòng hàng, số SO, số DO, số hóa đơn của DO các sàn, ánh xạ SKU, tiền sàn đã trả theo đơn (`platform_settlement`: mã đơn, số tiền, ngày) | các bảng còn lại | Không có dữ liệu cá nhân; `sap_tax_invoice` chỉ giữ dòng có Bill-to là khách SAP của sàn, không giữ tên, mã số thuế hay giá trị tiền |
| Nhật ký sự kiện | bảng `event_log` | Không: mã nguồn cấm ghi tên, địa chỉ vào đây |
| Bản sao lưu: database, thư mục dữ liệu (trừ log) và `.env` (không gồm mật khẩu sao lưu) | thư mục sao lưu trên máy chủ hoặc ổ mạng, Google Drive | Có, mã hóa AES-256 (tên file cũng ẩn). `.env` trong bản `app`/`full` có mật khẩu database và khóa phiên, nên ai có mật khẩu sao lưu có thêm hai thứ đó; rủi ro tăng ít vì mật khẩu sao lưu vốn đã mở được toàn bộ dữ liệu khách |

## Thời hạn lưu

Chốt ngày 2026-11-13: dữ liệu khách giữ **90 ngày**, đổi bằng `SHOPONLINE_RETENTION_DAYS`. Chốt ngày 2026-11-16: file trên máy chủ bị xóa ngay khi hết dùng; file gốc của sàn và `zrsd001` không được giữ làm bằng chứng.

### File

Một bộ quy tắc giữ (`kept_files` trong [retention.py](../src/shoponline/maintenance/retention.py)) dùng cho cả việc xóa ngay lúc file hết dùng lẫn lượt quét hằng đêm. File không có quy tắc nào giữ thì bị xóa.

| Thư mục | Giữ khi |
|---|---|
| `uploads/` | File `zrsd004` của đợt gửi kế toán đang mở (gắn tay hoặc robot đọc). File `zrsd004` upload tay đang chờ gắn vào đợt (danh sách "thêm được" trên trang đợt), tối đa `SHOPONLINE_RETENTION_DAYS` ngày |
| `exports/` | Mọi file kế toán (`generated_file.kind = accounting_file`, kể cả file sinh trước khi có đợt và file của đợt đã hủy hoặc gỡ chốt: bản đã gửi kế toán không bao giờ bị dọn). File Shop Online còn ít nhất một đơn chưa được xác nhận đã dán |
| `robot-work/job-<n>/` | Việc chưa `DONE`, tối đa số ngày giữ ảnh màn hình robot |
| `robot-evidence/` | Tối đa số ngày giữ ảnh màn hình robot (mặc định 30, đặt ở trang Kết nối SAP) |

Xóa ngay, sau khi ghi database:

- File sàn, file quyết toán Shopee/TikTok, bảng ánh xạ SKU, `zrsd001` và `zrsd003`, dù upload tay hay robot đọc: ngay khi nhập xong. File bị từ chối cũng bị xóa, trừ khi file cùng nội dung đã có từ trước.
- `zrsd004`: khi đợt chốt hoặc hủy. Khi hủy, file upload tay của đợt quay lại danh sách chờ gắn nên vẫn được giữ. Nếu gỡ một đợt đã chốt, phải upload lại các file `zrsd004` tay của đợt đó.
- `robot-work/job-<n>`: ngay khi việc nhập xong (`DONE`). Việc lỗi giữ thư mục để xem lại.
- File `ĐƠN HÀNG ONLINE`: ngay sau khi gửi xong cho trình duyệt. Muốn có lại thì bấm tải lần nữa.

Lượt quét hằng đêm dừng và không xóa gì trong hai trường hợp, ghi vào `retention.log`:

- Đang có `maintenance.json` (deploy, phục hồi hoặc chuyển máy): thoát sớm với mã 0, vì khôi phục bản `db` rồi quét sẽ xóa file mới hơn bản đó.
- Có đường dẫn lưu trong database (`import_batch`, `generated_file`) nằm ngoài `SHOPONLINE_DATA_DIR` hiện tại, thường do database khôi phục lên máy có thư mục dữ liệu khác: mã thoát 1. Quy tắc giữ không khớp file nào, nên quét tiếp sẽ xóa mọi file quá 1 giờ. Sửa `SHOPONLINE_DATA_DIR` hoặc đường dẫn trong database rồi chạy lại.

Gỡ xác nhận một file lịch sử Shop Online bị từ chối khi tên khách của đơn nào trong file đã bị xóa theo thời hạn lưu: nếu cho gỡ, đơn đó sẽ bị chặn mãi vì thiếu tên khách.
- File Shop Online: khi mọi đơn trong file đã được xác nhận, kể cả xác nhận qua file khác.

Lệnh `shoponline retention` (tác vụ `shoponline-retention`, 12:30 hằng ngày) **luôn** xóa file theo bảng trên, không cần `--apply`. Nó bỏ qua file mới hơn 1 giờ, vì file có thể được ghi trước khi dòng giữ nó được lưu. File không xóa được (ví dụ còn mở trong SAP hoặc Excel) chỉ được ghi log và để lượt sau. Số file đã xóa được ghi vào `retention.log` và một dòng `retention_files` trong `event_log`.

### Dữ liệu khách

Với `--apply`, lệnh `shoponline retention`:

- Xóa dòng `customer_info` không đổi trong 90 ngày, **trừ** khi đơn chưa hủy và còn cần tên khách: DO của đơn chưa vào sổ gửi kế toán (`accounting_sent_delivery`), hoặc đơn chưa được xác nhận đã dán vào file lịch sử Shop Online (`sales_history_exported`). Vì vậy tên khách của đơn chưa xuất sang file lịch sử được giữ quá 90 ngày, tới khi admin xác nhận. Dòng nhập tay theo mã đơn không có trong hệ thống thì xóa theo tuổi.
- Giữ đơn, dòng hàng, số SO, số DO và sổ DO đã gửi (chỉ chứa số Delivery): không phải dữ liệu cá nhân, và cần để nhập lại file cũ không tạo đơn trùng, không gửi kế toán hai lần.
- Ghi một dòng `retention_purge` vào `event_log` (chỉ số lượng).

Không có `--apply` thì lệnh chỉ liệt kê dữ liệu khách sẽ bị xóa.

### Phiếu trả hàng

Phiếu trả hàng (`sales_return`) giữ bản chụp tên và địa chỉ người mua, và hai file của phiếu, **không giới hạn thời gian**: đây là chứng từ điều chỉnh hóa đơn. Quy tắc 90 ngày không áp dụng cho chúng. Quét file giữ mọi `generated_file` mà một phiếu trỏ tới, theo dữ liệu chứ không theo loại file, nên hoàn tác mã cũng không làm mất phiếu. Chỉ admin xem tên, địa chỉ và tải hai file; viewer chỉ thấy danh sách và số liệu. Bản sao lưu `db` hằng ngày chép hai file này cùng file kế toán.

PDF hóa đơn tải lên không được ứng dụng lưu vào kho file, nhưng máy chủ web có thể tạm đặt upload lớn (hơn 1 MB) vào thư mục tạm của hệ điều hành trước khi route chạy; PDF chỉ nhận từ admin, tối đa 5 MB và 5 trang.

### Bản sao lưu

Xoay vòng ([retention.py](../src/shoponline/backup/retention.py)) áp dụng như nhau cho từng thư mục đích và cho Google Drive, và chỉ nơi nào đã nhận bản mới mới được dọn. Mặc định (đổi trên trang **Sao lưu**):

| Loại | Giữ |
|---|---|
| `db` | 15 bản mới nhất (1 bản mỗi ngày cộng bản trước mỗi deploy: khoảng 1–2 tuần). Ngoài database còn có thư mục `accounting-files/` chứa các file kế toán đã gửi (chỉ có trong thư mục dữ liệu, còn bản `full` thì hằng tuần). Phục hồi một bản `db` chép lại các file này nếu thư mục dữ liệu đang thiếu, không bao giờ ghi đè file đang có |
| `app` | 15 bản mới nhất |
| `full` | Theo tuổi: tối đa 30 ngày (web chỉ cho đặt 7–90 ngày). Bản `full` cuối cùng cũng bị xóa khi quá hạn; web cảnh báo khi 8 ngày không có bản `full` thành công |

Mọi mặc định và mức tối đa đều nằm trong thời hạn 90 ngày, nên dữ liệu khách đã xóa không còn trong bản sao lưu quá 90 ngày. Bản sao lưu trước deploy chỉ ở máy chủ, không lên Drive. Bản thành công mới nhất của mỗi loại và bản an toàn của lần phục hồi gần nhất không xóa tay được. Phục hồi trả `public` (gồm `customer_info` và `event_log`) về thời điểm của bản sao lưu nhưng **không lùi tài khoản web**, lịch sao lưu và kết nối Drive; mọi người phải đăng nhập lại.

Chỉ `admin` được tải về, xóa, tải lên và phục hồi bản sao lưu. Mỗi lần tải về, xóa, tải lên ghi một dòng `event_log` (ai, bản nào, không có nội dung). File tải về vẫn là `.7z` mã hóa nhưng chứa dữ liệu khách rời khỏi máy chủ, nên chỉ tải khi cần.

### Bật xóa thật dữ liệu khách

1. `register-tasks.ps1` đăng ký tác vụ `shoponline-retention` chạy 12:30 hằng ngày; phần dữ liệu khách ở chế độ **chỉ liệt kê**. Kết quả ghi vào `<SHOPONLINE_DATA_DIR>\logs\retention.log` (xoay vòng 10 × 5 MB).
2. Trong một tuần, người quản trị đọc log: chỉ có đơn đã gửi kế toán và đã vào file lịch sử Shop Online, và đơn đã hủy.
3. Đăng ký lại với `-RetentionApply` (thêm cùng các tham số đã dùng lần đầu, ví dụ `-AtLogOn`):

   ```powershell
   pwsh -ExecutionPolicy Bypass -File scripts\windows\register-tasks.ps1 -User <tài khoản> -RetentionApply
   ```

Chạy tay: `uv run shoponline retention` xóa file hết dùng và liệt kê dữ liệu khách sẽ xóa; `uv run shoponline retention --apply` xóa cả dữ liệu khách. Việc xóa không đảo được; muốn lấy lại thì phải khôi phục bản sao lưu.

## Quyền truy cập

- PostgreSQL chỉ nghe `localhost`. Ứng dụng dùng role `shoponline_app`, không dùng `postgres`.
- Web chỉ mở cho mạng nội bộ (Windows Firewall profile Domain hoặc Private). Người dùng web có vai trò `admin` (thay đổi dữ liệu, bật robot) hoặc `viewer` (chỉ xem).
- `.env` và `SHOPONLINE_DATA_DIR` chỉ cho tài khoản chạy hệ thống, tài khoản robot và quản trị viên.
- SSH vào máy chạy thật (OpenSSH Server của Windows) dùng để xem log và tác vụ: chỉ nhận khóa (`PasswordAuthentication no`, `KbdInteractiveAuthentication no`), khóa nằm ở `C:\ProgramData\ssh\administrators_authorized_keys`, cổng 22 chỉ mở cho `192.168.18.0/24` và `192.168.68.0/24`. Khóa riêng trên máy phát triển có passphrase và nạp qua `ssh-agent`.

## Máy chạy thật dùng Windows 10 không có ESU

Từ 2026-11-16 máy chạy thật là Windows 10 không mua Extended Security Updates, nên không còn bản vá bảo mật. Chủ dự án chấp nhận rủi ro này ngày 2026-11-16, với các biện pháp bù:

- Web và SSH chỉ mở cho mạng nội bộ, không mở ra Internet.
- Không dùng máy để duyệt web hay đọc mail.
- Quyền `.env` và thư mục dữ liệu bị giới hạn như mục trên.

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
| Mật khẩu mã hóa sao lưu | `.env` của máy chạy thật; kho bí mật. Không đặt cạnh bản sao lưu, và không bao giờ nằm trong bản sao lưu |
| Client ID và Client Secret của OAuth client Google Drive | Client Secret trong Windows Credential Manager của tài khoản chạy hệ thống; **cả hai phải có trong kho bí mật của chủ dự án** (máy mới nhập lại để thấy các bản cũ). Client ID còn nằm trong database (không bí mật) |
| Refresh token Google Drive | Windows Credential Manager của tài khoản chạy hệ thống. Không nằm trong database, bản sao lưu, log hay trang web; mất máy thì kết nối lại bằng mã thiết bị |

**Bản sao lưu trên Drive phụ thuộc một tài khoản Gmail cá nhân** (Drive, OAuth client trong Google Cloud project của tài khoản đó). Ghi tên người giữ tài khoản vào kho bí mật cùng thủ tục chuyển giao khi người đó rời vai trò: tạo project và OAuth client mới trên tài khoản kế nhiệm, kết nối lại, rồi chạy **Sao lưu ngay** loại Toàn bộ; Drive chỉ thấy file do chính project tạo, nên các bản cũ ở Drive của tài khoản cũ không tự theo sang.
| Mật khẩu `AL17016` | Windows Credential Manager của tài khoản chạy robot; kho bí mật |

Repo không chứa bí mật nào. `.gitignore` loại `.env` và `docs/sap-recordings/` (bản ghi recorder có dữ liệu khách thật). Trước khi bàn giao, quét lịch sử git một lần, ví dụ bằng `gitleaks detect`.

## Khi một người rời vai trò vận hành

1. Khóa tài khoản web: `uv run shoponline create-user <tên> --role viewer` rồi đặt một mật khẩu ngẫu nhiên không báo cho ai.
2. Đổi những bí mật họ từng biết theo bảng trên. Đổi mật khẩu sao lưu thì bản sao lưu cũ vẫn mở bằng mật khẩu cũ; giữ mật khẩu cũ trong kho bí mật cho tới khi các bản đó hết hạn.
3. Gỡ quyền Remote Desktop vào máy chạy thật.
4. Nếu người đó giữ tài khoản Gmail của Drive sao lưu hoặc biết Client Secret: bấm **Ngắt kết nối** ở khối Google Drive (thu hồi quyền phía Google), đổi mật khẩu và Client Secret của tài khoản đó, rồi chuyển giao như đoạn **Bản sao lưu trên Drive** ở mục Bí mật.
