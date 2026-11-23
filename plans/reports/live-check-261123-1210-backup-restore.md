# Báo cáo diễn tập: sao lưu, khôi phục và chuyển máy

Ngày 2026-11-23. Phạm vi: [plan](../261123-0312-backup-restore-server-migration/plan.md) và [brainstorm](brainstorm-261123-0955-backup-restore-server-migration.md).

## Kết luận

Cả bảy phase đã làm xong mã, test và tài liệu trên máy dev, chưa push. Bằng chứng ở dưới là test tự động (pytest, `pg_dump`, `pg_restore`, 7-Zip và Alembic thật; Google và Windows Credential Manager giả lập) cộng vài lần chạy tay trên máy dev. **Chưa có bước nào chạy trên máy chạy thật**: cột "Trên máy thật" liệt kê việc còn lại, cần chủ dự án (OAuth client, push `main`, giờ ngoài giờ xử lý đơn).

Máy dev này có các tác vụ `shoponline-*` đang Disabled, nên tôi không chạy `service-control.ps1`, `server-export.ps1` (không `-Prepare`) hay phục hồi thật bằng script, vì chúng sẽ dừng hoặc bật tác vụ thật.

## 23 tiêu chí

| # | Tiêu chí | Bằng chứng trên máy dev | Trên máy thật |
|---|---|---|---|
| 1 | `backup run --kind db\|full` tạo `.7z` mã hóa có manifest, lên máy chủ và Drive, Drive xác nhận checksum | `test_runner::test_full_backup_contents_and_manifest`; Drive: `test_drive::test_upload_in_pieces_list_download_delete`, `…wrong_md5…` (MD5 sai thì xóa file và lỗi); chạy tay ba loại, `7z l` không mật khẩu thất bại | Upload thật lên Drive của chủ dự án |
| 2 | Bản `full` có dữ liệu, `.env` bỏ mật khẩu, git bundle | cùng test; chạy tay: `env` không có `SHOPONLINE_BACKUP_PASSWORD`, dump có 25 bảng `public` và 5 bảng `ops` | |
| 3 | Một nơi hỏng thì nơi kia vẫn nhận, mã 2, không dọn khi bản mới chưa tới | `test_one_broken_place_gives_exit_2_and_keeps_its_old_files`, `test_scheduled_run_uploads_and_a_drive_failure_gives_exit_2` | Ngắt mạng thật, thử lại |
| 4 | Xoay vòng theo số bản, riêng từng nơi (đổi theo quyết định chủ dự án: `db` 15, `app` 15, `full` ≤ 30 ngày) | `test_naming_retention_schedule` (11 test cho bộ chọn) | |
| 5 | Lịch sửa trên web; tác vụ 15 phút; chạy bù | `test_saving_the_schedule_changes_the_next_run`, `test_machine_off_at_slot_catches_up_once`, `test_friday_runs_database_then_full`; `register-tasks.ps1` chỉ kiểm cú pháp | Đăng ký tác vụ và xem `-OnlyMissing` đổi trigger cũ; 24 giờ sau lịch 16:30 chạy |
| 6 | Trang Sao lưu: trạng thái, danh sách, sao lưu ngay, kiểm tra, diễn tập; viewer chỉ xem | `test_backup_page.py`, `test_backup_list.py` (viewer bị chặn ở mọi route khác); diễn tập: `test_drill_compares_rows_and_refuses_the_running_database` | Máy dev không có database diễn tập (role ứng dụng không tạo được database): cần tạo `SHOPONLINE_RESTORE_DATABASE_URL` |
| 7 | Phục hồi thật từ web: dừng, bản an toàn, phục hồi, migrate, so số dòng, tự lùi, banner | `test_restore.py` (bản cũ không manifest rồi `migrate`; thay file dữ liệu; migrate lỗi thì `rolled_back` và bản an toàn có trước `pg_restore`; lùi cũng lỗi thì giữ đánh dấu và in lệnh), `test_restore_outcome_is_shown_once_to_the_first_admin` | Chạy nút web thật ngoài giờ; ghi lại `schtasks /Run` từ tiến trình web có chạy được tác vụ đăng ký bằng quyền quản trị không (nếu không, trang báo sau 2 phút) |
| 8 | Chuyển máy bằng hai lệnh, đối chiếu số dòng, không hai runner | `test_new_machine_restore.py` (10 test: tài khoản đăng nhập được, lịch lấy từ gói, kết nối Drive của máy mới giữ nguyên, `.env`); `server-export.ps1 -Prepare` chạy trên dev tạo bản `full` nguồn "Chuyển máy"; truy vấn runner GitHub kiểm bằng dữ liệu thật (chỉ đọc); ba script parse được, `setup-production-machine.ps1` cả trên Windows PowerShell 5.1 | Dựng máy thử bằng `-Bundle drive:latest -Prepare`; ngày chuyển thật |
| 9 | `backup-db.ps1` chạy được từ `update-production.ps1`; deploy tiếp theo xanh | Chạy wrapper trên dev: mã 0, bản nguồn `deploy`, không lên Drive; mã 3 khi khóa bận (`test_lock_busy_gives_exit_3_and_no_backup`) | Job `deploy` xanh sau khi push |
| 10 | Tài liệu đúng lệnh, biến, thời hạn | README, `.env.example`, system-architecture, deployment-guide (mục 6, 6b, 7, chuyển máy, khi máy hỏng), security-and-data-retention, operations-runbook, daily-operations; đã kiểm mọi link và anchor | |
| 11 | Kết nối Drive trên web; thư mục tạo đúng một lần | `test_connect_flow_through_the_web`, `test_folder_is_created_once_across_reconnects` | Tạo OAuth client và kết nối thật |
| 12 | Không response, log, bản sao lưu nào chứa secret hay token | `test_no_secret_or_token_in_state_errors_or_logs`, `test_connect_flow_through_the_web` (trang không chứa Secret, refresh token, access token), `test_password_never_in_errors_or_logs` | |
| 13 | Kiểm tra kết nối: hoạt động, `invalid_grant`, thư mục bị xóa | `test_check_ok_revoked_and_folder_deleted`, `test_revoked_access_shows_a_plain_message` | |
| 14 | Ngắt kết nối thu hồi token; sau đó sao lưu không lên Drive và web cảnh báo | `test_check_and_disconnect` (thu hồi), `test_banner_when_scheduled_backups_find_drive_disconnected` | |
| 15 | `drive connect` trên CLI cùng kết quả như nút web | `test_drive_cli.py` (set-client, connect có in mã, status, disconnect, từ chối) | Chạy trên máy mới |
| 16 | Mỗi nút tạo đúng loại, đúng nội dung | `test_app_backup_has_no_database`, `test_full_backup_contents_and_manifest`; ba thẻ trong `backup.html` | |
| 17 | Dòng "Đang chạy" dưới 5 giây; bấm lần hai không tạo bản thứ hai | `test_a_second_click_while_one_waits_makes_no_second_request`; chạy tay hai `backup run` cùng lúc: một bản, lệnh sau thoát mã 3 | Đo thời gian thật từ lúc bấm |
| 18 | Ô Drive bỏ chọn thì không lên Drive; khóa khi chưa kết nối | `test_drive_checkbox_is_locked_until_connected` | |
| 19 | Bảng hiện cả lần lỗi; "Thử lại" không tạo bản mới | `test_failed_runs_show_their_reason_and_drive_retry_makes_no_new_run`, `test_retry_drive_uploads_without_a_new_run` | |
| 20 | Bản bị xoay vòng ở máy chủ nhưng còn trên Drive vẫn tải về và phục hồi được | `test_a_backup_only_on_drive_is_listed_once_and_downloads_and_restores` | |
| 21 | Bản có revision mới hơn mã bị từ chối | `test_newer_backup_cannot_be_restored`, `test_newer_backup_is_refused_before_services_stop`, `test_newer_bundle_is_refused` | |
| 22 | Tải lên: sai mật khẩu, sửa một byte bị từ chối; file đúng tạo dòng "Tải lên" | `test_wrong_password_file_is_refused_and_leaves_nothing`, `test_changed_byte_is_refused`, `test_unencrypted_file_is_refused`, `test_a_good_backup_can_be_uploaded`, giới hạn 1 GB và ổ đầy | Diễn tập bản vừa tải lên trên máy thật |
| 23 | Không xóa được bản thành công mới nhất mỗi loại; mỗi lần tải về và xóa có dòng `event_log` | `test_delete_rules_and_log`, `test_the_safety_backup_of_the_latest_restore_is_kept`, `test_a_backup_only_on_drive_…` (dòng `backup_download`) | |

## Kết quả kiểm tra tổng

- `uv run ruff check src tests migrations`: sạch.
- `uv run pytest`: 610 test đạt (trước phase 1 là 460; thêm 150 test cho tính năng này).
- Dev: migrate `0010`, `0011` lên database dev sau khi `pg_dump` nó ra file; ba loại sao lưu, hai lệnh chạy đồng thời, wrapper `backup-db.ps1`, `server-export.ps1 -Prepare`.

## Việc còn lại trên máy thật (theo thứ tự đề xuất)

1. Push `main` (deploy tự chạy). Job `deploy` phải xanh; bản `db` nguồn "Trước deploy" xuất hiện trong bảng. Deploy đầu tiên chạy bản `update-production.ps1` cũ trên đĩa; các thay đổi trong script (tạm tắt tác vụ sao lưu, đánh dấu bảo trì) có hiệu lực từ deploy sau.
2. Tạo OAuth client (hướng dẫn 4 bước trên trang), kết nối Drive, ba nút sao lưu lên Drive, ngắt rồi nối lại để thử "Thử lại".
3. Tạo database diễn tập (`postgres` tạo `shoponline_restore`, đặt `SHOPONLINE_RESTORE_DATABASE_URL`), diễn tập bản `full` và một bản cũ làm bằng `backup-db.ps1` trước đây.
4. Phục hồi thật từ web ngoài giờ với một bản `db` tạo trước migration gần nhất; ghi lại `schtasks /Run`.
5. `server-export.ps1 -Prepare`, dựng máy thử bằng `-Bundle drive:latest -Prepare` rồi gỡ máy thử.
6. Sau 24 giờ: lịch 16:30 đã chạy khi web và robot vẫn chạy.

## Câu hỏi còn mở

- Cột "Trên máy thật" cần ghi kết quả vào bảng này khi làm xong; chưa ai làm.
- Role `shoponline_app` không có quyền tạo database nên không thể tự động hóa việc tạo database diễn tập; có muốn `create-databases.ps1` tạo luôn `shoponline_restore` không?
- Ngay từ lần deploy đầu, banner cam sẽ báo "Google Drive chưa kết nối" và "chưa có bản Toàn bộ" cho tới khi Drive được nối và bản `full` đầu tiên (thứ Sáu 16:30 hoặc bấm tay) chạy xong. Đây là hành vi đúng nhưng ồn; có muốn tắt ô "Bản theo lịch lên Google Drive" tới khi nối Drive không?
