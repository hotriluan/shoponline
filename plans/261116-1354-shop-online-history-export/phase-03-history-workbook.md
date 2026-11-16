---
phase: 3
title: "Bộ dựng file lịch sử"
status: completed
priority: P1
effort: "4h"
dependencies: [1]
---

# Phase 3: Bộ dựng file lịch sử

## Goal
Một hàm lấy mọi đơn `DELIVERED` chưa vào sổ đã xuất (đặt tới hết một ngày cho trước) và trả về các dòng đúng 17 cột của sheet1, hoặc danh sách đơn bị chặn kèm lý do; một hàm dựng workbook từ các dòng đó.

## Bối cảnh
- Mẫu bộ dựng: [order_workbook.py](../../src/shoponline/exports/order_workbook.py) (dataclass kết quả, `openpyxl`, định dạng số).
- Công thức giá trị dòng: [expected_value.py](../../src/shoponline/domain/expected_value.py) `Σ (unit_price − unit_subsidy) × quantity`.
- Sổ đã xuất: bảng `sales_history_exported` (phase 1).
- Header thật của sheet1 (dòng 1, giữ đúng chữ và khoảng trắng, chú ý `unitPrice ` có dấu cách cuối):
  `Division, createTime, month, year, billingName, billingPhone, billingCity, Cust + time, Transaction, Customer paid, unitPrice , sellerDiscountTotal, shippingFee, Quantity, itemName, Product Classification SKU, variation`.
- Dạng giá trị trong sheet1: createTime là chuỗi `YYYY-MM-DD HH:MM`; month và year là số; billingPhone là chuỗi `******`; công thức `=E2&" "&B2` và `=IF(H2=H1,0,1)` (dòng 2 trong file lịch sử là `1`).

## Files to Create / Modify
- Create: `src/shoponline/exports/sales_history_workbook.py`.
- Create: `tests/exports/test_sales_history_workbook.py`.

## Tasks & Steps
1. Hằng số `COLUMNS` (đúng header ở trên) và `DIVISION = {"SHOPEE": "Shopee Bình Dương", "TIKTOK": "tiktok Bình Dương", "LAZADA": "Lazada Mall"}`. Sàn không có trong `DIVISION` thì chặn với lý do "Sàn chưa có tên Division".
2. `collect_rows(session, until: date) -> HistoryRows`: <!-- Updated: Validation Session 1 - pending orders instead of a date range -->
   - đơn `status == DELIVERED`, không có dòng trong `sales_history_exported`, `ordered_at` trước `until + 1 ngày`;
   - nạp sẵn `customer_info` theo `(platform, platform_order_id)` và `report_item_name` theo mã vật tư bằng hai truy vấn (không truy vấn theo từng dòng);
   - sắp theo `ordered_at`, `platform_order_id`, `line_no`;
   - mỗi đơn thiếu tên khách (`customer_name` rỗng hoặc không có dòng `customer_info`), `province_of(address)` ra `None`, hoặc có dòng mà mã vật tư chưa có trong `report_item_name` thì thành một `BlockedOrder(platform, platform_order_id, ordered_at, reasons)`; một đơn có thể có nhiều lý do;
   - trả về `rows` (giá trị từng cột cho từng dòng sản phẩm), `order_ids` (id các đơn có trong `rows`), `blocked`.
3. `build_history_workbook(rows) -> Workbook`: sheet tên `sheet1`, header dòng 1 in đậm, dữ liệu từ dòng 2; cột H và I là công thức tương đối theo số dòng thật (`=E{r}&" "&B{r}`, `=IF(H{r}=H{r-1},0,1)`); `Customer paid` = `(unit_price − unit_subsidy) × quantity`; `unitPrice ` = `unit_price`; `sellerDiscountTotal`, `shippingFee` để trống; định dạng `#,##0` cho hai cột tiền.
4. `history_file_name(day)` = `SHOP ONLINE LỊCH SỬ {day:%d%m%y}.xlsx`, với `day` là ngày tải (`today_vn()`).
5. Bộ dựng không lưu file và không ghi sổ; phase 4 quyết định dựa trên `blocked` và `rows`.
6. Test với dữ liệu tự tạo trên fixture `db`:
   - đơn hai dòng sản phẩm, một dòng có `unit_subsidy` và `quantity = 2`: kiểm tiền và thứ tự dòng;
   - header trùng hằng số và đúng 17 cột; công thức dòng 2 và dòng 3 đúng;
   - đơn `READY` và `CANCELLED` không vào; đơn đã có trong `sales_history_exported` không vào; đơn đặt sau `until` không vào; đơn đặt lúc 23:59 ngày `until` có vào;
   - đơn đặt từ tháng trước nhưng chưa xác nhận vẫn vào (trường hợp DO trễ);
   - ba lý do chặn, mỗi lý do một test; đơn bị chặn không có dòng trong `rows` và không có trong `order_ids`;
   - mỗi sàn ra đúng chữ Division.

## Verification
- `uv run pytest tests/exports/test_sales_history_workbook.py`
- `uv run ruff check src tests`

## Risk & Rollback
- `ordered_at` lưu dạng giờ Việt Nam không múi giờ (theo file sàn); so sánh trực tiếp với ngày chọn, không đổi múi giờ.
- File mới, không sửa code cũ; lùi lại bằng cách xóa file.
