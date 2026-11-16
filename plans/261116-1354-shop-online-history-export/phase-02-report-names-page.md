---
phase: 2
title: "Trang sửa tên báo cáo"
status: completed
priority: P2
effort: "3h"
dependencies: [1]
---

# Phase 2: Trang sửa tên báo cáo

## Goal
Admin xem và sửa itemName, kích cỡ, variation cho mọi mã vật tư đang có trong ánh xạ SAP, với giá trị gợi ý điền sẵn cho mã chưa có tên.

## Bối cảnh
- Mẫu trang có lưu hàng loạt, giữ giá trị đã nhập khi lỗi: [sku_mapping.py](../../src/shoponline/web/routes/sku_mapping.py) (`save_unmapped`) và [sku_mappings.html](../../src/shoponline/web/templates/sku_mappings.html).
- Router được nạp ở [app.py:221](../../src/shoponline/web/app.py); menu ở [base.html:45-54](../../src/shoponline/web/templates/base.html).
- Quyền: `require_admin` cho thao tác ghi, `current_user` cho xem.

## Files to Create / Modify
- Create: `src/shoponline/web/routes/report_names.py`.
- Create: `src/shoponline/web/templates/report_names.html`.
- Modify: `src/shoponline/web/app.py`: nạp router mới (theo cách các router khác được nạp).
- Modify: `src/shoponline/web/templates/base.html`: thêm mục menu "Tên báo cáo".
- Create: `tests/web/test_report_names_routes.py`.

## Tasks & Steps
1. `GET /report-names`: danh sách mã vật tư khác nhau trong `sku_mapping` (kèm `sap_name`), nối trái với `report_item_name`. Mã chưa có tên báo cáo lên đầu, ô nhập điền sẵn bằng `suggest_report_name` (phase 1) và đánh dấu "gợi ý, chưa lưu". Tham số `missing=true` chỉ hiện mã chưa có tên.
2. `POST /report-names` (admin): nhận ba cột cho mỗi mã như `save_unmapped`. Lưu các dòng có đủ ba ô; dòng thiếu một ô thì báo đỏ. Có dòng lỗi thì không lưu gì, trả lại trang với giá trị đã nhập. Ghi `updated_by`. Ghi một sự kiện `report_names_saved` vào `event_log` với số dòng đổi (không ghi tên khách, không có dữ liệu cá nhân).
3. Dòng không đổi thì không cập nhật `updated_at`.
4. Test: viewer xem được trang; viewer POST bị chuyển hướng và không dòng nào đổi; admin lưu được; một dòng thiếu ô làm cả lần lưu bị từ chối và giá trị đã nhập còn nguyên; mã chưa có tên hiện gợi ý.

## Verification
- `uv run pytest tests/web/test_report_names_routes.py`
- `uv run pytest tests/web` (menu đổi không làm vỡ test trang khác)
- `uv run ruff check src tests`

## Risk & Rollback
- Trang chỉ đọc `sku_mapping`, không ghi; lùi lại bằng cách gỡ router và mục menu.
