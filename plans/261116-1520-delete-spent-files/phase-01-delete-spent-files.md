---
phase: 1
title: "Xóa file trong code và test"
status: completed
---

# Phase 01: Xóa file trong code và test

## Files

- Sửa: [src/shoponline/saprobot/worker.py](../../src/shoponline/saprobot/worker.py) (`Worker._finish`)
- Sửa: [src/shoponline/web/routes/batches.py](../../src/shoponline/web/routes/batches.py) (`download_order_file`)
- Test: [tests/saprobot/test_worker.py](../../tests/saprobot/test_worker.py), [tests/web/test_web_flow.py](../../tests/web/test_web_flow.py)

## Steps

1. **Robot.** Trong `_finish`, sau `db.commit()`: nếu `outcome.status == queue.DONE` (vẫn `DONE` sau phần nhập kết quả) thì `shutil.rmtree(self.settings.robot_work_dir / f"job-{job_id}")` trong `try/except OSError`; lỗi chỉ `log.warning`. Việc khác `DONE` thì không xóa. `_run_check` không tạo file nên không đổi.
2. **File đơn hàng.** Trả `FileResponse(..., background=BackgroundTask(_discard, path))`, trong đó `_discard` gọi `Path.unlink(missing_ok=True)` và bắt `OSError` để ghi log. Starlette chạy background task sau khi gửi xong body.
3. **Test robot:** job đọc báo cáo `DONE` thì thư mục `job-N` không còn và file vẫn có trong `uploads/`; job lỗi (`FAILED` từ fake SAP, và trường hợp hàm nhập kết quả ném lỗi) thì thư mục còn nguyên.
4. **Test web:** sau `GET /batches/{id}/order-file`, response có nội dung xlsx hợp lệ, bản ghi `GeneratedFile` tồn tại, file ở `stored_path` không còn.

## Validation

```
uv run pytest tests/saprobot/test_worker.py tests/web/test_web_flow.py
uv run pytest tests/saprobot tests/web tests/maintenance
uv run ruff check
```

## Risk và rollback

- SAP GUI còn giữ file (khóa trên Windows) lúc xóa: `rmtree` lỗi, ghi log, lượt quét đêm (phase 03) dọn sau. Không làm hỏng việc.
- Rollback: revert commit; không có migration.
