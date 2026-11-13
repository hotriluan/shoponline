# Vận hành hằng ngày (chế độ thủ công)

Dành cho admin shop online. Ở chế độ thủ công hệ thống không ghi gì vào SAP; sales admin vẫn tạo SO và DO như hiện nay.

## Trong ngày D

1. **Tải file sàn.** Trang **Tải file sàn**: chọn sàn (Shopee, TikTok hoặc Lazada), ngày xử lý D, chọn file "chờ giao hàng" tải từ trang quản lý sàn. Tải nhiều file trong một ngày được; đơn đã có không bị nhân đôi. Đơn có nhiều sản phẩm được gom thành một đơn: cùng một số ở cột `Đơn Hàng` trong file `ĐƠN HÀNG ONLINE`, nên sales admin tạo một SO và kế toán xuất một hóa đơn cho cả đơn. Lazada gom theo cột `orderNumber` (không phải `orderItemId`, là mã của từng sản phẩm).
2. **Xử lý đơn lỗi.** Nếu kết quả báo đơn **Thiếu ánh xạ**, vào **Ánh xạ SAP**, điền mã SAP và tên SAP cho các sản phẩm còn thiếu. Dòng nào đủ hai ô thì tự lưu khi chuyển sang ô khác; nút **Lưu tất cả** lưu lại mọi dòng đã điền (dòng để trống được bỏ qua). Nhiều dòng thì bấm **tải danh sách này ra Excel**, điền cột Mã SAP và Tên SAP, rồi nhập lại ở mục **Nhập từ Excel**. Đơn tự chuyển sang **Sẵn sàng**. Đơn **Cần kiểm tra** (ví dụ trợ giá TikTok không chia đều cho số lượng): mở đơn, kiểm tra tay, bấm **Đã kiểm tra, cho đi tiếp**.
3. **Kiểm tra ngày goods issue.** Màn hình lô đề xuất ngày làm việc kế tiếp (cuối tháng thì giữ ngày D). Gặp ngày lễ thì đổi ngày; ngày tự lưu và trang tải lại.
4. **Tải file `ĐƠN HÀNG ONLINE`** trên màn hình lô và gửi sales admin. File chỉ gồm đơn **Sẵn sàng**; đơn không giảm giá đứng trước, đơn có giảm giá đứng sau, cột `Sale` ghi trợ giá cho một sản phẩm. Sales admin phải tạo SO không giảm giá trước.
5. **Nhập tên khách.** Bấm **Nhập tên khách** trên màn hình lô, chép tên từ phiếu giao hàng. Địa chỉ đã điền sẵn từ file sàn; sửa nếu cần. Mỗi dòng tự lưu khi chuyển sang ô khác, kết quả hiện ở cột cuối; dòng lưu lỗi hiện chữ đỏ và trình duyệt hỏi lại trước khi rời trang. Đơn Lazada đã có sẵn tên (cột `billingName`) và địa chỉ đầy đủ (cột `billingAddr`) từ file; chỉ kiểm tra lại. Tên, địa chỉ đã sửa tay không bị nhập lại file ghi đè.
6. **Hủy đơn.** Đơn khách hủy trước khi làm SO: mở đơn, bấm **Đánh dấu hủy**. Việc hủy SO hoặc DO trong SAP vẫn do người làm.

## Sau khi sales admin tạo SO và DO

7. Trên màn hình lô bấm **Sales admin đã tạo SO và DO**.
8. Chạy `zrsd001` trong SAP với lựa chọn **Complete**, lọc đúng ngày D, xuất Excel. Trang **Báo cáo SAP**, mục zrsd001: chọn lô vừa xác nhận rồi tải file lên. Nếu file không có SO nào của sàn trong ngày D, hệ thống báo để kiểm tra lại bộ lọc. Khi robot đang bật, robot đọc `zrsd001` thay bạn ngay sau khi xác nhận lô; nếu sales admin tạo thêm SO sau đó, bấm **Đọc lại zrsd001** trên trang lô. Tải file bằng tay vẫn là đường dự phòng.
9. Đọc phần **Đối chiếu SO** trên màn hình lô:
   - **Đơn sẵn sàng chưa có SO**: sales admin còn sót đơn.
   - **SO có PO No không khớp đơn nào**: thường do gõ sai mã đơn vào `PO No`. Chọn đúng đơn ở cột **Nối với đơn** rồi bấm **Nối**.
   - **Một mã đơn có nhiều SO**: báo sales admin hủy SO thừa trong SAP.
   - **SO khác file sàn**: giá trị hoặc mã vật tư, số lượng khác file sàn; kiểm tra SO trong SAP.

## Ngày goods issue

10. Chạy `zrsd004` trong SAP, xuất Excel. Trang **Báo cáo SAP**, mục zrsd004: tải file lên.
11. Màn hình xem trước liệt kê các dòng còn thiếu mã đơn, tên khách hoặc địa chỉ. Bổ sung ở trang **Khách hàng** rồi tải lại file zrsd004, hoặc vẫn bấm tải nếu chấp nhận.
12. Tải `SHOP ONLINE ddmmyy.xlsx` và gửi kế toán. File giữ nguyên mọi cột, mọi dòng của `zrsd004` (kể cả hai dòng tổng) và chèn ba cột `mã đơn hàng`, `tên khách hàng`, `địa chỉ` ngay sau `SO Reference`. Đơn đã hủy DO không còn trong `zrsd004` nên không có trong file.

## Khi có sự cố

- **Web không mở được hoặc máy chạy thật hỏng:** làm file Excel bằng tay như trước, báo người quản trị hệ thống.
- **Thanh cảnh báo sao lưu màu cam:** bản sao lưu gần nhất đã quá 36 giờ; báo người quản trị.
- **File bị từ chối:** thông báo nêu cột thiếu hoặc dòng lỗi. Sàn có thể đã đổi mẫu file; không sửa tay file sàn, báo người quản trị.

## Biên bản chạy song song (cổng G1)

Trong 10 ngày làm việc liên tiếp, admin vẫn làm file gửi kế toán bằng tay và so từng ô với file hệ thống. Mỗi khác biệt được ghi lại, sửa trong hệ thống và thêm thành ca test.

| Ngày | Sàn | Số dòng | Ô khác nhau | Ghi chú | Người so |
|---|---|---|---|---|---|
| 11/11/2026 (dữ liệu mẫu, trên máy phát triển) | Shopee, TikTok, Lazada | 15 dòng DO | 0 | So `SHOP ONLINE 111126.XLSX` dựng lại từ `zrsd001`, `zrsd004`, `NOTE TT KH T11` | Kiểm thử tự động |
