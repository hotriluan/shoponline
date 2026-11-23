---
phase: 3
title: "Khôi phục"
status: completed
priority: P1
effort: "2d"
dependencies: [1, 2]
---

# Phase 3: Khôi phục

<!-- Updated: Red Team 2026-11-23 - thay public thay vì --clean, giữ schema ops, bản an toàn trên cùng kết nối khóa, bản cũ không manifest, chặn chồng với deploy, hủy phiên, dùng chung dừng/bật dịch vụ, restore-db.ps1 giữ nguyên -->

## Goal

`uv run shoponline backup restore <bản> --drill|--production` khôi phục an toàn mọi bản (kể cả bản cũ không manifest): diễn tập vào database tạm và so số dòng; phục hồi thật thay schema `public` (tài khoản, nhật ký sao lưu, kết nối Drive trong `ops` giữ nguyên), migrate, đối chiếu, buộc mọi người đăng nhập lại, và tự lùi về bản an toàn khi lỗi.

## Context

- [restore-db.ps1](../../scripts/windows/restore-db.ps1) dùng `pg_restore --clean --if-exists --no-owner`; `setup-production-machine.ps1:227-228` gọi nó với `-TargetSetting SHOPONLINE_DATABASE_URL -AllowProduction` vào database trống trước `migrate`. **Giữ nguyên script này**, không biến thành wrapper.
- `--clean` chỉ xóa đối tượng có trong dump: phục hồi dump cũ hơn một migration để lại bảng mới, `alembic_version` lùi về, `migrate` lỗi DuplicateTable. Vì vậy phục hồi thật xóa và tạo lại schema `public`.
- Bản cũ (`backup-db.ps1:52-55`) chỉ chứa `<db>-<stamp>.dump`, không có manifest; mọi bản hiện có đều là loại này.
- Dừng/bật dịch vụ đã có và đã chạy thật trong [update-production.ps1](../../scripts/windows/update-production.ps1) dòng 47–117 (`Test-WebUp`, `Stop-Web` diệt cả tiến trình python còn giữ cổng, `Start-Web`, `Stop-Robot`, `Start-Robot`).
- Phiên web chỉ chứa `user_id` (`web/routes/login.py:25-26`); `current_user` ở `web/app.py:53-58`; middleware phiên ở `app.py:188-192`.
- Brainstorm: quyết định 4 (C2), mục "Danh sách" điểm 2–4, tiêu chí 7, 20, 21. Red-team: mục 1, 2, 4, 5, 6, 7, 8, 11, 12, 14, 15.

## Files to Create / Modify

- Create: `scripts/windows/service-control.ps1` — chuyển `Test-WebUp`, `Stop-Web`, `Start-Web`, `Stop-Robot`, `Start-Robot` ra khỏi `update-production.ps1`; dot-source được và gọi được bằng `-Action stop|start`
- Modify: `scripts/windows/update-production.ps1` — dot-source `service-control.ps1`; ghi file đánh dấu bảo trì `deploy` lúc bắt đầu, xóa lúc kết thúc; từ chối chạy (thoát khác 0, không dừng gì) khi có đánh dấu `restore` chưa quá 2 giờ
- Create: `src/shoponline/backup/maintenance.py` — đọc/ghi `<SHOPONLINE_DATA_DIR>\maintenance.json` (`kind`, `pid`, `started_at`); đánh dấu quá 2 giờ coi là cũ
- Create: `src/shoponline/backup/restore.py` — `prepare(bản)`, `check_version(manifest)`, `drill(…)`, `production(…)`, `restore_public_schema(…)` dùng chung cho phase 6
- Modify: `src/shoponline/backup/runner.py` — `run_backup(..., conn=...)` dùng kết nối đang giữ khóa cho bản an toàn
- Modify: `src/shoponline/web/app.py` — `current_user` so `request.session["epoch"]` với `ops.system_state.session_epoch` (lệch thì xóa phiên, về trang đăng nhập) và cập nhật `ops.app_user.last_seen_at` tối đa mỗi phút; `login.py` ghi `epoch` vào phiên
- Modify: `src/shoponline/cli.py` — `backup restore <file|run_id> (--drill | --production) [--force] [--yes]`; `backup process-queue` xử lý cả `action=drill|verify|restore`
- Modify: `scripts/windows/register-tasks.ps1` — tác vụ `shoponline-restore`: `uv run --no-dev --extra robot shoponline backup process-queue --restore`, không trigger, cùng tài khoản, `MultipleInstances IgnoreNew`, giới hạn 1 giờ
- Create: `tests/backup/test_restore.py`, `tests/web/test_session_epoch.py`

## Tasks & Steps

1. `service-control.ps1`: chuyển nguyên văn các hàm, `update-production.ps1` dot-source; chạy một deploy trên máy dev bằng tay để chắc hành vi không đổi.
2. `prepare`:
   - Tìm bản theo tên hoặc `run_id`; chỉ có trên Drive thì tải về thư mục sao lưu đầu tiên, so MD5.
   - `sevenzip.require_encrypted`, giải nén vào `staging_dir()` theo danh sách tên được phép.
   - Có `manifest.json`: so SHA-256 từng phần. Không có (bản cũ): `legacy=True`, lấy file `*.dump` duy nhất, bỏ qua SHA-256 và so số dòng, ghi cảnh báo.
3. `check_version`: revision trong manifest phải bằng hoặc là tổ tiên của `head` (`alembic.script.ScriptDirectory`); mới hơn → từ chối "Bản sao lưu từ phiên bản mới hơn (revision X), cập nhật mã trước" (tiêu chí 21). Bản cũ: chỉ biết revision sau khi diễn tập (đọc `alembic_version` trong database diễn tập); phục hồi thật bản cũ đòi `--force`.
4. `drill`: chỉ vào `SHOPONLINE_RESTORE_DATABASE_URL`, từ chối nếu trùng database đang chạy; `DROP SCHEMA public CASCADE; DROP SCHEMA IF EXISTS ops CASCADE; CREATE SCHEMA public`, rồi `pg_restore --no-owner --exit-on-error --single-transaction`; so số dòng `public` với manifest; trả bảng khác biệt vào `backup_request.result`.
5. `restore_public_schema(dump, target_conn)`: `pg_restore -l` lấy mục lục, bỏ mọi mục thuộc schema `ops`, ghi file danh sách; `DROP SCHEMA public CASCADE; CREATE SCHEMA public` (giữ quyền như `create-databases.ps1` đã cấp); `pg_restore -L <danh sách> --no-owner --exit-on-error --single-transaction`.
6. `production`, thứ tự cố định; tiến độ ghi vào `ops.backup_request.message` (bảng này không bị đụng) và `restore-status.json`:
   1. Từ chối khi có đánh dấu bảo trì `deploy` còn hiệu lực; ghi đánh dấu `restore`.
   2. Mở một kết nối giữ `pg_advisory_lock` sao lưu suốt quá trình, `lock_timeout` 5 phút.
   3. Có người dùng khác có `last_seen_at` trong 5 phút → cần `--force` (web hiện cảnh báo trước khi gửi, rồi truyền `--force`).
   4. Dừng robot, dừng web qua `service-control.ps1 -Action stop`.
   5. Bản an toàn `full`, nguồn `safety`, gọi `run_backup(conn=<kết nối đang giữ khóa>)`; ghi `safety_run_id`; không có file bản an toàn thì dừng ở đây, bật lại web và robot.
   6. Bản `full`: với từng mục cấp cao trong `data/` của gói (trừ `logs`, `robot-work`, `backup-work`), chuyển mục hiện có sang `<data>\backup-work\before-restore-<stamp>\` rồi chép mục mới vào. Không đổi tên cả thư mục dữ liệu (log của chính tiến trình nằm trong đó). Thư mục `before-restore-*` giữ 7 ngày rồi `sweep_stale` xóa.
   7. `restore_public_schema`.
   8. `migrate` (migration `ops` idempotent nên chạy lại an toàn); so số dòng `public` với manifest.
   9. Tăng `ops.system_state.session_epoch`.
   10. Bật web, chờ `/login`; bật robot; xóa đánh dấu `restore`.
   11. Lỗi ở bước 6–10: lùi lại bằng bản an toàn theo cùng bước 6–10, trạng thái `rolled_back` kèm lý do. Lùi lại cũng lỗi: `failed`, giữ đánh dấu `restore`, in đúng lệnh CLI cho người quản trị.
7. `process-queue --restore`: chỉ nhận yêu cầu `restore` ở trạng thái `pending` tạo trong 10 phút gần nhất; cũ hơn đánh `expired`.
8. Phiên: thêm `epoch` vào phiên khi đăng nhập; `current_user` kiểm; cập nhật `last_seen_at` có giới hạn tần suất.

## Verification

- `uv run pytest tests/backup/test_restore.py tests/web/test_session_epoch.py -q`, gồm:
  - Phục hồi dump ở revision `0009` (bản cũ, không manifest) vào database đang ở head rồi `migrate`: thành công, `ops.app_user`, `ops.backup_run` không đổi.
  - Phục hồi rồi tạo bản sao lưu mới ngay: chèn `backup_run` không lỗi khóa trùng.
  - Từ chối revision mới hơn; gói không mã hóa bị từ chối; gói sửa một byte bị từ chối.
  - `migrate` bị ép lỗi → `rolled_back`, dữ liệu `public` bằng bản an toàn, `safety_run_id` có và file tồn tại trước khi `pg_restore` chạy.
  - Phiên cũ sau khi tăng `session_epoch` bị đưa về trang đăng nhập.
  - Yêu cầu phục hồi tạo 11 phút trước bị `expired`.
- Trên máy dev: `backup restore <bản full> --drill` khớp; `--production --yes` trên database dev (đã sao lưu dev trước).
- `pwsh -File scripts\windows\restore-db.ps1 -Archive <bản cũ>` vẫn chạy như trước (script không đổi).
- Deploy thử trên máy dev khi có đánh dấu `restore`: `update-production.ps1` từ chối và không dừng web.

## Risks

- Phục hồi thật là thao tác nguy hiểm: bản an toàn có trước khi đụng dữ liệu, lùi lại tự động, phục hồi bản cũ cần `--force`.
- Quyền schema `public` sau khi tạo lại: test kiểm role `shoponline_app` vẫn đọc/ghi được.
- Tài khoản không lùi theo bản sao lưu (chủ dự án chốt): hộp thoại ở phase 5 ghi rõ; nhật ký `event_log` (trong `public`) vẫn lùi về.

## Rollback

Roll-forward; không có migration mới. Gỡ tác vụ `shoponline-restore` bằng `Unregister-ScheduledTask`. `service-control.ps1` có thể giữ lại vì `update-production.ps1` dùng nó.
