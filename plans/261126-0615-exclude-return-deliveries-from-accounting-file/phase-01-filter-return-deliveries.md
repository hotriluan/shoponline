---
title: "Phase 1: Lọc phiếu không phải giao bán"
status: completed
priority: P1
effort: "2h"
dependencies: []
---

# Phase 1: Lọc phiếu không phải giao bán

## Overview

Chỉ giữ dòng `Delivery Type = ZDA1` trong file gộp gửi kế toán, và không điền hay cảnh báo thông tin khách cho dòng loại khác trong bản xem trước một file.

## Context

- Bộ lọc dòng của file gộp: `build_merged_accounting_workbook` tại `src/shoponline/exports/accounting_workbook.py:402-425`. Thứ tự kiểm tra hiện tại: khách ngoài sàn → chưa có ngày GI → trạng thái khác C → trước mốc → đã gửi.
- Cảnh báo "thiếu mã đơn, tên khách, địa chỉ" sinh ở `_fill_customers` (`accounting_workbook.py:147-177`). Hàm này dùng chung cho bản xem trước một file (`build_accounting_workbook`, gọi từ `reconcile/report_ingest.py:62` khi robot đọc) và cho file gộp.
- Trang đợt đã hiện `dropped` theo lý do (`web/templates/accounting_run.html:128-131`); không cần sửa giao diện.
- `mark_delivered` (`reconcile/so_link.py:374`) chỉ cập nhật đơn có SO trong `sales_order`, nên SO của phiếu `ZDE1` không khớp gì; không cần sửa.
- Fixture `zrsd004_row` (`tests/fixtures/build_fixtures.py:498`) không đặt `Delivery Type`, nên ô này đang rỗng. Phải cho fixture mặc định `ZDA1` trước, nếu không mọi test hiện có sẽ bị lọc mất dòng.

## Requirements

- [x] Hằng `DELIVERY_TYPE_COLUMN = "Delivery Type"` và `SALES_DELIVERY_TYPES = ("ZDA1",)` cạnh `GOODS_ISSUED`, kèm chú thích: `ZDE1` là phiếu nhập hàng trả về vào kho QC `0301`.
- [x] Lý do bỏ dòng mới, ví dụ `NOT_SALES_DELIVERY = "không phải phiếu giao bán (phiếu nhập hàng trả về hoặc loại khác)"`. Không thêm vào `NOT_YET_ISSUED`.
- [x] File gộp: `Delivery Type` nằm trong `required`; kiểm tra loại phiếu ngay sau kiểm tra khách hàng, trước kiểm tra ngày GI và trạng thái.
- [x] `_fill_customers`: khi sheet có cột `Delivery Type`, dòng có loại phiếu không thuộc `SALES_DELIVERY_TYPES` được bỏ qua (không điền ba cột, không cảnh báo). Sheet không có cột này giữ hành vi cũ.
- [x] Bản xem trước một file vẫn giữ mọi dòng như SAP xuất (không xóa dòng).

## Implementation Steps

1. `tests/fixtures/build_fixtures.py`: thêm tham số keyword `delivery_type: str = "ZDA1"` cho `zrsd004_row` và ghi `"Delivery Type": delivery_type` vào dict.
2. Chạy `uv run pytest tests/exports tests/accounting tests/web/test_accounting_routes.py -q` để xác nhận fixture mới không đổi kết quả hiện có.
3. Viết test trước (cả hai file test):
   - `tests/exports/test_merged_accounting_workbook.py`:
     - `ZDA1` và `ZDE1` lẫn nhau: chỉ còn `ZDA1`; `dropped[mod.NOT_SALES_DELIVERY]` đúng số; dòng tổng chỉ cộng số lượng `ZDA1`; `deliveries` và `so_numbers` không có phiếu `ZDE1`.
     - Dòng `ZDE1` có `goods_status="A"` hoặc `gi_date=None`: bị đếm vào lý do mới, không nằm trong `skipped`.
     - Loại phiếu lạ (ví dụ `ZXX1`) cũng bị bỏ với cùng lý do.
     - File không có cột `Delivery Type`: `FileRejected` có nhắc tên cột. Tạo bằng cách xóa cột khỏi workbook fixture.
     - Chỉ có dòng `ZDE1`: `FileRejected("Không có DO mới")`.
   - `tests/exports/test_accounting_workbook.py`: file có một dòng `ZDA1` thiếu dữ liệu khách và một dòng `ZDE1` → cảnh báo chỉ nhắc SO của dòng `ZDA1`; dòng `ZDE1` vẫn còn trong sheet, ba cột chèn để trống.
4. Sửa `src/shoponline/exports/accounting_workbook.py` theo Requirements. Cập nhật docstring của `build_merged_accounting_workbook` (thêm điều kiện loại phiếu giao bán).
5. Chạy test hẹp, rồi toàn bộ.

## Todo

- [x] Fixture `zrsd004_row` có `delivery_type="ZDA1"`
- [x] Test file gộp: lọc `ZDE1`, dòng tổng, không vào `skipped`, loại lạ, thiếu cột, chỉ toàn `ZDE1`
- [x] Test bản xem trước một file: không cảnh báo `ZDE1`
- [x] Hằng số và lý do mới
- [x] Lọc trong `build_merged_accounting_workbook`
- [x] Bỏ qua dòng không phải giao bán trong `_fill_customers`
- [x] `uv run pytest` và `uv run ruff check .` sạch

## Verification

- `uv run pytest tests/exports -q`
- `uv run pytest -q`
- `uv run ruff check . && uv run ruff format --check .`

## Success Criteria

Mọi test mới và cũ qua. Dòng `ZDE1` không vào file gộp, không vào `skipped`, không sinh cảnh báo; dòng `ZDA1` thiếu dữ liệu vẫn được cảnh báo.

## Risks

- **SAP thêm một loại giao bán mới cho sàn:** dòng đó bị bỏ. Giảm rủi ro: lý do và số dòng hiện trên trang đợt, sửa bằng một hằng số. Năm file kế toán gần nhất trên máy chạy thật chỉ có `ZDA1`.
- **File tải tay cũ không có cột `Delivery Type`:** file gộp từ chối với thông báo rõ. Layout ZRSD004 trong `docs/zrsd004.XLSX` và mọi file robot đều có cột này.

## Rollback

Revert commit. Không có thay đổi dữ liệu hay schema.
