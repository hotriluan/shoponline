# Brainstorm: xuất dòng nối tiếp file "Shop Online 2022-2026"

Ngày: 2026-11-16. Nguồn: `docs/Shop Online 2022-2026_10.xlsx` (sheet1, 17 cột dữ liệu, 3.010 dòng tới 10/2026) và database production `shoponline` trên máy 192.168.18.123, kiểm tra chỉ đọc qua SSH.

## Outcome
Admin chọn khoảng ngày trên web và tải về một file có đúng 17 cột như sheet1. File gồm các dòng của những đơn đã có DO (`status = DELIVERED`), mỗi dòng sản phẩm là một dòng. Admin dán các dòng này vào cuối file lịch sử mà không phải gõ tay cột nào.

## Quyết định của người dùng
- `unitPrice` = `sales_order_item.unit_price`, tức đơn giá của dòng trong đơn. Các con số kiểu 90.300 ở các dòng cũ là giá đã thay đổi trên sàn; không cần tái tạo.
- Shop: SHOPEE là Shopee Bình Dương.
- Chỉ xuất đơn giao thành công. Không cần tách đơn bị trả hàng sau khi đã có DO.
- `billingName` lấy `customer_info.customer_name`. Admin phải bổ sung tên trước khi xuất; đơn còn thiếu tên thì chặn xuất.

## Cột và nguồn

| Cột | Nguồn |
|---|---|
| Division | Từ sàn: SHOPEE thành `Shopee Bình Dương`, TIKTOK thành `tiktok Bình Dương`, LAZADA thành `Lazada Mall` (theo các dòng 2026 trong file) |
| createTime | `ordered_at`, dạng `YYYY-MM-DD HH:MM` |
| month, year | Từ `ordered_at` |
| billingName | `customer_info.customer_name`; bắt buộc có |
| billingPhone | Chữ `******` |
| billingCity | Tách tỉnh/thành từ `customer_info.address` (xem bên dưới) |
| Cust + time, Transaction | Công thức `=E{n}&" "&B{n}` và `=IF(H{n}=H{n-1},0,1)`, viết theo số dòng thật khi dán |
| Customer paid | `unit_price × quantity`, khớp cách ghi tổng tiền dòng ở các dòng 2026 |
| unitPrice | `unit_price` |
| sellerDiscountTotal, shippingFee | Để trống, như các dòng 2026 |
| Quantity | `quantity` |
| itemName, Product Classification SKU, variation | Bảng tên báo cáo theo mã vật tư (xem bên dưới) |

## billingCity: tách tự động từ địa chỉ
Trên production, mọi địa chỉ đều kết thúc bằng `…, <tỉnh/thành>, Việt Nam`. Ví dụ: `Phường Bình Thạnh, Thành phố Hồ Chí Minh, Việt Nam` hoặc `Xã Bình Hòa, Tỉnh An Giang, Việt Nam`. Cách lấy: lấy phần đứng trước `Việt Nam`, bỏ tiền tố `Thành phố ` hoặc `Tỉnh `, rồi so với danh sách cố định 34 tỉnh/thành sau sáp nhập 2025. Nếu không khớp danh sách thì chặn xuất và chỉ ra đơn đó, để admin sửa địa chỉ trên web. Không đoán.

## itemName, kích cỡ, variation: dùng ánh xạ SAP làm cầu nối
Bảng `sku_mapping` có 597 dòng, theo cặp (sàn, tên sản phẩm, tên phân loại). Các dòng đó dồn về 75 mã vật tư, và mọi dòng đơn đã có `material_number`. Tên trên sàn và tên SAP (ví dụ `V-09 REDDISH CLAY 2004 VN-0.8L`) đều không trùng kiểu tên của file (`Propan - ULTRAN VERNIS - V-09 - Sơn Dầu Bóng Màu` / `0.8 lít` / `Màu sắc:2004 Cánh gián`). Vì vậy dùng ánh xạ SAP để có mã vật tư, rồi tra mã vật tư trong một bảng nhỏ mới giữ ba cột tên báo cáo.

Các phương án đã so sánh:
- **A. Bảng tên báo cáo theo mã vật tư (đề xuất).** Một bảng khoảng 75 dòng: mã vật tư, itemName, kích cỡ, variation. Điền sẵn bằng script; admin duyệt một lần qua upload/download như file ánh xạ. Mã vật tư mới chưa có tên báo cáo thì chặn xuất. Phương án này dựa vào một giả định: tên báo cáo chỉ phụ thuộc vào vật tư, không phụ thuộc vào sàn. Nó sai khi kế toán muốn cùng một vật tư mang tên khác nhau trên từng sàn.
- **B. Thêm ba cột vào `sku_mapping`.** Không cần bảng mới, nhưng admin phải điền 597 dòng thay vì 75 dòng, và cùng một vật tư dễ bị điền tên khác nhau.
- **C. Suy tên bằng quy tắc trong code.** Kích cỡ lấy từ đuôi tên SAP, màu lấy từ tên phân loại trên sàn, itemName lấy theo dòng sản phẩm. Không cần nhập liệu, nhưng sẽ sai khi sàn đổi cách đặt tên, và file lịch sử viết hoa không thống nhất (`Màu sắc:` lẫn `Màu Sắc:`).

Trade-offs: A tốn một lần duyệt 75 dòng và thêm một bảng; B tốn công nhập gấp tám lần; C rẻ nhất lúc đầu nhưng hỏng âm thầm khi sàn đổi tên. A rẻ nhất để bỏ nếu cần đổi: chỉ cần xóa một bảng.

Better approaches: không có cách nào tốt hơn. Hướng đề xuất đúng là dùng ánh xạ SAP như người dùng gợi ý (bằng chứng: 100% dòng đơn trên production đã có `material_number`).

## Constraints
- Chỉ đọc dữ liệu đơn hàng. Bảng mới đi qua một migration Alembic, sao lưu database trước khi migrate trên production.
- Không đổi các bảng đơn hàng đang có và không đổi các file xuất đang có.
- Theo cách xuất file hiện có trong `src/shoponline/exports/`.

## Non-goals
- Không nạp ngược 3.010 dòng lịch sử vào database.
- Không ghi trực tiếp vào file lịch sử; admin tự dán.
- Không làm sellerDiscountTotal, shippingFee, số điện thoại thật, hay theo dõi đơn trả hàng.
- Không thêm shop Shopee PGT, Shopee Đà Nẵng.

## Acceptance criteria
- Xuất khoảng 11–16/11/2026 trên dữ liệu production ra đúng các dòng của 24 đơn đã có DO, đủ 17 cột theo đúng thứ tự tiêu đề của sheet1.
- Việc xuất bị chặn, và danh sách đơn được liệt kê, khi: thiếu tên khách, tỉnh/thành không tách được, hoặc mã vật tư chưa có tên báo cáo.
- Dán vào cuối file lịch sử thì các công thức `Cust + time` và `Transaction` tính đúng.
- Có test cho phần tách tỉnh/thành, cách tính Customer paid/unitPrice, và điều kiện chặn xuất.

## Câu hỏi còn mở
- Customer paid có trừ trợ giá (`unit_subsidy`) không? Các dòng 2026 trong file luôn ghi theo giá gốc, nên đề xuất trên dùng giá gốc. Trên production có 7 dòng đơn có trợ giá (4 Lazada, 3 TikTok).
