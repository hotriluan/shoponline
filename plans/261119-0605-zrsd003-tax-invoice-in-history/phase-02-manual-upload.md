---
phase: 2
title: "Ô upload tay zrsd003"
status: completed
priority: P2
effort: "2h"
dependencies: [1]
---

# Phase 2: Ô upload tay zrsd003

## Goal
Admin tải file zrsd003 xuất tay từ SAP lên trang Báo cáo SAP khi robot hỏng; kết quả giống hệt robot.

## Files to Create / Modify
- Modify: `src/shoponline/web/routes/sap_reports.py` — route `POST /sap-reports/zrsd003`; thêm `zrsd003` vào danh sách kind của `_page`.
- Modify: `src/shoponline/web/templates/sap_reports.html` — form thứ ba "zrsd003 – số hóa đơn (Tax Invoice)".
- Modify: `tests/web/test_uploads.py` (hoặc test route Báo cáo SAP hiện có).

## Tasks & Steps
1. Route theo khuôn `upload_zrsd004` (`sap_reports.py:74`): `require_admin`, `save_upload(kind="zrsd003")`, `ingest_zrsd003`; lỗi `UploadRejected`/`FileRejected` thì rollback, `discard_unused` file mới, hiện lỗi.
2. Sau commit gọi `retention.discard_unused(db, settings, [record.stored_path])` — file gốc chứa dữ liệu khách doanh nghiệp, không giữ. Đã kiểm: `waiting_uploads` (`accounting/runs.py:347`) chỉ lấy kind `zrsd004`, nên `kept_files` không giữ file zrsd003.
3. Thông báo kết quả: "zrsd003: N hóa đơn của sàn (M mới, K cập nhật), bỏ qua X dòng khách khác." rồi quay lại `/sap-reports`.
4. Ghi chú dưới form: hóa đơn xuất sau DO; chọn Sales Org 1000, Sales Office 1401, Billing Date bao trùm các đơn đang chờ.
5. Test: admin tải file → hóa đơn có trong DB, file không còn trên đĩa; viewer bị từ chối; file sai cột hiện lỗi và không ghi gì.

## Verification
- `uv run pytest tests/web -q -k "sap_report or upload"`
