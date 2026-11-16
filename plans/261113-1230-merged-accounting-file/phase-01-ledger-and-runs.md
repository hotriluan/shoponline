# Phase 1: Sổ DO, đợt xuất, retention và lưu file

## Bối cảnh

Chưa có chỗ nào ghi "DO này đã gửi kế toán". Migration mới nhất là `0005_sap_settings`; mẫu: [0004_sap_job.py](../../migrations/versions/0004_sap_job.py). Models: [models.py](../../src/shoponline/db/models.py). Retention coi `DELIVERED` là "đã có file kế toán" ([retention.py:6-9, 27-28](../../src/shoponline/maintenance/retention.py)) và xóa mọi file trong `exports/` và `uploads/` quá hạn theo giờ sửa. `save_generated` ([uploads.py:58](../../src/shoponline/web/uploads.py)) trả về `Path`, đặt tên theo giây và ghi đĩa trước khi commit. Test dùng một database dựng một lần cho cả phiên ([conftest.py:23-57](../../tests/conftest.py)).

## Yêu cầu

**Bảng mới (migration `0006_accounting_runs`):**

- `accounting_run`: `id`, `status` (`OPEN`, `FINALIZED`, `CANCELLED`, `REVOKED`, ràng buộc CHECK có đủ bốn giá trị ngay từ đầu), `created_by`, `created_at`, `finalized_by`, `finalized_at`, `missing_note` (cặp đã chốt thiếu và đơn chưa có DO đã được xác nhận), `generated_file_id` (FK `generated_file`, null tới khi chốt). Tối đa một dòng `OPEN` (chỉ mục unique có điều kiện, như `uq_sap_job_active_key`).
- `accounting_run_read`: `id`, `run_id`, `platform`, `gi_date`, `sap_job_id` (FK `sap_job`, null khi không có việc). Unique `(run_id, platform, gi_date)`.
- `accounting_run_source`: `run_id`, `import_batch_id`: các file `zrsd004` tải lên và gắn vào đợt.
- `accounting_sent_delivery`: `delivery` (khóa chính), `run_id` (null cho dòng nền), `sent_at`.
- `accounting_baseline`: một dòng duy nhất (`id = 1`), cột `cutoff_date`. DO có ngày goods issue thực ≤ `cutoff_date` coi như đã gửi.

**Dữ liệu nền.** Hàm thuần `seed_baseline(connection)` (để test được trên fixture `db`), được `upgrade()` gọi:

- đặt `cutoff_date` bằng ngày chạy migration;
- thêm vào sổ mọi `sales_order.do_number` khác null của đơn `DELIVERED`.

**Retention** ([retention.py](../../src/shoponline/maintenance/retention.py)):

- giữ `customer_info` của đơn cho tới khi DO của đơn có trong `accounting_sent_delivery` (thay cho điều kiện trạng thái `DELIVERED`/`CANCELLED`; đơn `CANCELLED` vẫn được xóa như cũ);
- không xóa file `generated_file` được `accounting_run.generated_file_id` trỏ tới, và file nguồn của đợt `OPEN`;
- cập nhật docstring và `FINISHED_STATUSES`.

**`save_generated`** ([uploads.py](../../src/shoponline/web/uploads.py)): flush và trả về dòng `GeneratedFile` (không phải `Path`); tên file dưới `export_dir` thêm hậu tố ngẫu nhiên để hai lần gọi cùng giây không ghi đè nhau; sửa hai nơi gọi hiện có ([batches.py:127](../../src/shoponline/web/routes/batches.py), [sap_reports.py:112](../../src/shoponline/web/routes/sap_reports.py)).

**CLI** (theo mẫu phẳng của [cli.py](../../src/shoponline/cli.py), người chạy lấy từ `getpass.getuser()`; lỗi từ chối dùng `ValueError` để ánh xạ ra mã thoát 2):

- `accounting-ledger list`: in các DO nền kèm sàn, mã đơn và mốc ngày hiện tại.
- `accounting-ledger add <delivery>...`: thêm DO vào sổ nền (`run_id` null).
- `accounting-ledger remove <delivery>...`: gỡ DO nền, từ chối DO thuộc một đợt.
- `accounting-ledger cutoff [--set YYYY-MM-DD]`: xem hoặc đổi mốc ngày.
- `accounting-run revoke <run_id> [--yes]`: chỉ nhận đợt `FINALIZED`; không có `--yes` thì chỉ in số DO sẽ gỡ. Với `--yes`: xóa mọi DO của đợt khỏi sổ, đặt đợt về `REVOKED`, ghi sự kiện `accounting_run_revoked`. File đã lưu giữ nguyên. Phần logic nằm ở hàm `revoke_run` trong `src/shoponline/accounting/ledger.py` (phase này) để web, phase 4 và CLI dùng chung; CLI chỉ gọi hàm đó. <!-- Updated: Validation Session 1 - revoke_run lives in phase 1 -->

**Thông báo của `retention` trên CLI** ([cli.py:184](../../src/shoponline/cli.py)) đang ghi "Giữ lại vì đơn chưa có file gửi kế toán"; đổi thành "chưa có DO trong sổ gửi kế toán" cho khớp điều kiện mới. <!-- Updated: Validation Session 1 - stale CLI message found in verification -->

**Giờ Việt Nam:** hàm `today_vn()` (theo `Asia/Saigon`) đặt ở `src/shoponline/clock.py` và có test; phase 4 và các route dùng chung hàm này. <!-- Updated: Validation Session 1 - no existing helper -->

Test cho phase này (`seed_baseline`, ràng buộc, retention) và `today_vn()` nằm ở `tests/`; thư mục `tests/accounting/` do phase này tạo.

Mọi lệnh ghi sổ ghi một sự kiện vào nhật ký.

## Tệp được sửa

- `migrations/versions/0006_accounting_runs.py` (mới)
- `src/shoponline/db/models.py`
- `src/shoponline/cli.py`
- `src/shoponline/accounting/__init__.py`, `src/shoponline/accounting/ledger.py` (mới: `revoke_run` và các hàm sổ nền), `src/shoponline/clock.py` (mới: `today_vn`), `tests/accounting/` (mới)
- `src/shoponline/maintenance/retention.py`, `tests/maintenance/test_retention.py`
- `src/shoponline/web/uploads.py`, `src/shoponline/web/routes/batches.py` và `sap_reports.py` (chỉ phần gọi `save_generated`)
- `tests/db/` (test ràng buộc và `seed_baseline`), `tests/test_cli*.py` hoặc file test CLI hiện có

## Các bước

1. Viết test trước cho: ràng buộc bảng, `seed_baseline` trên fixture `db`, retention mới, `save_generated`, các lệnh CLI.
2. Thêm model, migration (`downgrade` xóa năm bảng theo thứ tự khóa ngoại).
3. Sửa retention, `save_generated` và hai nơi gọi.
4. Viết `accounting/ledger.py` (sổ nền và `revoke_run`) và `clock.py`, rồi khai báo các lệnh CLI gọi chúng. Phase 4 chỉ import `revoke_run` từ `ledger.py`; phase 1 không phụ thuộc phase nào.
5. Sao lưu database trước khi chạy migration ở máy thật (ghi trong phase 6).

## Kiểm tra

- Ràng buộc: đợt `OPEN` thứ hai bị từ chối; `(run, sàn, ngày)` trùng bị từ chối; trạng thái ngoài bốn giá trị bị từ chối.
- `seed_baseline` trên fixture `db`: đơn `DELIVERED` có và không có `do_number`, mốc ngày đặt đúng.
- Vòng `downgrade 0005_sap_settings` rồi `upgrade head` chạy trên chính database `*_test` ở cuối phiên test (sau mọi test khác, không dùng fixture `db`), hoặc ghi rõ là chạy tay; không tạo database riêng. <!-- Updated: Validation Session 1 - same _test database -->
- `today_vn()`: trả về ngày theo `Asia/Saigon` khi giờ UTC đã sang ngày mới nhưng giờ Việt Nam chưa (và ngược lại).
- Retention: tên khách của đơn có DO chưa vào sổ vẫn được giữ quá hạn; đã vào sổ thì xóa theo tuổi; file `generated_file` của đợt và file nguồn đợt `OPEN` không bị xóa.
- `save_generated`: hai lần gọi cùng giây cho hai đường dẫn khác nhau; trả về dòng có `id`.
- CLI: `remove` từ chối DO của đợt; `revoke` không `--yes` không đổi gì; `--yes` chỉ gỡ DO của đúng đợt; từ chối đợt không `FINALIZED`; mọi lệnh ghi nhật ký với người chạy.

## Rủi ro và hoàn tác

- Sổ nền và mốc ngày có thể bỏ nhầm DO chưa từng gửi; phase 6 buộc chủ dự án duyệt.
- Hoàn tác: `alembic downgrade 0005_sap_settings`, khôi phục bản sao lưu nếu cần.
