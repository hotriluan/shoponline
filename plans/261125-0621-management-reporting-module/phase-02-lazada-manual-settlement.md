---
phase: 2
title: "Nhập tay tiền về Lazada"
status: completed
priority: P1
effort: "6h"
dependencies: []
---

# Phase 2: Nhập tay tiền về Lazada

## Goal

Admin nhập số tiền Lazada đã chuyển về cho từng đơn. Số này đi vào cùng bảng `platform_settlement` mà Shopee và TikTok đang dùng, nên cột "Tiền Vô" của file lịch sử và đường tiền thực nhận của báo cáo tự nhận.

## Bối cảnh

- File Balance Transactions của Lazada không có mã đơn, nên [settlement_files.py](../../src/shoponline/importers/settlement_files.py) từ chối nó. Chủ dự án xác nhận không có nguồn file nào khác.
- `platform_settlement`: khóa duy nhất `(platform, line_key)`; `import_batch_id` NOT NULL. Không thể tạo `import_batch` giả với `stored_path` rỗng, vì `foreign_paths` của lượt dọn file sẽ coi đó là đường dẫn lạ và từ chối chạy.
- [sales_history_workbook.py](../../src/shoponline/exports/sales_history_workbook.py) hiện để trống "Tiền Vô" với Lazada (`SETTLEMENT` chỉ áp cho Shopee/TikTok) và không chặn đơn Lazada khi thiếu tiền.

## Thiết kế

- **Migration `0013_manual_settlement`:** `platform_settlement.import_batch_id` cho phép NULL; thêm cột `source` (`file` | `manual`, mặc định `file`), `entered_by` (String 50, NULL). Có CHECK: `source='file'` thì phải có `import_batch_id`; `source='manual'` thì phải có `entered_by`.
- **Một dòng nhập tay cho mỗi đơn:** `line_key = 'manual'`, kết hợp khóa `(platform, line_key)` thì không đủ. Vì vậy dùng `line_key = 'manual:' || platform_order_id`. Sửa là cập nhật dòng đó; xóa là xóa dòng đó.
- **Mã:** `src/shoponline/accounting/manual_settlement.py` gồm `pending_orders(session, month)`, `set_amount(session, order_id, amount, settled_on, actor)`, `remove(session, order_id, actor)`, `parse_paste(text)` (mỗi dòng `mã đơn<TAB>số tiền<TAB>ngày dd/mm/yyyy`). Mọi thay đổi ghi `event_log` kind `settlement_manual_set` / `settlement_manual_removed` kèm số cũ và số mới.
- **Kiểm tra dữ liệu:** đơn phải là `LAZADA` và có trong `sales_order`; số tiền là số nguyên ≥ 0 (cho nhập 0 khi sàn giữ lại toàn bộ tiền); ngày không ở tương lai và không trước ngày đặt đơn. Dán nhiều dòng: dòng sai bị liệt kê với lý do, dòng đúng vẫn được lưu chỉ khi admin bấm xác nhận sau khi xem trước.
- **Trang `/settlements/lazada`** (nhóm menu "Kế toán", nhãn "Tiền về Lazada"):
  - Danh sách đơn Lazada đã có DO mà chưa có tiền về, lọc theo tháng đặt đơn, ô nhập số tiền và ngày nhận ở từng dòng.
  - Khung dán nhiều dòng, có bước xem trước rồi mới lưu.
  - Bảng các đơn đã nhập, sửa và xóa được.
  - Viewer xem được, chỉ admin sửa (theo cách `admin_required` các route khác đang làm).
- **File lịch sử Shop Online:** cột "Tiền Vô" có số khi đã nhập tay. **Không** chặn đơn Lazada thiếu tiền như Shopee/TikTok, để file kế toán không phụ thuộc việc nhập tay; hộp "Đơn chờ tiền vô" không tính Lazada.
- **Tách hằng `SETTLED_PLATFORMS`** <!-- Updated: Validation Session 1 - hằng đang dùng cho cả tra tiền lẫn chặn, và order_progress.py cũng dùng --> (hiện là `("SHOPEE", "TIKTOK")`, 5 chỗ trong `sales_history_workbook.py` dòng 88, 211, 221, 262, 340 và 3 chỗ trong `reconcile/order_progress.py` dòng 14, 45, 56) thành hai hằng trong `sales_history_workbook.py`:
  - `SETTLEMENT_LOOKUP_PLATFORMS = ("SHOPEE", "TIKTOK", "LAZADA")`: sàn để tra tiền về. Dùng ở dòng 211, 221 và trong `order_progress.py`, nên chip "tiền về" của đơn Lazada hiện số đã nhập.
  - `SETTLEMENT_REQUIRED_PLATFORMS = ("SHOPEE", "TIKTOK")`: sàn bị chặn khi thiếu tiền. Dùng ở dòng 262 và 340.
  - Sửa docstring của `order_progress`, không còn nói `paid` luôn rỗng với Lazada.

## Files to Create / Modify

- Create: `migrations/versions/0013_manual_settlement.py`
- Modify: `src/shoponline/db/models.py` (`PlatformSettlement`)
- Create: `src/shoponline/accounting/manual_settlement.py`
- Create: `src/shoponline/web/routes/settlements.py`, `src/shoponline/web/templates/lazada_settlements.html`
- Modify: `src/shoponline/web/app.py` (gắn router), `src/shoponline/web/templates/_nav.html`
- Modify: `src/shoponline/exports/sales_history_workbook.py` (tách hai hằng, tiền vô Lazada, không chặn)
- Modify: `src/shoponline/reconcile/order_progress.py` (dùng hằng tra tiền; người gọi duy nhất là `src/shoponline/web/routes/batches.py`)
- Create: `tests/accounting/test_manual_settlement.py`, `tests/web/test_lazada_settlements.py`
- Modify: `tests/exports/test_sales_history_workbook.py`: thêm trường hợp Lazada có và chưa có tiền (chưa có tiền thì đơn vẫn vào file, không bị chặn).
- Modify: `tests/web/test_batch_progress.py`: chip tiền về của đơn Lazada hiện số đã nhập.

## Tasks & Steps

- [x] Migration và model; test migration chạy lên được trên database test.
- [x] Module `manual_settlement` với kiểm tra dữ liệu và `event_log`.
- [x] Route, template, menu.
- [x] Tách `SETTLED_PLATFORMS` thành hai hằng và sửa `order_progress.py`; sửa file lịch sử.
- [x] Test: đặt, sửa, xóa, dán nhiều dòng có dòng lỗi, quyền viewer, số tiền hiện ở cột "Tiền Vô".

## Verification

- `uv run pytest tests/accounting/test_manual_settlement.py tests/web/test_lazada_settlements.py tests/exports`
- `uv run alembic upgrade head` trên database dev (sau khi sao lưu).

## Risk

- `ingest_settlement` ([report_ingest.py:167](../../src/shoponline/reconcile/report_ingest.py)) chỉ upsert theo `(platform, line_key)` và không xóa dòng nào, nên không đụng dòng nhập tay (đã kiểm). Thêm một test giữ điều đó: nạp file Shopee/TikTok không đổi dòng `manual:`.
- Cột `import_batch_id` cho phép NULL: các chỗ đọc `platform_settlement.import_batch_id` phải chịu được NULL. Hiện không có chỗ nào ngoài `ingest_settlement` ghi cột này.

## Kết quả (2026-11-25)

Đã làm: migration `0013_manual_settlement`; model `PlatformSettlement` (cột `source`, `entered_by`, `import_batch_id` NULL, CHECK); `accounting/manual_settlement.py`; route `web/routes/settlements.py` và `lazada_settlements.html` (nhập từng đơn, dán nhiều dòng có xem trước, sửa, xóa; viewer chỉ xem); menu "Tiền về Lazada"; tách hằng thành `SETTLEMENT_LOOKUP_PLATFORMS` và `SETTLEMENT_REQUIRED_PLATFORMS`; test `tests/accounting/test_manual_settlement.py`, `tests/web/test_lazada_settlements.py`, thêm ca Lazada vào `test_sales_history_workbook.py` và `test_batch_progress.py`. Chưa chạy `alembic upgrade head` trên database dev (cần đọc `.env`, bị hook bảo mật chặn chờ chủ dự án đồng ý).
