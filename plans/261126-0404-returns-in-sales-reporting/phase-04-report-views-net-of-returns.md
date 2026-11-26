---
phase: 4
title: "View báo cáo trừ hàng trả"
status: completed
priority: P1
effort: "0.5d"
dependencies: [1]
---

# Phase 4: View báo cáo trừ hàng trả

## Goal

Mọi trang báo cáo ra số ròng sau hàng trả, khớp với file Shop Online theo tháng đặt đơn; tỷ lệ trả tính trên cùng cơ sở có thuế.

## Context

- Hai view ở `migrations/versions/0016_report_views.py`. `report_sale_line` loại `CANCELLED` nhưng tính đủ đơn có phiếu trả. `report_order_revenue.returned_value` = tổng `amount_returned` (chưa thuế) trong khi `invoice_value` có thuế.
- `reports/queries.py` đếm đơn bằng `COUNT(DISTINCT order_key)`.

## Files to Create / Modify

- Create: `migrations/versions/0019_report_views_net_of_returns.py` (`CREATE OR REPLACE VIEW`; downgrade trả lại định nghĩa của 0016)
- Modify: `src/shoponline/reports/queries.py`
- Modify: `src/shoponline/web/routes/reports.py`, template báo cáo nếu đổi tên cột
- Modify: `tests/reports/test_report_views.py`, `tests/reports/test_queries.py`, `tests/web/test_reports.py`

## Tasks & Steps

1. Sao lưu database dev trước khi chạy migration.
2. `report_sale_line`: thêm `UNION ALL` nguồn `'return'` từ `sales_return_sale_line` của phiếu `ISSUED`, nối `sales_order_item` và `sales_order` như nhánh `system`; `period` và `ordered_on` theo ngày đặt đơn; `quantity` và `customer_paid` âm; `order_key` là id đơn. Cùng điều kiện ngày và loại `CANCELLED`.
3. Đếm đơn: một đơn được đếm khi tổng `quantity` của nó trong bộ lọc > 0. Đổi các chỗ `COUNT(DISTINCT order_key)` sang đếm trên nhóm theo `order_key` có `SUM(quantity) > 0`. Giá trị trung bình mỗi đơn dùng số đơn mới.
4. Các lọc `source = 'history'` / `'system'` trong `data_notes` không tính nhánh `'return'`.
5. `report_order_revenue`:
   - `marketplace_value` trừ tổng `customer_paid` của dòng trả;
   - `returned_value` = `returned_net + returned_tax` của phiếu `ISSUED` (cùng cơ sở với `invoice_value`);
   - thêm `returned_marketplace_value` (tổng `customer_paid` của dòng trả).
6. `queries.overview` và trang Trả hàng: tỷ lệ trả = `returned_value / invoice_value`. Trang Trả hàng hiện cả giá trị theo hóa đơn và theo giá sàn. Ghi rõ trên trang: "Giá trị trên sàn đã trừ hàng trả".
7. Excel báo cáo tự theo vì đọc cùng query; cập nhật tiêu đề cột nếu đổi.

## Verification

- `uv run pytest tests/reports tests/web/test_reports.py -q`
- Test view: đơn trả cả đơn có tổng 0 và không được đếm; trả một phần chỉ trừ phần trả; phiếu `VOID` không trừ; đơn `CANCELLED` không xuất hiện.
- Test khớp: tổng `customer_paid` theo tháng từ view bằng SUM `Customer paid` của các dòng file Shop Online cho cùng đơn (dùng `collect_all_rows` cộng dòng trả).
- `alembic upgrade head` và `downgrade -1` trên database dev đã sao lưu.

## Risks

- Đổi cách đếm đơn làm các con số cũ thay đổi. Ghi chú trong phase 6 để người dùng biết.
