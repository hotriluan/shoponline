---
phase: 2
title: "Xóa file trong uploads khi hết dùng"
status: completed
---

# Phase 02: Xóa file trong uploads khi hết dùng

Quyết định của chủ dự án (2026-11-16): không cần giữ file gốc của sàn và zrsd001 làm bằng chứng.

## Quy tắc giữ

Một file trong `uploads/` chỉ được giữ khi có một `ImportBatch` trỏ tới nó và thuộc một trong hai trường hợp:

- là nguồn (`AccountingRunSource`) hoặc file robot đọc (`AccountingRunRead` → `SapJob.import_batch_id`) của một đợt `OPEN`; hoặc
- là zrsd004 upload tay chưa thuộc đợt `OPEN`/`FINALIZED` (đang nằm trong danh sách chờ gắn của `available_uploads`, [runs.py:327-352](../../src/shoponline/accounting/runs.py#L327-L352)).

Mọi file khác trong `uploads/` là hết dùng. File được đặt tên theo nội dung nên nhiều `ImportBatch` có thể trỏ cùng một file; luôn kiểm tra theo đường dẫn.

## Files

- Sửa: [src/shoponline/maintenance/retention.py](../../src/shoponline/maintenance/retention.py): thêm `discard_unused_uploads(session, paths)` dùng chung truy vấn với `_kept_files` (không chép lại truy vấn).
- Gọi sau `db.commit()` ở: [imports.py](../../src/shoponline/web/routes/imports.py) `import_file`, [sku_mapping.py](../../src/shoponline/web/routes/sku_mapping.py) `import_mappings`, [sap_reports.py](../../src/shoponline/web/routes/sap_reports.py) `upload_zrsd001` / `upload_zrsd004`, [worker.py](../../src/shoponline/saprobot/worker.py) `_finish` (cùng chỗ xóa `robot-work` ở phase 01), [accounting.py](../../src/shoponline/web/routes/accounting.py) `finalize_run` / `cancel_run` (các file nguồn và file đọc của đợt).
- Sửa: [uploads.py](../../src/shoponline/web/uploads.py) `store_file` cho biết file có vừa được tạo không, để nhánh bị từ chối chỉ xóa file mới tạo lần này.
- Test: `tests/maintenance/test_retention.py`, `tests/web/test_web_flow.py`, `tests/saprobot/test_worker.py`, `tests/accounting/test_runs.py`.

## Steps

1. Viết `discard_unused_uploads`: với mỗi đường dẫn, bỏ qua nếu nằm trong tập giữ; ngược lại `unlink(missing_ok=True)`, bắt `OSError` và ghi log.
2. Gọi hàm ở từng điểm trên, sau khi commit.
3. Nhánh từ chối (`UploadRejected`/`FileRejected`): xóa file nếu `store_file` vừa tạo nó.
4. Test: mỗi điểm gọi xóa đúng file; zrsd004 upload tay chưa gắn còn nguyên; đợt `OPEN` còn file; hai lần nhập cùng nội dung, một đợt chốt và một đợt còn mở, thì file còn; file bị từ chối mà đã có từ trước thì còn.

## Validation

```
uv run pytest tests/maintenance tests/web tests/saprobot tests/accounting
uv run ruff check
```

## Risk và rollback

- Đợt đã chốt bị gỡ (revoke): file zrsd004 upload tay của đợt đó đã bị xóa; admin upload lại khi làm đợt mới. File kế toán đã chốt trong `exports/` vẫn còn.
- Rollback: revert commit; không có migration. File đã xóa không lấy lại được (khôi phục từ sao lưu nếu có).
