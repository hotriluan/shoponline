---
phase: 2
title: "Google Drive client"
status: completed
priority: P1
effort: "1.5d"
dependencies: [1]
---

# Phase 2: Google Drive client

<!-- Updated: Red Team 2026-11-23 - một module secrets_store, bảng trong ops, device flow chạy được trước khi có dữ liệu, cùng tài khoản Windows -->

## Goal

Module `shoponline.backup.drive` kết nối Google Drive bằng OAuth device flow, cất bí mật trong Credential Manager, tải bản sao lưu lên có kiểm MD5, liệt kê, tải về, xóa, thu hồi; `backup run` dùng nó làm nơi lưu thứ hai với xoay vòng N bản mỗi loại; có CLI `drive set-client|connect|status|disconnect`.

## Context

- Google xác nhận `drive.file` nằm trong danh sách scope của device flow: <https://developers.google.com/identity/protocols/oauth2/limited-input-device>. Client phải là loại "TVs and Limited Input devices".
- Endpoint: `https://oauth2.googleapis.com/device/code`, `/token` (grant `urn:ietf:params:oauth:grant-type:device_code`, và `refresh_token`), `/revoke`; Drive v3 `files` (`uploadType=resumable`), `about?fields=user(emailAddress)`.
- Cất bí mật hiện có: [credentials.py](../../src/shoponline/saprobot/credentials.py) dòng 21–70; test monkeypatch `credentials._win32cred` ở `tests/saprobot/test_credentials.py:29,63`; người dùng: `cli.py:134,146,156`, `saprobot/worker.py:28,238`. CI chạy Ubuntu (`.github/workflows/deploy.yml:20`), không có pywin32.
- Credential Manager theo **tài khoản Windows**: web, tác vụ sao lưu, tác vụ phục hồi và lệnh CLI cấu hình Drive phải chạy cùng một tài khoản. Chế độ `-AtLogOn` (máy thật hiện tại) thỏa điều này; chế độ tài khoản riêng (`-User MAYCHU\shoponline`) thì phải chạy `drive connect` bằng chính tài khoản đó.
- Brainstorm: "Kết nối Google Drive trên web", tiêu chí 11–15. Red-team: mục 3, 9, 15.

## Files to Create / Modify

- Create: `src/shoponline/secrets_store.py` — `read(target)`, `write(target, value)`, `delete(target)`, `_win32cred()` (lỗi `CredentialStoreUnavailable` khi thiếu pywin32)
- Modify: `src/shoponline/saprobot/credentials.py` — thành lớp mỏng gọi `secrets_store`; giữ tên hàm công khai
- Modify: `tests/saprobot/test_credentials.py:29,63` — đổi đích monkeypatch sang `shoponline.secrets_store._win32cred`
- Create: `src/shoponline/backup/drive.py` — `DriveClient` (start/poll device flow, refresh, ensure_folder, upload, list, download, delete, revoke, about), `friendly_error()`; hai hằng target `shoponline/google-drive/client-secret`, `…/refresh-token`
- Create: `migrations/versions/0011_drive_connection.py` — `ops.drive_connection` (một dòng, idempotent): `client_id`, `folder_id`, `account_email`, `status`, `last_error`, `checked_at`, `device_code`, `user_code`, `verification_url`, `device_expires_at`, `poll_interval`, `changed_by`, `changed_at`
- Modify: `src/shoponline/db/models.py`
- Modify: `src/shoponline/backup/runner.py` — cắm Drive vào `upload_to_drive`; xử lý `backup_request` `action=retry_drive` (chỉ tải lại, không tạo bản mới)
- Modify: `src/shoponline/cli.py` — `drive set-client --client-id` (Secret hỏi bằng `getpass`), `drive connect` (in mã và link, chờ), `drive status`, `drive disconnect`
- Modify: `pyproject.toml` — chuyển `httpx` từ nhóm dev lên `dependencies`; `uv lock`
- Create: `tests/backup/test_drive.py` — giả lập Google bằng `httpx.MockTransport`; giả lập kho bí mật bằng fixture

## Tasks & Steps

1. `secrets_store.py`, đổi `credentials.py` và hai chỗ monkeypatch; `uv run pytest tests/saprobot` xanh.
2. Device flow: `start_device_flow()` lưu trạng thái chờ vào `ops.drive_connection`; `poll_device_flow()` gọi token endpoint một lần, xử lý `authorization_pending`, `slow_down` (tăng interval 5 giây), `access_denied`, `expired_token`; thành công thì cất refresh token, xóa `device_code`, `about` lấy email, `ensure_folder()`. Vì `ops` có ngay sau `migrate` (database còn trống dữ liệu nghiệp vụ), CLI `drive connect` chạy được trên máy mới trước khi nhập gói (phase 6).
3. `ensure_folder()`: có `folder_id` và `files.get` thấy (không `trashed`) thì dùng; không thì tìm thư mục `shoponline-backup` do app tạo; không có thì tạo.
4. Upload resumable theo khúc 8 MB, retry 3 lần với 5xx/mạng; so `md5Checksum` với MD5 cục bộ. Download theo khúc, so MD5.
5. `list_backups()` (tên, kích thước, md5, thời điểm, id), phân trang `pageToken`; chỉ file đúng mẫu tên.
6. `revoke()` rồi xóa refresh token; đổi `client_id` hoặc Secret thì xóa refresh token, `status = disconnected`.
7. `friendly_error()`: `invalid_grant` (quyền bị thu hồi hoặc hết hạn — nhắc kiểm tra Publish to production), 404 thư mục, `storageQuotaExceeded`, lỗi mạng, `invalid_client`; lỗi khác "Google Drive trả lỗi HTTP <mã>". Không bao giờ đưa body chứa token vào thông điệp hay log.
8. Cắm vào `runner.py` và xoay vòng Drive.

## Verification

- `uv run pytest tests/backup/test_drive.py tests/saprobot -q`
- Test: device flow đủ năm nhánh; thư mục tạo đúng một lần khi kết nối lại (tiêu chí 11); `invalid_grant`, thư mục bị xóa, mạng lỗi cho đúng câu (tiêu chí 13); `caplog` và lỗi không chứa token giả (tiêu chí 12); `retry_drive` không tạo `backup_run` mới (tiêu chí 19).
- Thử thật với OAuth client của chủ dự án khi có (không chặn merge).

## Risks

- OAuth client để ở Testing: refresh token hết hạn sau 7 ngày (`invalid_grant`); câu lỗi nhắc đúng nguyên nhân.
- pywin32 thiếu (dev, CI): `drive` báo "Credential Manager không dùng được" thay vì crash.
- Quota 15 GB của Gmail cá nhân: manifest ghi kích thước để theo dõi.

## Rollback

Roll-forward như phase 1: giữ file migration `0011`; revert mã. Xóa hai credential bằng `drive disconnect` hoặc `cmdkey /delete`.
