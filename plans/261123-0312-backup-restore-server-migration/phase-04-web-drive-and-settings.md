---
phase: 4
title: "Web: kết nối Drive, sao lưu ngay, cài đặt"
status: completed
priority: P1
effort: "1.5d"
dependencies: [1, 2]
---

# Phase 4: Web: kết nối Drive, sao lưu ngay, cài đặt

<!-- Updated: Red Team 2026-11-23 - quyền admin cho mọi route trừ trang xem, poll bằng POST, banner chỉ đọc database, bỏ đường dev chạy pg_dump từ web, khóa nút theo pg_locks -->

## Goal

Trang `/backup` có ba khối phía trên bảng danh sách: **Sao lưu ngay** (ba thẻ + ô Drive), **Kết nối Google Drive** (bước A, bước B, hướng dẫn 4 bước), **Lịch và số bản giữ**; banner cảnh báo sao lưu dựa trên `backup_run` thay cho `last-backup.txt`.

## Context

- Mẫu route: [robot.py](../../src/shoponline/web/routes/robot.py) (`current_user`, `require_admin`, `flash`, `redirect`, `render`); router nằm trong danh sách viết tay ở [app.py](../../src/shoponline/web/app.py) dòng 213–225, phải thêm `backup` vào đó; banner `backup_warning` ở `app.py` dòng 71 và [base.html](../../src/shoponline/web/templates/base.html) dòng 80.
- Mẫu trang cấu hình có kiểm tra kết nối: [sap_connection.html](../../src/shoponline/web/templates/sap_connection.html), test [test_sap_connection.py](../../tests/web/test_sap_connection.py).
- Brainstorm: mục "Kết nối Google Drive trên web", "Khối Sao lưu ngay", tiêu chí 5, 11–18.

## Files to Create / Modify

- Create: `src/shoponline/web/routes/backup.py` — trang và các POST/JSON endpoint của phase này
- Create: `src/shoponline/web/templates/backup.html` — trang chính (phase 5 thêm bảng)
- Create: `src/shoponline/web/templates/backup_drive.html` — partial khối Drive
- Create: `src/shoponline/backup/trigger.py` — `enqueue(action, …, actor)`: ghi `ops.backup_request`, gọi `schtasks /Run /TN shoponline-backup` và kiểm mã thoát; lỗi thì trang báo "sẽ chạy trong vòng 15 phút" (tác vụ lặp 15 phút sẽ xử lý). Không có đường chạy `pg_dump` từ tiến trình web; trên máy dev chạy `backup process-queue` bằng tay.
- Modify: `src/shoponline/web/app.py` — thêm `backup` vào danh sách router; `backup_warning` chỉ đọc database trong một truy vấn có index: bản `db` thành công gần nhất ở máy chủ và ở Drive (khi `ops.drive_connection.status = connected`) so với mốc lịch gần nhất + 2 giờ; không có bản `full` thành công trong 8 ngày (bản Toàn bộ chỉ giữ 30 ngày, nên lịch tuần hỏng lâu sẽ làm mất hết bản Toàn bộ); và `drive_connection.status = error`. Không bao giờ gọi Google trên đường xử lý request. Bỏ đọc `last-backup.txt`.
- Modify: `src/shoponline/web/templates/base.html` — mục menu "Sao lưu"
- Create: `tests/web/test_backup_page.py`

## Tasks & Steps

1. **Sao lưu ngay:** ba thẻ (Database / Ứng dụng / Toàn bộ) với mô tả đúng dữ liệu dự án (brainstorm bảng "Thẻ"). POST `/backup/run` (admin) → `enqueue("backup", …)`. Ba nút bị khóa khi có `backup_request` `pending` hoặc khi khóa advisory sao lưu đang thật sự bị giữ (`pg_locks`); dòng `running` mà không ai giữ khóa là dòng mồ côi và không khóa nút (runner sẽ đánh `interrupted`). POST kiểm lại cùng điều kiện và trả "Đang có bản sao lưu chạy". Ô "Lưu thêm 1 bản lên Google Drive": đánh dấu sẵn khi Drive `connected`, khóa kèm "Chưa kết nối Google Drive" khi chưa.
2. **Drive bước A:** POST `/backup/drive/client` lưu Client ID (database) và Secret (Credential Manager); ô trống giữ giá trị cũ; nhãn "Đã lưu (được mã hóa)" khi có Secret. Không bao giờ render Secret hay token.
3. **Drive bước B:**
   - POST `/backup/drive/connect` → `start_device_flow`, hiển thị `user_code` lớn, nút chép, link `https://www.google.com/device`, đồng hồ hết hạn.
   - JS gọi `POST /backup/drive/poll` (admin; nó thay đổi trạng thái nên không dùng GET) theo `poll_interval`; endpoint gọi `poll_device_flow` một lần và trả trạng thái JSON; thành công thì tải lại khối.
   - Nút **Kiểm tra kết nối** (POST, ghi `checked_at`), **Xem các bản trên Drive** (cuộn tới bảng ở phase 5 với bộ lọc "trên Drive"; trước khi có phase 5 thì hiện danh sách đơn giản), **Ngắt kết nối** (xác nhận → `revoke`).
   - Hiện email, tên và ID thư mục.
4. **Hướng dẫn 4 bước** (khối mở ra): tạo project; bật Google Drive API; consent screen External, scope `drive.file`, **Publish to production** (in đậm lý do: Testing làm mất kết nối sau 7 ngày); Credentials → OAuth client ID → **TVs and Limited Input devices**. Có link tới Google Cloud Console.
5. **Lịch và số bản giữ** (admin): giờ `db`, thứ + giờ `full`, số bản giữ `keep_db` (15), `keep_app` (15) (1–100) và số ngày giữ bản Toàn bộ `full_max_days` (30, cho phép 7–90), áp dụng cho cả máy chủ và Drive, "Bản theo lịch lên Drive"; hiện "Lần chạy kế tiếp" tính từ `schedule.py`. Lưu ghi `changed_by`.
6. Banner cảnh báo mới; viewer thấy trạng thái, không thấy nút và form.
7. Quyền: mọi route `/backup/*` dùng `require_admin`, trừ `GET /backup` (trang xem). Mẫu tải file hiện có dùng `current_user` (`batches.py:140-145`, `robot.py:199-204`) — không chép mẫu đó cho route sao lưu.

## Verification

- `uv run pytest tests/web/test_backup_page.py -q`: viewer bị chặn ở mọi route `/backup/*` trừ trang xem, kể cả các GET và `POST /backup/drive/poll`; banner không gọi HTTP ra ngoài (test với transport httpx ném lỗi); trang không chứa Secret/token giả đã cất (tiêu chí 12); bấm khi đang chạy không tạo `backup_request` thứ hai (tiêu chí 17); ô Drive bị khóa khi chưa kết nối (tiêu chí 18); lưu lịch đổi "lần chạy kế tiếp".
- Thủ công trên dev: bấm "Sao lưu Database ngay", dòng "Đang chạy" có trong `backup_run` dưới 5 giây.

## Risks

- `schtasks /Run` cần tác vụ cùng tài khoản: trên máy `-AtLogOn` đúng là vậy; chưa kiểm chứng được tiến trình web quyền thường có chạy được tác vụ đăng ký bằng quyền quản trị không — phase 7 thử trên máy thật. Nếu lỗi, yêu cầu vẫn còn và tác vụ 15 phút xử lý.
- Poll device flow khi hai admin cùng bấm: chỉ một phiên chờ trong `drive_connection`; bấm lần hai khi còn hạn hiện lại mã cũ.

## Rollback

Revert commit; xóa route và template. Không có thay đổi schema.
