---
phase: 2
title: "Robot: mật khẩu, heartbeat, việc kiểm tra"
status: completed
effort: 1.5d
---

# Phase 2: Robot — mật khẩu, heartbeat, việc kiểm tra kết nối

## Bối cảnh

- [cli.py:59-125](../../src/shoponline/cli.py): robot dựng `LoginConfig` một lần từ env và thoát nếu thiếu biến.
- [worker.py](../../src/shoponline/saprobot/worker.py): `run_once` dừng khi `paused`, `claim` lấy việc PENDING cũ nhất, `WrongSystem` làm robot tự tạm dừng, `record_outcome` đếm lỗi liên tiếp.
- [session.py](../../src/shoponline/saprobot/session.py): `ensure_session`, `login`, `check_identity`, `logoff` dùng lại nguyên vẹn.
- Test dùng engine giả trong [tests/saprobot/fake_sap.py](../../tests/saprobot/fake_sap.py).

## Yêu cầu

1. **Mật khẩu** — module mới `src/shoponline/saprobot/credentials.py`:
   - `read_password(user) -> str | None`: đọc Credential Manager (`win32cred.CredRead`, target `shoponline-sap:<USER>`), nếu không có thì đọc `SHOPONLINE_SAP_PASSWORD`. Thiếu pywin32 thì chỉ dùng env.
   - `store_password(user, password)` bằng `win32cred.CredWrite`, kiểu `CRED_PERSIST_LOCAL_MACHINE`.
   - CLI: `shoponline sap-password set [--user U]` (mặc định user trong `sap_settings`; nhập bằng `getpass`, hỏi hai lần) và `shoponline sap-password status`. Không bao giờ in mật khẩu.
2. **Cấu hình theo từng việc:** `Worker` nhận hàm `login_provider(db) -> LoginConfig` thay cho `LoginConfig` cố định, dựng từ `sap_settings.load` và `read_password`. Thiếu trường thì việc lỗi với thông báo nêu đúng tên trường cần điền trên web. Robot khởi động được cả khi cấu hình SAP chưa đủ (để vẫn gửi heartbeat). `log_off_leftovers` và `evidence.prune` đọc từ `sap_settings`.
3. **Heartbeat:** ở mỗi vòng `run_forever`, ghi `last_seen_at`, `robot_host`, `password_present` (với user hiện tại), và `saplogon_entries`. Danh sách mục SAP Logon đọc từ `%APPDATA%\SAP\Common\SAPUILandscape.xml` (thuộc tính `name` của các `Service` kiểu SAPGUI), chỉ đọc lại khi file đổi thời gian sửa; lỗi đọc thì ghi danh sách rỗng và ghi log, không làm hỏng vòng lặp. Giảm `poll_seconds` từ 10 xuống 5 giây để nút kiểm tra phản hồi nhanh.
4. **Quy tắc nhận việc** — `queue.claim(db, kinds=None)` thêm lọc theo loại việc. `run_once`:
   - Nếu robot đang tạm dừng **hoặc** cấu hình chưa được xác nhận (`target_verified` sai) thì chỉ nhận `check_connection`.
   - Ngoài ra nhận như cũ.
   - Khi nhận việc đọc báo cáo, kiểm tra lại đích của việc khớp `sap_settings.target`; không khớp thì việc lỗi và robot không đăng nhập.
5. **Việc `check_connection`:**
   - Thêm `queue.CHECK_CONNECTION` vào nhóm chỉ đọc. Đích của việc lấy từ `target_system/target_client` của việc.
   - Transaction `src/shoponline/saprobot/transactions/check_connection.py`: sau `ensure_session` và `gui.check()`, đọc `identity`, thời gian đăng nhập, phiên bản SAP GUI (nếu đọc được), rồi trả về `data`. Không gửi T-code nào.
   - Khi thành công: `sap_settings.mark_verified(target)`.
   - Lỗi không làm robot tạm dừng và không gọi `record_outcome` (kể cả `WrongSystem`). Không chụp ảnh màn hình đăng nhập (màn hình có ô mật khẩu); các lỗi khác chụp như hiện nay.
   - Phân loại lỗi vào `result.reason` (một mã) và `error` (tiếng Việt kèm cách sửa): `saplogon_not_running` hoặc `scripting_disabled`, `connection_not_found`, `logon_failed` (giữ nguyên văn thông báo SAP), `wrong_system`, `foreign_session`, `missing_settings`, `missing_password`.
   - `queue.supersede_checks(db, actor)`: đánh dấu các việc `check_connection` còn PENDING là FAILED "thay bằng lần kiểm tra mới", để nút bấm lại không bị chặn bởi khóa trùng lặp khi robot đang tắt.

## Files

- Tạo: `src/shoponline/saprobot/credentials.py`, `src/shoponline/saprobot/saplogon_entries.py`, `src/shoponline/saprobot/transactions/check_connection.py`, `tests/saprobot/test_check_connection.py`, `tests/saprobot/test_credentials.py`, `tests/saprobot/test_saplogon_entries.py`
- Sửa: `src/shoponline/cli.py`, `src/shoponline/saprobot/worker.py`, `src/shoponline/saprobot/transactions/__init__.py`, `src/shoponline/sapjobs/queue.py`, `tests/saprobot/test_worker.py`, `tests/saprobot/fake_sap.py`, `tests/sapjobs/`

## Các bước

1. Test trước với engine giả: kiểm tra thành công đánh dấu xác nhận; từng mã lỗi; robot tạm dừng vẫn chạy kiểm tra nhưng không nhận việc đọc; chưa xác nhận thì không nhận việc đọc; lỗi kiểm tra không tăng bộ đếm và không tạm dừng; mật khẩu không xuất hiện trong `error`, `result` hay log (bắt bằng `caplog`).
2. `credentials.py` có hàm Credential Manager thay được trong test; `saplogon_entries.py` với file XML mẫu trong `tests/fixtures`.
3. Sửa `queue`, `worker`, `cli`.
4. Chạy tay trên máy dev có SAP GUI: `uv run shoponline sap-password status`.

## Kiểm tra

- `uv run pytest tests/saprobot tests/sapjobs` (gồm test lớp chặn T-code, không được sửa để cho qua).

## Rủi ro và lùi lại

- **Ô mật khẩu xuất hiện trong ảnh chụp:** không chụp ảnh với lỗi đăng nhập; có test kiểm.
- **Robot nhận nhầm việc đọc khi chưa xác nhận:** chặn ở hai nơi (web không xếp việc, robot không nhận việc).
- Lùi: revert commit; `SHOPONLINE_SAP_PASSWORD` vẫn được đọc nên robot chạy tiếp.
