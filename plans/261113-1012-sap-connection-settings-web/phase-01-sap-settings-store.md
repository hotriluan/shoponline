---
phase: 1
title: "Bảng cấu hình SAP và heartbeat"
status: completed
effort: 1d
---

# Phase 1: Bảng cấu hình SAP và heartbeat

## Bối cảnh

- [config.py](../../src/shoponline/config.py): `Settings.sap_target`, `robot_max_failures`, `evidence_keep_days` đọc từ môi trường một lần lúc khởi động.
- Nơi dùng `sap_target`: [app.py:83,103](../../src/shoponline/web/app.py), [batches.py:158,181](../../src/shoponline/web/routes/batches.py), [robot.py:34](../../src/shoponline/web/routes/robot.py), [cli.py:108-114](../../src/shoponline/cli.py).
- `RobotControl` một dòng (id=1) trong [models.py](../../src/shoponline/db/models.py); migration mới nhất `0004_sap_job.py`.

## Yêu cầu

1. Migration `0005_sap_settings.py`:
   - Bảng `sap_settings` một dòng (id=1): `system`, `client`, `connection`, `sap_user`, `language`, `max_failures`, `evidence_keep_days`, `verified_system`, `verified_client`, `verified_at`, `changed_by`, `changed_at`. Mọi cột cấu hình cho phép NULL.
   - Thêm vào `robot_control`: `last_seen_at`, `saplogon_entries` (Text, JSON danh sách tên), `password_present` (bool, NULL = chưa biết), `robot_host` (tên máy).
   - Trước khi chạy migration trên máy thật: sao lưu database (`scripts/windows/backup-db.ps1`). `update-production.ps1` đã sao lưu trước `migrate`.
2. Module mới `src/shoponline/sapjobs/sap_settings.py`:
   - `SapSettings` (dataclass) với `target -> SapTarget | None` và `target_verified -> bool` (đúng khi `verified_system/client` bằng `system/client`).
   - `load(db, env) -> SapSettings`: lấy dòng DB; trường NULL lấy từ biến môi trường như hiện nay (`SHOPONLINE_SAP_*`, `SHOPONLINE_ROBOT_*`). Giữ kiểm tra "đặt cả SYSTEM và CLIENT hoặc bỏ cả hai".
   - **Tương thích máy đang chạy:** lần `load` đầu tiên khi dòng chưa có, tạo dòng từ biến môi trường; nếu môi trường có SYSTEM/CLIENT thì coi là đã kiểm tra (`verified_* = system/client`, `changed_by='env'`), để robot đang chạy không bị khóa sau deploy.
   - `save(db, actor, **fields)`: kiểm tra dữ liệu (system 3 ký tự chữ/số viết hoa; client 3 chữ số; user không rỗng khi có system; language rỗng hoặc 2 chữ cái; hai số nguyên dương). Ghi `states.log_event(db, actor, "sap_settings_changed", detail={trường: [cũ, mới]})`. Đổi system hoặc client thì xóa `verified_*`.
   - `mark_verified(db, system, client)`: chỉ ghi khi khớp cấu hình hiện tại.
   - `robot_alive(control, now, stale=30s) -> bool`.
3. Bỏ `sap_target`, `robot_max_failures`, `evidence_keep_days` khỏi `Settings`; mọi nơi dùng chuyển sang `sap_settings.load(db, env)`. Web giữ `env` đã nạp ở `app.state` để dùng làm giá trị dự phòng.

## Files

- Tạo: `migrations/versions/0005_sap_settings.py`, `src/shoponline/sapjobs/sap_settings.py`, `tests/sapjobs/test_sap_settings.py`
- Sửa: `src/shoponline/db/models.py`, `src/shoponline/config.py`, `src/shoponline/web/app.py`, `src/shoponline/web/routes/batches.py`, `src/shoponline/web/routes/robot.py`, `tests/test_config.py`

## Các bước

1. Viết test cho `load`/`save`/`mark_verified`/`robot_alive`: giá trị dự phòng từ env, tạo dòng lần đầu, kiểm tra dữ liệu, đổi system xóa xác nhận, ghi nhật ký sự kiện.
2. Model và migration; chạy `uv run shoponline migrate` trên database dev và test.
3. Viết module, chuyển các nơi dùng `settings.sap_target`.

## Kiểm tra

- `uv run pytest tests/sapjobs tests/test_config.py tests/web`
- `uv run alembic downgrade -1 && uv run alembic upgrade head` trên database test.

## Rủi ro và lùi lại

- Mã cũ đọc `Settings.sap_target` mà sót: `ruff` và `pytest` bắt được lỗi thuộc tính.
- Lùi: `alembic downgrade` xóa bảng và cột mới; biến môi trường vẫn còn nên hệ thống chạy như cũ.
