---
phase: 5
title: "View báo cáo và lớp truy vấn"
status: completed
priority: P1
effort: "6h"
dependencies: [2, 3, 4]
---

# Phase 5: View báo cáo và lớp truy vấn

## Goal

Hai view SQL làm nguồn duy nhất cho mọi báo cáo, và một module Python trả số liệu đã tổng hợp theo bộ lọc, để trang web và file Excel dùng chung.

## Thiết kế

- **Migration `0016_report_views`** tạo hai view trong schema `public` bằng `CREATE OR REPLACE VIEW`; downgrade thì `DROP VIEW`. View nằm trong `public` nên được `pg_dump` và phục hồi cùng dữ liệu. Đổi view sau này đi qua migration mới.
- **`report_sale_line`**, một dòng mỗi dòng sản phẩm, cùng cột cho hai nguồn:
  - Cột: `source` (`history` | `system`), `period` (ngày 1 của tháng), `ordered_on`, `platform`, `shop_code`, `division`, `province`, `item_name`, `size`, `variation`, `quantity`, `customer_paid`, `order_key`.
  - Phần lịch sử: từ `history_sale_line`; `province` = tên khớp 34 tỉnh, hoặc qua `province_alias`, còn lại NULL.
  - Phần hệ thống: từ `sales_order_item` nối `sales_order` với `ordered_at >= '2026-11-11'` và trạng thái khác `CANCELLED`. `customer_paid = (unit_price − unit_subsidy) × quantity`, đúng công thức file lịch sử đang dùng. Tên hàng, quy cách, màu lấy từ `report_item_name` theo `material_number`; chưa có thì lấy `product_name` / `variation_name`. `province` = `customer_info.province`, hoặc qua `province_alias` theo phần cuối địa chỉ. `order_key` = `sales_order.id`.
  - Mốc `2026-11-11` viết thẳng trong SQL của migration, và test so nó với `REPORTING_CUTOVER`.
- **`report_order_revenue`**, một dòng mỗi đơn hệ thống (từ mốc, khác `CANCELLED`):
  - Định danh: `sales_order_id`, `platform`, `shop_code`, `period`, `status`.
  - Ba con số: `marketplace_value` (tổng `customer_paid`), `invoice_value` (`net_value_vnd + tax_vnd` từ `sap_tax_invoice` theo `do_number`, NULL khi chưa có hóa đơn), `settled_value` (tổng `platform_settlement.amount` theo `(platform, platform_order_id)`, NULL khi chưa có).
  - Trả hàng: `returned_value` (tổng `sales_return_line.amount_returned` của phiếu có `status = 'ISSUED'`, bỏ `VOID`; tính cả `reason_kind` `CANCEL` và `RETURN`). <!-- Updated: Validation Session 1 - giá trị thật của status là ISSUED/VOID -->- **`src/shoponline/reports/queries.py`**, mọi hàm nhận `Filters(from_period, to_period, platforms, shop_codes)`:
  - `monthly_overview`: theo tháng gồm giá trị trên sàn (cả lịch sử), doanh thu hóa đơn, tiền thực nhận, trợ giá/chênh giá, phí sàn, số đơn, giá trị đơn trung bình, giá trị trả, tỷ lệ trả. Phí sàn và chênh giá chỉ tính trên các đơn có đủ hai số, đồng thời trả kèm số đơn còn thiếu hóa đơn và thiếu tiền.
  - `by_channel`: theo sàn và shop.
  - `by_product`: theo tên hàng, quy cách, màu; số lượng và giá trị.
  - `by_province`: theo tỉnh, có dòng "Chưa xác định".
  - `returns`: theo tháng và lý do (`sales_return.reason_kind`).
  - `data_notes`: các cảnh báo về độ đủ dữ liệu, ví dụ "Tháng 11/2026 thiếu đơn 01–10/11" khi chưa có dòng lịch sử nào kỳ 11/2026; "Lịch sử không có doanh thu hóa đơn và tiền thực nhận".

## Files to Create / Modify

- Create: `migrations/versions/0016_report_views.py`
- Create: `src/shoponline/reports/queries.py`
- Create: `tests/reports/test_report_views.py`, `tests/reports/test_queries.py`

## Tasks & Steps

- [ ] Viết view; test với dữ liệu tự dựng có cả hai nguồn ở hai bên mốc, đơn hủy, đơn chưa hóa đơn, đơn có tiền Lazada nhập tay, đơn có phiếu trả đã hủy.
- [ ] Viết `queries.py`; test từng hàm, nhất là phí sàn chỉ tính trên đơn đủ số.
- [ ] Test khóa mốc: đổi `REPORTING_CUTOVER` mà không sửa view thì test hỏng.
- [ ] Đo trên database dev đã nạp lịch sử: `monthly_overview` cho toàn khoảng 2022–nay dưới 500 ms.

## Verification

- `uv run pytest tests/reports`
- Truy vấn tay một tháng mẫu trên `sales_order_item`, `sap_tax_invoice`, `platform_settlement`; so với `monthly_overview`.

## Risk

- Một đơn có nhiều DO hoặc một DO nhiều hóa đơn sẽ làm nhân đôi doanh thu hóa đơn. `sap_tax_invoice` có khóa `delivery`, và `sales_order.do_number` chỉ là một giá trị, nên hiện là 1–1. Test giữ điều đó.

## Kết quả (2026-11-25)

Migration `0016_report_views` (hai view, cộng cột `history_sale_line.city_key` và `customer_info.place_key` để view tra `province_alias` bằng khóa đã chuẩn hóa mà không cần extension `unaccent`), `reports/queries.py` (`monthly_overview`, `by_channel`, `monthly_by_channel`, `by_product`, `by_province`, `returns`, `data_notes`). Test: `tests/reports/test_report_views.py`, `tests/reports/test_queries.py`. Trên dev: `monthly_overview` 59 tháng trong 57 ms; ba đường doanh thu tháng 11/2026 khớp truy vấn tay.
