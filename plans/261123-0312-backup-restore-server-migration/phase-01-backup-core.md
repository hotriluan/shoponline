---
phase: 1
title: "Lõi sao lưu, lịch và xoay vòng"
status: completed
priority: P1
effort: "2.5d"
dependencies: []
---

# Phase 1: Lõi sao lưu, lịch và xoay vòng

<!-- Updated: Red Team 2026-11-23 - schema ops, mã thoát khóa bận, snapshot, staging, xoay vòng N bản, trigger tác vụ, bỏ phần thêm ngoài phạm vi -->

## Goal

`uv run shoponline backup run --kind db|app|full` tạo bản `.7z` mã hóa có manifest nhất quán với dump, ghi `ops.backup_run`, xoay vòng N bản mỗi loại, chạy theo lịch trong database; `backup-db.ps1` vẫn giữ hợp đồng cho deploy và không bao giờ báo thành công khi không có bản sao lưu.

## Context

- Hiện có: [backup-db.ps1](../../scripts/windows/backup-db.ps1) (pg_dump → 7z → chép → xoay vòng → `last-backup.txt`, mã thoát 0/2), [backup-rotation.ps1](../../scripts/windows/backup-rotation.ps1), [settings.ps1](../../scripts/windows/settings.ps1), [register-tasks.ps1](../../scripts/windows/register-tasks.ps1).
- [update-production.ps1](../../scripts/windows/update-production.ps1) dòng 142–149: dừng robot và web, gọi `backup-db.ps1` (chấp nhận 0 hoặc 2), rồi `git merge`, `uv sync`, `migrate`. Runner chạy bản script trên đĩa.
- `-OnlyMissing` hiện giữ nguyên trigger (`register-tasks.ps1:17-19, 67-71`; `Test-TaskMatches` trong `settings.ps1:82-89` không so trigger).
- Không có khóa ngoại nào trỏ tới `app_user` ([models.py](../../src/shoponline/db/models.py)), nên có thể chuyển nó sang schema khác.
- Brainstorm: "Hợp đồng", "Khối Sao lưu ngay", quyết định 2 và lịch. Red-team: mục 2, 5, 8, 9, 10, 11, 12, 13, 14, 15.

## Schema `ops`

Dữ liệu vận hành phải sống qua một lần phục hồi trên cùng máy nằm trong schema riêng `ops`; dữ liệu nghiệp vụ ở `public`. Bản sao lưu dump **cả hai** schema. Phục hồi trên cùng máy chỉ thay `public` (phase 3); nhập gói trên máy mới lấy cả `ops.app_user` (phase 6).

- `ops.app_user` (chuyển từ `public`, thêm `last_seen_at`): chủ dự án chốt tài khoản không lùi theo bản sao lưu.
- `ops.system_state` (một dòng): `session_epoch` (tăng sau mỗi lần phục hồi để buộc đăng nhập lại, phase 3).
- `ops.backup_settings` (một dòng): `db_time` (16:30), `full_weekday` (4 = thứ Sáu, theo `date.weekday()` của Python: thứ Hai = 0), `full_time` (16:30), <!-- Updated: Validation Session 3 - giờ tự động đổi từ 23:00/23:15 sang 16:30 --> <!-- Updated: Validation Session 4 - bản Toàn bộ hằng tuần đổi từ Chủ nhật sang thứ Sáu --> `keep_db` (15 bản), `keep_app` (15 bản), `full_max_days` (30 ngày), `drive_on_schedule` (true), `changed_by`, `changed_at`. Áp dụng như nhau cho máy chủ và Drive. <!-- Updated: Validation Session 2 - bản Toàn bộ giữ theo tuổi, tối đa 30 ngày, thay cho 4 bản -->
- `ops.backup_run`: `id`, `kind`, `source` (`schedule|manual|deploy|safety|migration|upload|drive_found`), `actor`, `file_name`, `size_bytes`, `sha256`, `manifest` (JSONB), `started_at`, `finished_at`, `local_status`, `local_error`, `drive_requested`, `drive_status`, `drive_file_id`, `drive_error`, `verified_at`, `verify_result`, `deleted_by`, `deleted_at`. Index duy nhất từng phần trên `drive_file_id` khi khác null.
- `ops.backup_request` (hàng đợi duy nhất cho mọi thao tác chạy nền): `id`, `action` (`backup|retry_drive|drill|verify|restore`), `kind`, `target_run_id`, `to_drive`, `requested_by`, `requested_at`, `status` (`pending|running|done|failed|rolled_back|expired|interrupted`), `started_at`, `finished_at`, `message`, `result` (JSONB), `safety_run_id`.

**Quy tắc cho mọi migration đụng `ops`: viết idempotent** (`CREATE … IF NOT EXISTS`, kiểm tra cột trước khi thêm). Lý do: phục hồi một dump cũ đưa `public.alembic_version` lùi về, rồi `migrate` chạy lại các migration đó trong khi `ops` vẫn ở bản mới nhất. Ghi quy tắc này vào docstring của `0010` và vào [system-architecture.md](../../docs/system-architecture.md) (phase 7).

## Files to Create / Modify

- Create: `migrations/versions/0010_backup.py` — tạo schema `ops`, các bảng trên (idempotent); chuyển `app_user`: nếu `ops.app_user` đã có thì `DROP TABLE IF EXISTS public.app_user`, không thì `ALTER TABLE public.app_user SET SCHEMA ops`, rồi thêm `last_seen_at` nếu chưa có. Sao lưu database dev trước khi chạy.
- Modify: `src/shoponline/db/models.py` — `AppUser` có `__table_args__ = {"schema": "ops"}`; model mới cho bảng `ops`.
- Modify: `migrations/env.py` nếu cần để autogenerate thấy schema `ops` (`include_schemas=True`).
- Create: `src/shoponline/backup/__init__.py`
- Create: `src/shoponline/backup/naming.py` — tên mới `shoponline-<kind>-<db>-yyyyMMdd-HHmmss.7z`; tên cũ `shoponline-<db>-…` là `kind=db`, `legacy=True`.
- Create: `src/shoponline/backup/staging.py` — `staging_dir()` context manager: thư mục con trong `<SHOPONLINE_DATA_DIR>\backup-work` (thừa hưởng ACL chỉ chủ tài khoản của thư mục dữ liệu), xóa khi thoát kể cả khi lỗi; `sweep_stale()` xóa thư mục con cũ hơn 1 ngày ở đầu mỗi lần chạy. Không bao giờ dùng `%TEMP%`.
- Create: `src/shoponline/backup/sevenzip.py` — gọi 7z: tạo (`-mhe=on`), kiểm tra, giải nén theo danh sách tên được phép; `require_encrypted()` (liệt kê không mật khẩu phải thất bại và `7z l -slt` báo `Encrypted = +` cho mọi mục); chặn mục có đường dẫn tuyệt đối hoặc `..`. Mật khẩu: thử truyền qua stdin (`-p` không giá trị); nếu kiểm thử cho thấy 7z không đọc stdin trên Windows thì dùng `-p<mật khẩu>` và mọi exception mang argv đã che. Bộ lọc log che chuỗi `-p\S+` gắn vào root logger.
- Create: `src/shoponline/backup/manifest.py` — dataclass manifest; đếm dòng mọi bảng `public` trong **cùng snapshot** với dump; SHA-256 từng phần.
- Create: `src/shoponline/backup/archive.py` — dựng nội dung gói theo loại:
  - `db`: `database.dump` (`pg_dump -Fc --snapshot=<id>`, cả `public` và `ops`).
  - `app`: `source.bundle` (`git bundle create … HEAD`), `env` (`.env` bỏ dòng `SHOPONLINE_BACKUP_PASSWORD`), `config/`, `data/` (thư mục dữ liệu trừ `robot-work`, `backup-work`, `logs`). <!-- Updated: Validation Session 1 - không chép log -->
  - `full`: cả hai. Thiếu `git` hoặc `.git` hỏng chỉ ghi cảnh báo vào manifest, không làm hỏng phần `db`.
- Create: `src/shoponline/backup/retention.py` — `db` và `app`: giữ đúng N bản mới nhất (`keep_db`, `keep_app`); `full` (mọi nguồn, kể cả `safety`, `migration`): xóa bản có thời điểm trong tên cũ hơn `full_max_days` ngày, không giới hạn số bản trong 30 ngày đó. Không có bản nào được miễn — kể cả bản `full` duy nhất cũng bị xóa khi quá 30 ngày (chủ dự án chốt); phase 4 cảnh báo khi thiếu bản `full` mới. không có quy tắc nào khác (bản bị xóa tay vẫn được bảo vệ ở phase 5, không phải ở đây).
- Create: `src/shoponline/backup/schedule.py` — `is_due(kind, now, settings, last_success)`, chạy bù một lần khi máy tắt qua giờ, giờ Asia/Saigon (`clock.py`).
- Create: `src/shoponline/backup/runner.py` — xem bước 7.
- Modify: `src/shoponline/config.py` — `backup_password`, `backup_dirs`, `restore_database_url` là tùy chọn (không thêm vào `REQUIRED_VARS`, để web vẫn chạy trên máy chưa đặt).
- Modify: `src/shoponline/cli.py` — nhóm `backup`: `run [--kind] [--reason] [--if-due] [--no-drive] [--pg-bin] [--seven-zip]`, `verify <file|run_id>`, `process-queue`.
- Modify: `scripts/windows/backup-db.ps1` — wrapper `uv run --no-dev --extra robot shoponline backup run --kind db --reason deploy --pg-bin $PgBin --seven-zip $SevenZip`, chuyển mã thoát.
- Modify: `scripts/windows/register-tasks.ps1` — tác vụ `shoponline-backup` chạy `uv run --no-dev --extra robot shoponline backup run --if-due` với trigger lặp 15 phút, giới hạn 3 giờ; ngoại lệ hẹp cho `-OnlyMissing`: chỉ với `shoponline-backup`, trigger không phải lặp 15 phút thì thay trigger, không đụng tác vụ nào khác. `-BackupTime` vẫn nhận nhưng in cảnh báo "giờ sao lưu nay đặt trên trang Sao lưu". Sửa đoạn đầu file (dòng 17–19, 23) cho khớp.
- Modify: `scripts/windows/update-production.ps1` — sau bước sao lưu của chính nó, Disable và dừng `shoponline-backup` và `shoponline-restore` (đợi tiến trình Python của chúng thoát) trước `uv sync`, bật lại ở `Complete-Deploy`. Có hiệu lực từ deploy kế tiếp.
- Delete: `scripts/windows/backup-rotation.ps1` (không còn ai dot-source sau khi wrapper đổi).
- Create: `tests/backup/test_naming.py`, `test_retention.py`, `test_schedule.py`, `test_manifest.py`, `test_sevenzip.py`, `test_runner.py`, `test_staging.py`; `tests/db/test_ops_schema_migration.py`.

## Tasks & Steps

1. Migration `0010` + model + test: nâng từ `0009` chuyển `app_user` sang `ops` giữ nguyên dữ liệu; chạy lại `0010` khi `public.app_user` (cũ) và `ops.app_user` cùng tồn tại thì bỏ bảng `public`; đăng nhập web vẫn chạy (test web hiện có xanh).
2. `naming.py`, `retention.py`, `schedule.py` và test thuần (16 bản `db` giữ 15; loại khác không bị đụng; nhiều bản trong ngày vẫn chỉ giữ N; bản `full` 31 ngày tuổi bị xóa, 29 ngày được giữ, nhiều bản `full` bấm tay trong 30 ngày đều được giữ).
3. `staging.py` + test: thư mục rỗng sau exception ép buộc; `sweep_stale` xóa thư mục cũ.
4. `sevenzip.py` + test (bỏ qua khi máy không có 7z): gói không mã hóa bị `require_encrypted` từ chối; mục `..\x` bị chặn; mật khẩu không xuất hiện trong `caplog` và file log khi 7z lỗi.
5. `manifest.py` + `archive.py`: mở giao dịch `REPEATABLE READ`, `SELECT pg_export_snapshot()`, đếm dòng trong giao dịch đó, chạy `pg_dump --snapshot` khi giao dịch còn mở. `PGPASSWORD` chỉ trong env của tiến trình con.
6. Chạy thử ba loại trên máy dev, giải nén bằng 7-Zip tay, đối chiếu manifest.
7. `runner.py`, một hàm `run_backup(kind, reason, to_drive, conn=None)` dùng chung cho mọi đường:
   - Khóa: `pg_try_advisory_lock` cho lịch và bấm tay; `pg_advisory_lock` có `lock_timeout` 20 phút cho `deploy`, `migration`; `conn` truyền vào nghĩa là người gọi đã giữ khóa trên chính kết nối đó (bản an toàn của phase 3).
   - Khi lấy được khóa: mọi dòng `backup_run`/`backup_request` đang `running` từ trước được đánh `interrupted`.
   - Mã thoát: 0 (mọi nơi được yêu cầu nhận bản), 2 (một phần), 1 (không nơi nào), **3 (không lấy được khóa, không có bản nào)**. Drive "chưa kết nối" không tính là nơi lỗi.
   - `deploy`, `migration`, `safety`: chỉ tạo đúng bản được yêu cầu, không xử lý hàng đợi; `deploy` không lên Drive (chủ dự án chốt).
   - `--if-due`: xử lý `backup_request` đang chờ trước (phase 1 chỉ có `action=backup`), rồi lịch. Khi `db` và `full` cùng tới hạn (thứ Sáu 16:30) thì chạy lần lượt `db` rồi `full` trong cùng lần chạy, không bỏ loại nào.
   - Điểm nối Drive `upload_to_drive(run)` (phase 2 cắm vào; phase 1 trả "chưa kết nối").
   - Ghi `last-backup.txt` như cũ khi mọi nơi thành công (giữ cho tới khi phase 4 đổi banner).
8. CLI, wrapper, `register-tasks.ps1`, `update-production.ps1`.

## Verification

- `uv run pytest tests/backup tests/db -q` và `uv run pytest` toàn bộ (đăng nhập sau khi đổi schema).
- `uv run ruff check`
- `uv run shoponline backup run --kind full --no-drive`; `7z l` không mật khẩu thất bại; `env` không có `SHOPONLINE_BACKUP_PASSWORD`; dump có cả `ops` và `public` (`pg_restore -l`).
- `pwsh -File scripts\windows\backup-db.ps1; $LASTEXITCODE` trả 0 và tạo bản `db` nguồn `deploy`; khi một tiến trình khác giữ khóa quá 20 phút thì trả 3 và `update-production.ps1` dừng deploy (sửa điều kiện ở dòng 146: chỉ 0 hoặc 2 là tiếp tục — đã đúng).
- Hai lệnh `backup run` cùng lúc: chỉ một bản (tiêu chí 17).
- Trên máy có tác vụ cũ hằng ngày: `register-tasks.ps1 -AtLogOn -OnlyMissing` đổi trigger `shoponline-backup` sang lặp 15 phút, trigger web/retention/robot không đổi.

## Risks

- Đổi schema `app_user` chạm đăng nhập: test web toàn bộ phải xanh; migration idempotent đã test hai chiều.
- Wrapper hỏng làm deploy dừng ở bước sao lưu: thử wrapper trên máy dev trước khi push.
- 7z không đọc mật khẩu từ stdin: đường dự phòng `-p` với argv được che đã nằm trong bước 4.

## Rollback

Roll-forward, không downgrade: deploy chỉ chạy `migrate` lên (update-production.ps1:149) và từ chối commit cũ (:137-138). Muốn lùi tính năng: revert mã ứng dụng nhưng **giữ** file migration `0010` và model `ops.app_user`; các bảng `ops` khác không ảnh hưởng mã cũ. `backup-db.ps1` cũ lấy lại từ git cùng `backup-rotation.ps1`, và chạy `register-tasks.ps1` **không** có `-OnlyMissing` để trả trigger hằng ngày.
