# Bỏ phiếu nhập hàng trả về (ZDE1) khỏi file gửi kế toán

Ngày: 2026-11-26. Trạng thái: đã chốt hướng, chờ triển khai.

## Bằng chứng

- Lần gửi kế toán số 8 (file `SHOP ONLINE 261126.xlsx`, việc robot 91, 92, 93) có 5 dòng `Delivery Type = ZDE1`: SO 20001989 đến 20001993, delivery 1960001310 đến 1960001314, kho `0301`, `Req. Type` trống. 32 dòng còn lại là `ZDA1`, kho `0101`.
- Cả 5 SO không có trong `sales_order` lẫn `sap_so_ref`, nên lookup trả rỗng và hệ thống báo "thiếu mã đơn, tên khách, địa chỉ".
- Các file kế toán ngày 19, 20, 23 và 25/11 chỉ có `ZDA1`.
- Người dùng xác nhận: `ZDE1` là phiếu nhập hàng trả về. `0301` là kho tạm QC; hàng đạt QC mới chuyển sang kho thành phẩm.
- Người dùng đã bỏ tay 5 dòng này khỏi file 26/11 trước khi gửi.

## Hợp đồng

**Kết quả:** file gửi kế toán chỉ chứa phiếu giao bán (`ZDA1`). Phiếu nhập hàng trả về không vào file, không bị cộng vào dòng tổng và không tạo cảnh báo "thiếu mã đơn" ở cả trang Robot SAP lẫn trang đợt Gửi kế toán.

**Ràng buộc:**
- Lọc theo `Delivery Type`, không theo dấu hiệu thiếu thông tin khách. Đơn bán thật thiếu dữ liệu vẫn phải được báo.
- Danh sách cho phép (chỉ `ZDA1`), không phải danh sách chặn: một loại phiếu lạ sẽ bị bỏ và hiện ra, không âm thầm lọt vào file.
- Dòng bị bỏ được đếm với lý do riêng trên trang đợt. Trang đã liệt kê sẵn mọi lý do (`accounting_run.html`), nên không cần sửa giao diện.
- Cột `Delivery Type` trở thành cột bắt buộc của file kế toán gộp; thiếu cột thì từ chối file.

**Ngoài phạm vi:**
- Sửa lại file 26/11 (đã chốt và đã bỏ tay).
- Ghép phiếu `ZDE1` với tính năng phiếu trả hàng của hệ thống hoặc báo cáo trả hàng.
- Đưa danh sách loại phiếu vào `.env` hay trang cài đặt.

**Tiêu chí hoàn thành:**
- Gộp các file có cả `ZDA1` và `ZDE1`: kết quả không có dòng `ZDE1`, dòng tổng chỉ tính `ZDA1`, `dropped` có lý do "phiếu nhập hàng trả về / không phải phiếu giao bán (ZDE1)" với đúng số dòng.
- Một dòng `ZDE1` có trạng thái khác C hoặc chưa có ngày GI vẫn bị bỏ vì loại phiếu, không rơi vào danh sách "chưa goods issue xong".
- Bản xem trước một file (`build_accounting_workbook`, dùng khi robot đọc) không ghi cảnh báo thiếu thông tin cho dòng `ZDE1`, nhưng vẫn cảnh báo dòng `ZDA1` thiếu dữ liệu.
- Delivery `ZDE1` không được ghi vào sổ "đã gửi kế toán".
- Toàn bộ test hiện có vẫn qua.

## Hướng triển khai

Mọi thay đổi nằm trong `src/shoponline/exports/accounting_workbook.py`:

1. Thêm hằng `DELIVERY_TYPE_COLUMN = "Delivery Type"` và `SALES_DELIVERY_TYPES = ("ZDA1",)`, đặt cạnh `GOODS_ISSUED`, theo cách module đang giữ các mã SAP. Thêm lý do bỏ dòng mới.
2. `build_merged_accounting_workbook`: thêm cột vào `required`. Kiểm tra loại phiếu ngay sau kiểm tra khách hàng, trước các kiểm tra ngày GI và trạng thái.
3. `_fill_customers`: khi file có cột `Delivery Type`, bỏ qua dòng có loại phiếu không nằm trong danh sách (không điền, không cảnh báo). Bản xem trước một file vẫn giữ mọi dòng như SAP xuất.
4. Test trong `tests/exports/test_merged_accounting_workbook.py` và `tests/exports/test_accounting_workbook.py`; fixture `ZRSD004_HEADERS` đã có cột `Delivery Type`.
5. Tài liệu: bổ sung một câu ở `docs/daily-operations.md` bước 12 rằng phiếu nhập hàng trả về (`ZDE1`) không vào file kế toán.

`mark_delivered` không cần sửa: nó chỉ cập nhật đơn có SO trong `sales_order`, nên SO của phiếu `ZDE1` không bao giờ khớp.

## Đánh đổi

- **Danh sách cho phép `ZDA1` (đã chọn).** Dựa trên giả định `ZDA1` là loại phiếu giao bán duy nhất cho sàn; 5 file kế toán gần nhất đều đúng. Nếu SAP thêm một loại giao bán mới, các dòng đó sẽ bị bỏ, nhưng vẫn hiện trên trang đợt với lý do và số dòng, rồi sửa một hằng số.
- **Danh sách chặn `ZDE1`.** Dựa trên giả định không có loại phiếu lạ nào khác. Nếu có, phiếu đó lọt vào file mà không ai thấy, và kế toán nhận dữ liệu sai.

Better approaches: none — hướng đã chọn là hướng người dùng yêu cầu (dựa trên 5 file kế toán thực tế và xác nhận nghiệp vụ về `ZDE1`).
