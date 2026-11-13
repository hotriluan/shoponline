---
title: "Bộ đọc file Lazada và đơn nhiều sản phẩm"
date: 2026-11-13
summary: Thêm bộ đọc file chờ giao hàng của Lazada, lấy tên và địa chỉ khách từ cột billing; xác nhận đơn nhiều sản phẩm của cả ba sàn đi thành một SO, một hóa đơn
---

# Bộ đọc file Lazada và đơn nhiều sản phẩm

## File mẫu
- `docs/lazadaexport.xlsx`: một sheet, 77 cột, **mỗi dòng là một đơn vị sản phẩm**. Không có cột số lượng. `orderItemId` là mã từng đơn vị; các dòng cùng đơn chung `orderNumber`.
- Mã chủ dự án đưa làm ví dụ, `530668468300329`, là `orderItemId`. Đơn thật là `530668468200329` (hai dòng: Nâu đậm 8206 và Nâu nhạt 3002). Mã ghi vào `PO No` của SO phải là `orderNumber`.
- Giảm giá ghi số âm, theo từng dòng, tức theo từng đơn vị (`unitPrice` 120000, `platformDiscountTotal` -12500, `paidPrice` 107500).
- Tên và địa chỉ ở cột `billing*` không bị che, khác với `shipping*` và với Shopee, TikTok. `billingAddr` hay lặp lại phần số nhà: "146 Đường A, 146 Đường A".

## Cách làm
- `importers/lazada_orders.py`: gom theo `orderNumber`; các dòng cùng sản phẩm, phân loại, giá và trợ giá cộng thành số lượng; trợ giá một đơn vị = |sellerDiscountTotal| + |platformDiscountTotal|, giống TikTok (người bán + sàn).
- `ParsedOrder.customer_name` mới, chỉ Lazada điền. Khi nhập, tên và địa chỉ chỉ điền vào ô còn trống, không ghi đè ô admin đã sửa.
- Địa chỉ mặc định Lazada = `billingAddr` (bỏ phần lặp), phường (`billingAddr4`), tỉnh (`billingAddr3`), "Việt Nam". Cùng dạng với địa chỉ Lazada admin từng gõ tay trong file kế toán mẫu.

## Đơn nhiều sản phẩm
Không phải sửa gì ở luồng sau khi nhập. Ba sàn đều gom dòng theo mã đơn. File `ĐƠN HÀNG ONLINE` ghi chung một số `Đơn Hàng` cho các dòng của một đơn, nên sales admin tạo một SO. Đối chiếu `zrsd001` so vật tư và số lượng theo cả SO. File kế toán điền khách theo số SO cho mọi dòng của DO (mẫu `SHOP ONLINE 111126` có SO 210038698 với ba dòng). Đã thêm test đầu-cuối: một đơn Lazada hai sản phẩm thành hai dòng cùng số `1`, đơn kế tiếp số `2`.

## Kiểm chứng
- Chạy bộ đọc trên file mẫu thật: 4 đơn, đơn `530668468200329` có hai dòng, tên "Võ Đình Hà".
- 7 test mới (bộ đọc, nhập tên khách, không ghi đè, đơn nhiều sản phẩm trong file đơn hàng). Toàn bộ 155 test đạt.
- Ruff còn hai lỗi dòng dài có từ trước, ở `exports/accounting_workbook.py` và `tests/exports/test_order_workbook.py`.

## Còn mở
- File Lazada có cột `status` (mẫu toàn `pending`). Bộ đọc chưa lọc theo trạng thái, giống Shopee và TikTok. Nếu file tải về có lẫn đơn đã hủy thì cần quyết định cách xử lý.
- Cần nhập bảng ánh xạ cho Lazada; tên phân loại có dạng "Màu sắc:Nâu đậm - 8206, Đóng Gói:0.8 lít".
