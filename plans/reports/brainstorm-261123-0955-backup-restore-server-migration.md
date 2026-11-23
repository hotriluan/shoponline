# Brainstorm: sao lưu, khôi phục và chuyển máy chạy thật

Ngày 2026-11-23. Đầu vào cho plan `plans/261123-xxxx-backup-restore-server-migration/`.

## Hiện trạng (đã kiểm tra trong repo)

| Đã có | Ở đâu | Giới hạn |
|---|---|---|
| Sao lưu database: `pg_dump -Fc`, mã hóa 7-Zip AES-256 (ẩn tên file), `7z t` kiểm tra | [backup-db.ps1](../../scripts/windows/backup-db.ps1) | Chỉ database; không có thư mục dữ liệu, cấu hình, phiên bản mã |
| Chép tới nhiều thư mục (`SHOPONLINE_BACKUP_DIRS`), gồm thư mục Google Drive for desktop | như trên | Chép vào thư mục Drive ≠ đã lên Drive: app Drive tắt hoặc mất đăng nhập thì vẫn báo thành công |
| Xoay vòng: giữ mọi bản hôm nay + 1 bản/ngày trong `KEEP_DAYS` (14) ngày | [backup-rotation.ps1](../../scripts/windows/backup-rotation.ps1) | Không có giới hạn số bản, không có bản tuần/tháng, cùng một quy tắc cho mọi nơi |
| Lịch: một tác vụ Task Scheduler hằng ngày 23:00 | [register-tasks.ps1](../../scripts/windows/register-tasks.ps1) | Đổi giờ phải đăng ký lại bằng quyền quản trị; không xem được trên web |
| Sao lưu trước mỗi deploy | [update-production.ps1](../../scripts/windows/update-production.ps1) (gọi `backup-db.ps1`, chấp nhận mã thoát 2) | Giữ nguyên hợp đồng này |
| Khôi phục vào database diễn tập, chặn `shoponline` khi thiếu `-AllowProduction` | [restore-db.ps1](../../scripts/windows/restore-db.ps1) | Khôi phục thật phải tự dừng web/robot, tự migrate, tự đối chiếu |
| Cảnh báo trên web khi bản sao lưu cũ hơn 36 giờ | `backup_warning` trong [app.py](../../src/shoponline/web/app.py) | Không biết nơi nào hỏng, không có danh sách bản sao lưu |
| Chuyển máy: script dựng máy nhận `-Archive`, `-DataSource`, `-Prepare`; quy trình 8 bước tay | [setup-production-machine.ps1](../../scripts/windows/setup-production-machine.ps1), [deployment-guide.md](../../docs/deployment-guide.md#chuyển-máy-chạy-thật-sang-máy-khác) | Đếm dòng, gỡ runner, chép dữ liệu, đối chiếu đều làm tay |

Kết luận: không làm lại từ đầu. Nâng phần đã có thành một module có kiểm thử, thêm lớp quản trị trên web, và gói quy trình chuyển máy thành hai lệnh.

## Hợp đồng

**Outcome.** Admin mở trang **Sao lưu** trên web: thấy bản sao lưu gần nhất ở từng nơi (máy chủ, Google Drive), danh sách bản còn giữ, lịch kế tiếp; bấm sao lưu ngay, kiểm tra, diễn tập khôi phục; sửa lịch và số bản giữ lại mà không cần quyền quản trị Windows. Người quản trị chuyển máy chạy thật bằng hai lệnh (máy cũ xuất gói, máy mới nhận gói), hệ thống tự đối chiếu số dòng và chỉ còn đúng một runner, một robot.

**Constraints.**
- Một máy Windows, PostgreSQL 16 chỉ nghe `localhost`, Task Scheduler, không có dịch vụ đám mây ngoài Google Drive.
- Mã hóa AES-256 bằng 7-Zip với mật khẩu từ kho bí mật; mật khẩu không bao giờ nằm cạnh bản sao lưu hay lên Drive.
- Giữ hợp đồng `backup-db.ps1` (mã thoát 0/2, file `last-backup.txt`) vì `update-production.ps1` đang chạy bản trên đĩa.
- Tên file bản cũ `shoponline-<db>-yyyyMMdd-HHmmss.7z` vẫn được liệt kê, khôi phục và xoay vòng.
- Bất biến chuyển máy: không bao giờ có hai runner nhãn `shoponline-prod` hoặc hai robot dùng `AL17016` cùng chạy.
- Dữ liệu khách trong bản sao lưu: thời hạn giữ bản sao lưu phải được ghi vào [security-and-data-retention.md](../../docs/security-and-data-retention.md).

**Non-goals.**
- Sao lưu liên tục / PITR (WAL archiving), bản sao PostgreSQL thứ hai: một máy nội bộ, mất tối đa vài giờ nhập liệu là chấp nhận được và admin có quy trình tay dự phòng.
- Sao lưu `.venv`, PostgreSQL binary, SAP GUI, Excel: dựng lại bằng script.
- Sao lưu mật khẩu SAP trong Windows Credential Manager: vẫn nhập lại từ kho bí mật.
- Kho đám mây khác (S3, OneDrive), thông báo qua email/Zalo.

**Acceptance criteria.**
1. `uv run shoponline backup run --kind db|full` tạo một file `.7z` mã hóa có `manifest.json` (thời điểm, loại, lý do, commit, revision alembic, phiên bản PostgreSQL, số dòng từng bảng, SHA-256 từng phần); file có mặt ở thư mục máy chủ và trên Google Drive, và Drive xác nhận đúng checksum.
2. Bản `full` còn chứa thư mục dữ liệu (trừ `robot-work`), `.env` bỏ dòng `SHOPONLINE_BACKUP_PASSWORD`, và `git bundle` của commit đang chạy.
3. Một nơi đích hỏng thì nơi còn lại vẫn nhận bản sao lưu, lệnh thoát mã 2, web chỉ rõ nơi hỏng; không nơi nào dọn bản cũ khi bản mới chưa tới nơi đó.
4. Xoay vòng theo số lượng, riêng cho máy chủ và Drive: giữ `last` bản mới nhất, `daily`/`weekly`/`monthly` bản đại diện, mọi bản của hôm nay, và không vượt `max_total` (bản mới nhất không bao giờ bị xóa). Có test đơn vị cho bộ chọn.
5. Lịch và số bản giữ lại sửa được trên web (admin); tác vụ `shoponline-backup` chạy mỗi 15 phút với `--if-due` và áp dụng lịch mới không cần đăng ký lại; máy tắt lúc tới giờ thì chạy bù khi bật lại.
6. Trang **Sao lưu**: trạng thái từng nơi, danh sách bản (cả bản chỉ còn trên Drive), sao lưu ngay, kiểm tra, diễn tập khôi phục vào `SHOPONLINE_RESTORE_DATABASE_URL` và so số dòng với manifest. Viewer chỉ xem.
7. `uv run shoponline backup restore <bản> --production` dừng robot và web, sao lưu an toàn bản hiện tại, khôi phục database (và thư mục dữ liệu nếu là bản `full`), migrate, so số dòng, bật lại web và robot; lỗi giữa chừng thì in cách lùi lại.
8. Chuyển máy: máy cũ `server-export` tạo gói chuyển máy và trả máy về trạng thái "đã nhả" (runner gỡ khỏi repo, tác vụ Disabled); máy mới `setup-production-machine.ps1 -Bundle <file>` dựng máy, khôi phục, đối chiếu số dòng với manifest, và từ chối bật runner/robot khi GitHub còn runner `shoponline-prod` khác đang online. Có lệnh lùi lại trên máy cũ.
9. `backup-db.ps1` vẫn chạy được từ `update-production.ps1` cũ (wrapper gọi lệnh Python mới); deploy tiếp theo xanh.
10. README, deployment-guide, security-and-data-retention cập nhật đúng lệnh, biến và thời hạn giữ.

## Lựa chọn thiết kế

### A. Cách đưa bản sao lưu lên Google Drive

| | A1. Giữ thư mục Drive for desktop | A2. rclone (khuyến nghị) | A3. Google Drive API viết trong Python |
|---|---|---|---|
| Giả định chịu lực | App Drive luôn chạy và đăng nhập dưới đúng tài khoản | rclone.conf có token hợp lệ, cài qua `winget` như các gói khác | Tự quản OAuth (client, refresh token, upload resumable) |
| Hỏng đầu tiên khi | App bị đăng xuất hoặc tạm dừng: bản sao lưu nằm trong thư mục cục bộ, Drive không có gì, hệ thống vẫn báo xanh | Token bị thu hồi hoặc OAuth client ở chế độ Testing (token hết hạn sau 7 ngày): lỗi rõ ràng, web báo nơi Drive hỏng | Bug trong code tự viết cho upload lớn, retry, quota |
| Xác minh đã lên Drive | Không | `rclone lsjson --hash` so MD5 | Có (md5Checksum) |
| Liệt kê/xóa bản trên Drive cho web | Gián tiếp qua thư mục | Có | Có |
| Chi phí | 0 | Một binary, một lần `rclone config` (đăng nhập trình duyệt) | Thêm `google-api-python-client`/OAuth, nhiều code và test nhất |

Khuyến nghị **A2**: rclone đã giải quyết OAuth refresh, upload chia khúc, retry và checksum; code của ta chỉ gọi `copyto`, `lsjson`, `deletefile`. Dùng scope `drive.file` và OAuth client riêng ở trạng thái "In production" để token không hết hạn sau 7 ngày. A1 vẫn được chấp nhận như một thư mục đích thường cho máy đã cấu hình kiểu cũ, nhưng không được tính là "Google Drive" trong trạng thái.

### B. Nơi đặt logic sao lưu và lịch

| | B1. Module Python `shoponline.backup` + Task Scheduler gọi `--if-due` (khuyến nghị) | B2. Giữ PowerShell, web đọc kết quả | B3. Bộ lập lịch chạy trong tiến trình web |
|---|---|---|---|
| Giả định chịu lực | Task Scheduler chạy tác vụ 15 phút một lần | Logic xoay vòng/manifest/Drive viết được tốt trong PowerShell | Web luôn chạy |
| Hỏng đầu tiên khi | Tác vụ bị Disable: web báo "quá hạn" sau khung giờ đã lên lịch | Web cần liệt kê, sửa lịch, chạy ngay: phải gọi chéo PowerShell, logic nằm hai nơi, không có pytest | Deploy dừng web đúng lúc cần sao lưu trước migrate; web crash thì mất cả lịch |

Khuyến nghị **B1**. Lịch và chính sách giữ nằm trong database (bảng cấu hình, sửa trên web); lịch sử chạy ghi vào một bảng `backup_run` (thời điểm, loại, lý do, kết quả từng nơi, kích thước, checksum) để web hiển thị mà không phải quét thư mục mỗi lần. Khóa chống chạy song song bằng `pg_try_advisory_lock`. `pg_dump`, `7z`, `rclone` vẫn là tiến trình con. `backup-db.ps1` thành wrapper gọi `uv run --no-dev shoponline backup run --kind db --reason deploy` và giữ mã thoát.

"Sao lưu ngay" trên web xếp một yêu cầu vào database và tác vụ 15 phút (hoặc `Start-ScheduledTask` nếu tài khoản web có quyền) thực hiện, để web không chạy `pg_dump` dài trong request.

### C. Khôi phục database chạy thật

| | C1. Chỉ bằng CLI có bảo vệ (khuyến nghị) | C2. Nút trên web kích hoạt tác vụ một lần |
|---|---|---|
| Giả định chịu lực | Việc này hiếm, do người quản trị có quyền vào máy làm | Tác vụ tách rời đủ tin cậy để dừng chính web đã gọi nó |
| Hỏng đầu tiên khi | Người quản trị không vào được máy (đã có SSH/RDP nội bộ) | Lỗi giữa chừng khi web đã tắt: admin chỉ thấy trang không mở được, không thấy lỗi |

Khuyến nghị **C1**; web hiển thị đúng lệnh cần chạy cho bản được chọn. Diễn tập khôi phục (vào database tạm) có trên web.

### D. Chuyển máy

Một hướng duy nhất hợp lý: gói các bước tay hiện có thành hai lệnh, dùng chung module sao lưu.

- **Máy cũ** `pwsh scripts\windows\server-export.ps1 [-Prepare]`:
  - `-Prepare` (máy cũ vẫn chạy): tạo bản `full` loại `migration`, không dừng gì; dùng để dựng trước máy mới.
  - Không có `-Prepare` (ngày chuyển): dừng và Disable runner, robot, web; tạo bản `full` cuối có số dòng; Disable backup, retention; gỡ runner khỏi repo và kiểm tra `gh api .../actions/runners`; ghi trạng thái "đã nhả" vào database; in đường dẫn gói ở máy chủ và trên Drive.
  - `-Rollback`: Enable lại tác vụ, cài lại runner, bật web và robot (chỉ khi máy mới đã nhả).
- **Máy mới** `setup-production-machine.ps1 -Bundle <đường dẫn | drive:latest>`: thay `-Archive`/`-DataSource` (vẫn giữ hai tham số cũ), khôi phục database, thư mục dữ liệu, `.env` (đặt lại `SHOPONLINE_WEB_HOST` theo IP máy mới, hỏi mật khẩu sao lưu), migrate, so số dòng với manifest, kiểm tra không còn runner `shoponline-prod` online, rồi mới cài runner và bật robot. Lần chạy với `-Bundle` của bản `-Prepare` thì dừng trước runner và để robot Disabled như `-Prepare` hiện nay.
- Việc tay còn lại được in trong bảng kiểm tra cuối: Autologon, SAP GUI, `sap-password set`, bấm **Kiểm tra** SAP.

## Trade-offs

- **A2 rclone** phụ thuộc vào việc tạo OAuth client riêng ở trạng thái In production; bỏ qua bước này thì token hết hạn sau 7 ngày và Drive im lặng ngừng nhận (web sẽ báo). Đổi lại không phải viết và bảo trì code OAuth.
- **`.env` trong bản `full`**: tiện chuyển máy (không phải nhập lại mật khẩu database, khóa phiên), nhưng ai có mật khẩu sao lưu sẽ có thêm mật khẩu database và khóa phiên. Rủi ro tăng ít, vì mật khẩu sao lưu vốn đã mở được toàn bộ dữ liệu khách. Mật khẩu sao lưu luôn bị bỏ khỏi bản sao.
- **Lịch trong database + tác vụ 15 phút** thêm một lần khởi động `uv run` mỗi 15 phút (vài giây CPU); đổi lại admin sửa lịch không cần quyền quản trị Windows.
- **Giữ theo số lượng trên Drive lâu hơn máy chủ** (ví dụ 30 ngày + 12 tháng) kéo dài thời gian dữ liệu khách đã xóa còn trong bản sao lưu vượt 90 ngày; cần chốt lại chính sách bảo mật (câu hỏi 2).

## Better approaches

Không thay hướng người dùng yêu cầu; hai điểm điều chỉnh có bằng chứng:
- Đưa bản sao lưu lên Drive qua rclone thay vì thư mục Drive for desktop đang dùng, vì cách hiện tại không phát hiện được khi bản sao lưu chưa thật sự lên Drive (`backup-db.ps1` chỉ `Copy-Item` vào thư mục cục bộ).
- "Sao lưu toàn bộ dự án" = database + thư mục dữ liệu + cấu hình + `git bundle` commit đang chạy, không chép cả cây thư mục `C:\shoponline` (gồm `.venv` hàng trăm MB dựng lại được bằng `uv sync --frozen`).

## Giá trị mặc định đề xuất

| Mục | Mặc định |
|---|---|
| Lịch bản `db` | 12:30 và 23:00 hằng ngày, cộng trước mỗi deploy |
| Lịch bản `full` | Chủ nhật 23:15 |
| Giữ ở máy chủ | mọi bản hôm nay, 7 ngày, 4 tuần; tối đa 30 bản |
| Giữ trên Drive | mọi bản hôm nay, 14 ngày, 8 tuần, 6 tháng; tối đa 60 bản |
| Cảnh báo trên web | nơi nào không có bản thành công sau khung giờ dự kiến + 2 giờ |

## Rủi ro

- Restore `--production` chạy khi admin đang nhập liệu: lệnh kiểm tra phiên web hoạt động trong 5 phút gần nhất và yêu cầu `--force` nếu có.
- Bản `full` lớn dần nếu thư mục dữ liệu phình (hiện nhỏ vì file bị xóa khi hết dùng); manifest ghi kích thước, web hiển thị xu hướng.
- Đổi mật khẩu sao lưu: bản cũ vẫn cần mật khẩu cũ; manifest không lưu mật khẩu nhưng ghi "thế hệ khóa" để biết bản nào cần mật khẩu nào.

## Quyết định của chủ dự án (2026-11-23)

Các quyết định này thay cho phần tương ứng ở trên.

1. **Google Drive: Gmail cá nhân.** Kết nối (qua Drive API, xem mục "Kết nối Google Drive trên web") dùng My Drive của tài khoản đó, OAuth client riêng trong Google Cloud project của tài khoản này, scope `drive.file`, đưa lên trạng thái **In production** (không cần Google xác minh với scope này) để refresh token không hết hạn sau 7 ngày. Thư mục đích `shoponline-backup`. Bản sao lưu phụ thuộc vào một tài khoản cá nhân: ghi vào tài liệu bàn giao và thủ tục khi người đó rời vai trò.
2. **Giữ trên Drive: 15 bản gần nhất.** Chính sách giữ chuyển thành đơn giản theo số lượng, cấu hình được trên web cho từng nơi (`keep_count`): Drive mặc định 15, máy chủ mặc định 15, đếm riêng theo từng loại (xem mục "Sao lưu ngay"). Bỏ phần daily/weekly/monthly và `max_total` ở tiêu chí 4. Với 2 bản `db`/ngày, 15 bản ≈ 7 ngày lùi lại, nằm trong thời hạn 90 ngày.
3. **`.env` vào bản `full`: có**, bỏ dòng `SHOPONLINE_BACKUP_PASSWORD`.
4. **Khôi phục database chạy thật: có cả nút trên web (C2)**, thay cho C1. Thiết kế để bù điểm yếu "lỗi khi web đã tắt":
   - `register-tasks.ps1` đăng ký thêm tác vụ một lần `shoponline-restore` (không có trigger), chạy dưới cùng tài khoản; web gọi nó sau khi ghi yêu cầu (bản nào, ai, lúc nào) vào database.
   - Nút chỉ dành cho admin, yêu cầu nhập lại mật khẩu và gõ tên bản sao lưu để xác nhận.
   - Tác vụ dùng đúng lệnh CLI `backup restore --production`: dừng robot, web; sao lưu an toàn; khôi phục; migrate; đối chiếu số dòng. **Lỗi ở bất kỳ bước nào thì tự khôi phục lại bản sao lưu an toàn** rồi bật web, robot.
   - Kết quả ghi vào `<SHOPONLINE_DATA_DIR>\restore-status.json` và log; web khi khởi động lại hiện một banner thành công hoặc lỗi kèm lý do cho admin. Web không bật lại được thì CLI vẫn dùng được qua SSH/RDP.
   - Tiêu chí 7 thêm: nút web chạy hết luồng trên và banner hiện đúng kết quả, kể cả khi cố ý làm hỏng một bước (test với bản sao lưu hỏng).

## Kết nối Google Drive trên web (bổ sung 2026-11-23 10:02)

Chủ dự án muốn một khối "Kết nối Google Drive" trên trang **Sao lưu**, theo ảnh mẫu: nhập OAuth Client ID và Secret, xác thực bằng mã thiết bị, xem trạng thái, kiểm tra, xem các bản trên Drive, ngắt kết nối.

**Outcome.** Admin kết nối, kiểm tra và ngắt Google Drive hoàn toàn trên web, không cần mở terminal trên máy chủ. Khối hiển thị:
- Huy hiệu trạng thái "Đã kết nối: <email>" (hoặc "Chưa kết nối" hay "Lỗi: <lý do>").
- Nút "Hướng dẫn tạo OAuth Client (4 bước)".
- **Bước A:** Client ID và Client Secret, với nhãn "Đã lưu (được mã hóa)"; ô để trống thì giữ giá trị cũ.
- **Bước B:** tài khoản đang liên kết, thư mục đích kèm ID, và các nút **Kết nối (lại) bằng mã thiết bị**, **Kiểm tra kết nối**, **Xem các bản trên Drive**, **Ngắt kết nối**.

**Thay đổi so với quyết định A2.** Bỏ rclone, chọn **A3: gọi Google Drive API trực tiếp từ Python.**
- Lý do: muốn kết nối được từ web thì ứng dụng phải tự giữ token, tự chạy device flow và tự hiển thị email. Với rclone thì phải sinh `rclone.conf` từ token của mình, tức là quản token ở hai nơi.
- Phần code cần viết nhỏ vì bản sao lưu chỉ vài MB. Cần năm lệnh gọi:
  1. Device flow: `oauth2.googleapis.com/device/code` và `/token` (`grant_type=urn:ietf:params:oauth:grant-type:device_code`).
  2. Làm mới token.
  3. Tải file lên bằng `files.create` (upload resumable), kiểm tra `md5Checksum`.
  4. Liệt kê (`files.list` theo thư mục) và xóa (`files.delete`).
  5. Lấy email bằng `about.get(fields=user(emailAddress))`, không cần thêm scope.
- HTTP client là `httpx`, chuyển từ nhóm dev lên dependency chính (đã có trong `uv.lock`). Phần lựa chọn A ở trên đã bị thay bởi mục này.

**Ràng buộc.**
- Scope chỉ là `https://www.googleapis.com/auth/drive.file`, nằm trong danh sách scope Google cho phép với device flow. Ứng dụng chỉ thấy file và thư mục do chính nó tạo.
- Loại OAuth client phải là **TVs and Limited Input devices**. Consent screen loại External, đã **Publish to production**; nếu để Testing thì refresh token hết hạn sau 7 ngày.
- Client Secret và refresh token nằm trong Windows Credential Manager của tài khoản chạy hệ thống, theo cùng cách đang cất mật khẩu SAP ([credentials.py](../../src/shoponline/saprobot/credentials.py), DPAPI). Hệ quả:
  - Chúng không nằm trong database, nên không theo bản sao lưu lên Drive.
  - Chúng không bao giờ được trả về trình duyệt; ô nhập chỉ hiện "Đã lưu".
  - Client ID, ID thư mục đích, email và thời điểm kiểm tra gần nhất nằm trong database. Đây là dữ liệu không bí mật.
- Chỉ admin thấy nút; viewer chỉ thấy trạng thái.
- Tác vụ sao lưu chạy cùng tài khoản Windows với web, nên đọc được cùng credential.

**Luồng.**
1. **Lưu Client ID và Secret.** Đổi client thì xóa refresh token cũ và trạng thái chuyển về "Chưa kết nối", vì `drive.file` gắn với project: client ở project khác không thấy các bản đã tải lên.
2. **Kết nối bằng mã thiết bị.**
   - Server xin `device_code`, rồi hiển thị `user_code` và link `https://www.google.com/device`, kèm đồng hồ hết hạn.
   - Trình duyệt gọi một endpoint của web theo chu kỳ `interval` Google trả về; endpoint này hỏi Google token.
   - Khi nhận được token: cất refresh token; tạo thư mục `shoponline-backup` hoặc dùng lại thư mục đã lưu ID nếu ứng dụng còn thấy nó; lấy email.
   - Xử lý các trường hợp `authorization_pending`, `slow_down`, `access_denied` và `expired_token`.
   - Trạng thái chờ (device_code, hạn) nằm trong database, nên tải lại trang không mất phiên. Mỗi lúc chỉ có một phiên chờ.
3. **Kiểm tra kết nối.** Làm mới token, gọi `about.get`, đọc thư mục đích, và ghi kết quả kèm thời điểm.
4. **Xem các bản trên Drive.** Liệt kê tên, kích thước, thời điểm và trạng thái khớp với bản ở máy chủ. Dùng chung danh sách với bảng bản sao lưu.
5. **Ngắt kết nối.**
   - Yêu cầu xác nhận, gọi `oauth2.googleapis.com/revoke`, rồi xóa refresh token.
   - Các file trên Drive vẫn còn. Lần sao lưu sau ghi nơi Drive là "chưa kết nối" và web cảnh báo.
6. **Hướng dẫn 4 bước** (hộp mở ra, có link):
   1. Tạo project ở Google Cloud Console.
   2. Bật Google Drive API.
   3. Tạo OAuth consent screen loại External, thêm scope `drive.file`, rồi bấm Publish to production.
   4. Tạo Credentials → OAuth client ID → loại **TVs and Limited Input devices**, rồi chép Client ID và Secret.

**Chuyển máy.** Credential Manager không đi theo bản sao lưu. Trên máy mới, admin mở trang Sao lưu, nhập lại **cùng** Client ID và Secret (từ kho bí mật), rồi kết nối lại bằng mã thiết bị. Cùng project thì thấy lại mọi bản cũ.
- Vì vậy `setup-production-machine.ps1 -Bundle drive:latest` cần một lệnh CLI tương đương: `uv run shoponline drive connect`, in mã thiết bị ra terminal và dùng chung module.
- Client ID và Secret phải được ghi vào kho bí mật của chủ dự án. Plan phải thêm dòng này vào bảng bí mật trong security-and-data-retention.

**Acceptance criteria bổ sung.**
11. Trên web, admin lưu Client ID và Secret, kết nối bằng mã thiết bị và thấy "Đã kết nối: <email>". Thư mục `shoponline-backup` được tạo đúng một lần, kể cả khi kết nối lại.
12. Không response, log hay bản sao lưu nào chứa Client Secret, access token hoặc refresh token. Có test kiểm tra template và log.
13. "Kiểm tra kết nối" báo đúng ba trường hợp, kiểm bằng test có giả lập phản hồi Google: hoạt động, token bị thu hồi (`invalid_grant`), thư mục bị xóa.
14. "Ngắt kết nối" thu hồi token phía Google. Sau đó sao lưu không lên Drive và web cảnh báo.
15. `shoponline drive connect` trên CLI cho cùng kết quả như nút web.

## Khối "Sao lưu ngay" (bổ sung 2026-11-23)

Chủ dự án đề xuất khối hành động nhanh gồm ba thẻ (Database, Website, Toàn bộ) và ô "Lưu thêm 1 bản lên Google Drive". Giữ bố cục, điều chỉnh nội dung theo dự án này:

| Thẻ | Loại (`kind`) | Nội dung bản sao lưu |
|---|---|---|
| **Sao lưu Database** | `db` | `pg_dump -Fc` database `shoponline`: đơn, dòng hàng, ánh xạ SAP, số SO/DO/hóa đơn, sổ gửi kế toán, tiền về, người dùng web, cấu hình SAP, nhật ký sự kiện |
| **Sao lưu Ứng dụng** (thay "Website") | `app` | `git bundle` của commit đang chạy, `.env` (trừ `SHOPONLINE_BACKUP_PASSWORD`), `config/*.yaml`, thư mục dữ liệu trừ `robot-work`. Không gồm `.venv`, `__pycache__`, `.pytest_cache`, `.ruff_cache` (dựng lại bằng `uv sync --frozen`) |
| **Sao lưu Toàn bộ** | `full` | `db` + `app` trong một file; là gói chuyển máy |

**Quyết định kèm theo.**
- **Định dạng file.** Giữ `.7z` mã hóa AES-256 (ẩn tên file), không đặt đuôi riêng kiểu `.cscc-backup`: lúc sự cố vẫn mở được bằng 7-Zip mà không cần ứng dụng. Tên file `shoponline-<kind>-<db>-yyyyMMdd-HHmmss.7z`. File cũ `shoponline-<db>-…7z` được hiểu là `kind=db`. Mỗi file có `manifest.json` (loại, lý do, commit, revision alembic, phiên bản PostgreSQL, số dòng từng bảng, SHA-256 từng phần). Ngoài ra có SHA-256 của cả file `.7z` ghi trong `backup_run`, dùng cho nút **Kiểm tra**.
- **"Sao lưu ngay" chạy ngay, không chờ chu kỳ 15 phút.** Web ghi yêu cầu (loại, có lên Drive không, ai bấm) vào database, rồi gọi `Start-ScheduledTask shoponline-backup`. Web và tác vụ cùng tài khoản, nên không cần quyền quản trị. Tác vụ xử lý yêu cầu đang chờ trước, rồi mới xét lịch. Bảng bản sao lưu hiện một dòng "Đang chạy" và tự cập nhật thành "Xong" hoặc "Lỗi". Khóa `pg_try_advisory_lock` làm bấm hai lần hay trùng giờ lịch không chạy chồng. Đang có bản chạy thì cả ba nút bị khóa.
- **Ô "Lưu thêm 1 bản lên Google Drive".** Chỉ áp dụng cho lần bấm tay. Mặc định đánh dấu khi Drive đã kết nối; bị khóa kèm dòng "Chưa kết nối Google Drive" khi chưa kết nối. Bản theo lịch lên Drive theo cài đặt của lịch.
- **Lịch** (chủ dự án chốt 2026-11-23): `db` **1 lần mỗi ngày**, mặc định 23:00, cộng thêm một bản trước mỗi deploy. `full` hằng tuần, mặc định Chủ nhật 23:15. `app` chỉ chạy tay, vì `full` đã chứa nó. Giờ chạy sửa được trên web. Mục "Lịch bản `db`" trong bảng "Giá trị mặc định đề xuất" ở trên được thay bằng dòng này.
- **Số bản giữ lại tính riêng theo từng loại**, 15 bản gần nhất mỗi loại, cho mỗi nơi lưu. Đây là cách hiểu cụ thể của quyết định "giữ 15 bản". Nếu đếm chung, vài lần deploy trong một ngày (mỗi lần một bản `db`) sẽ đẩy mất bản `full` và `app`. Quy tắc "bản `full` mới nhất không bao giờ bị xóa" vì vậy không cần nữa.
- Sao lưu không dừng web. `pg_dump` cho ảnh chụp nhất quán của database. Thư mục dữ liệu được chép khi web vẫn chạy, nên có thể lệch vài giây với database; manifest ghi rõ điều này. Bản `full` cuối lúc chuyển máy chạy sau khi đã dừng web và robot, nên không lệch.

**Acceptance criteria bổ sung.**
16. Bấm từng nút tạo đúng loại file với đúng nội dung theo bảng trên. Có test đọc lại manifest và danh sách file trong gói. `.env` trong gói không có dòng mật khẩu sao lưu.
17. Từ lúc bấm tới lúc dòng "Đang chạy" xuất hiện dưới 5 giây. Bấm lần hai khi đang chạy thì không tạo bản thứ hai.
18. Ô Drive bỏ chọn thì bản không lên Drive. Ô bị khóa khi Drive chưa kết nối.

## Danh sách bản sao lưu và nhật ký (bổ sung 2026-11-23)

Chủ dự án muốn bảng "Danh sách bản sao lưu & nhật ký thực hiện" theo ảnh mẫu: các cột phạm vi/tên file (kèm số bảng, số bản ghi), nguồn tạo, thời gian, dung lượng, người thực hiện, trạng thái cục bộ, trạng thái Google Drive (có nút Thử lại); các thao tác Tải về, Phục hồi, Xóa; nút "Tải lên bản sao lưu". Giữ nội dung đó, điều chỉnh như sau.

**Nguồn dữ liệu của bảng.** Mỗi dòng là một bản ghi `backup_run`, kể cả lần chạy lỗi, nên bảng vừa là danh sách vừa là nhật ký. Mỗi lần mở trang, hệ thống đối chiếu với thư mục máy chủ và với danh sách trên Drive (lưu tạm vài phút), để biết bản nào đã bị xoay vòng xóa hoặc chỉ còn trên Drive. File `.7z` có trên Drive mà chưa có trong database (ví dụ trên máy mới) được thêm thành dòng có nguồn "Tìm thấy trên Drive"; manifest của nó được đọc khi cần.

**Cột.**

| Cột | Nội dung |
|---|---|
| Phạm vi / tên file | Database / Ứng dụng / Toàn bộ; tên `.7z`; "DB: N bảng • M bản ghi" và revision alembic, lấy từ manifest |
| Nguồn | Theo lịch · Bấm tay · Trước deploy (kèm commit rút gọn) · An toàn trước phục hồi · Chuyển máy · Tải lên · Tìm thấy trên Drive |
| Thời gian | `dd/mm/yyyy HH:MM:SS` giờ Asia/Saigon, kèm thời lượng chạy |
| Dung lượng | Kích thước file `.7z` |
| Người thực hiện | Tên người dùng web, hoặc `system` |
| Máy chủ | Đang chạy · Thành công · Lỗi (lý do) · Đã xóa theo số bản giữ · Không có (chỉ trên Drive) |
| Google Drive | Đã lên Drive (MD5 khớp) · Đang tải lên · Lỗi Drive kèm nút **Thử lại** · Không yêu cầu · Chưa kết nối · Đã xóa theo số bản giữ |

**Điều chỉnh so với ảnh mẫu.**
1. **Bảng gọn hơn.** Chín cột cùng ba nút làm chữ trong nút bị xuống dòng. Gộp "Nguồn", "Thời gian" và "Người thực hiện" thành một ô hai dòng. **Tải về** và **Xóa** thành nút biểu tượng có nhãn khi rê chuột.
2. **Phục hồi không phải nút cam nổi bật trên mọi dòng.** Đây là thao tác nguy hiểm nhất của hệ thống. Thay bằng nút **Phục hồi…** viền mở một hộp thoại có hai lựa chọn:
   - **Diễn tập:** khôi phục vào database tạm và so số dòng với manifest. Đây là lựa chọn mặc định.
   - **Phục hồi hệ thống thật:** luồng C2 (nhập lại mật khẩu, gõ tên bản, sao lưu an toàn, tự lùi lại khi lỗi).

   Hộp thoại ghi rõ phục hồi sẽ thay những gì:
   - Bản `db`: database.
   - Bản `full`: database và thư mục dữ liệu.
   - Bản `app` không có nút phục hồi trên web, chỉ dùng khi chuyển máy. Mã nguồn luôn do deploy quản lý, không bao giờ bị ghi đè từ bản sao lưu trên máy đang chạy.
3. **Chặn phục hồi sai phiên bản.** Bản có revision alembic mới hơn mã đang chạy thì bị từ chối, vì mã cũ không đọc được schema mới. Bản cũ hơn thì phục hồi rồi `migrate`.
4. **Bản chỉ còn trên Drive vẫn tải về và phục hồi được.** Hệ thống tải nó về máy chủ trước và kiểm tra MD5.
5. **Thêm thao tác Kiểm tra** (trong menu "…"): `7z t` và so SHA-256 với `backup_run`.
6. **Xóa:**
   - Hộp thoại cho chọn xóa ở máy chủ, trên Drive, hoặc cả hai.
   - Không cho xóa bản thành công mới nhất của mỗi loại, và không cho xóa bản an toàn của lần phục hồi gần nhất.
   - Dòng nhật ký vẫn giữ, với trạng thái "Đã xóa bởi <người dùng>".
7. **Tải về:**
   - File tải về vẫn là `.7z` mã hóa nên đọc cần mật khẩu, nhưng nó vẫn chứa dữ liệu khách rời khỏi máy chủ. Vì vậy chỉ admin được tải.
   - Mỗi lần tải ghi vào `event_log` (ai, bản nào), không ghi nội dung.
8. **Tải lên bản sao lưu:**
   - Nhận file `.7z` của hệ thống này, không nhận `.cscc-backup`. Giới hạn kích thước 1 GB.
   - Hệ thống kiểm tra mở được bằng mật khẩu sao lưu, đọc manifest và kiểm tra SHA-256 từng phần.
   - File không hợp lệ thì bị từ chối và xóa ngay. File hợp lệ được lưu vào thư mục sao lưu máy chủ với nguồn "Tải lên", sau đó diễn tập hoặc phục hồi như mọi bản khác.
9. **Lỗi phải dễ hiểu và làm theo được.** Không hiện thông báo kỹ thuật như "fetch failed". Đổi các lỗi đã biết thành câu tiếng Việt:
   - "Google đã thu hồi quyền truy cập: kết nối lại Drive"
   - "Thư mục shoponline-backup trên Drive đã bị xóa"
   - "Hết dung lượng Drive"
   - "Không có mạng tới Google"

   Lỗi chưa biết thì hiện mã HTTP và ghi chi tiết vào log. Thông báo không bao giờ chứa token.
10. **Nhiều dòng.** Dùng lại phân trang và tìm kiếm phía server đã có (`pager.html`, `pagination.py`). Thêm bộ lọc theo loại, nguồn và trạng thái. Số trong tiêu đề là tổng số dòng theo bộ lọc.
11. **Quyền:** viewer xem bảng nhưng không thấy nút Tải về, Phục hồi, Xóa, Tải lên, Thử lại.
12. **Dòng đang chạy** tự cập nhật (đọc trạng thái vài giây một lần). Mọi thao tác trên dòng đó bị khóa.

**Acceptance criteria bổ sung.**
19. Bảng hiện cả lần chạy lỗi kèm lý do tiếng Việt. "Thử lại" ở cột Drive chỉ tải lại lên Drive, không tạo bản mới.
20. Bản do xoay vòng xóa ở máy chủ nhưng còn trên Drive hiện "Không có" ở cột Máy chủ và vẫn tải về và phục hồi được.
21. Phục hồi một bản có revision alembic mới hơn mã đang chạy bị từ chối, kèm thông báo.
22. Tải lên một file sai mật khẩu hoặc bị sửa một byte bị từ chối. Tải lên một file đúng tạo một dòng "Tải lên" và diễn tập được.
23. Không xóa được bản thành công mới nhất của một loại. Mỗi lần tải về và xóa có một dòng `event_log`.

## Câu hỏi còn mở

Không còn câu hỏi chặn plan.
