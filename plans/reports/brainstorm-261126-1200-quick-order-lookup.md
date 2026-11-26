# Brainstorm: tra cứu nhanh đơn hàng theo mã đơn / số hóa đơn

Ngày: 2026-11-26 · Trạng thái: đã chốt hướng A, phạm vi gồm mã đơn, hóa đơn VAT, SO, DO, phiếu trả

## Hiện trạng (đã kiểm tra trong code)

- Trang chi tiết đơn đã có sẵn: `GET /orders/{id}` ([orders.py](../../src/shoponline/web/routes/orders.py)).
- Không có đường nào đi thẳng tới đơn. Người dùng phải vào `/batches` → mở từng lô → tìm trong bảng. Ô tìm của `/batches` chỉ lọc theo cột của lô (sàn, ngày, người xác nhận), không lọc theo mã đơn.
- Dữ liệu cần để tra đều có trong DB:
  - mã đơn sàn: `sales_order.platform_order_id` (chỉ có unique index `(platform, platform_order_id)`; tra mà không biết sàn thì index này không dùng được hiệu quả);
  - SO: `sales_order.so_number` (đã có index); DO: `sales_order.do_number` (chưa có index);
  - số hóa đơn: `sap_tax_invoice.tax_invoice_doc`, nối qua `delivery = sales_order.do_number`. Số này lưu kèm số 0 ở đầu; code kế toán đã phải dùng `ltrim(tax_invoice_doc, '0')` để so khớp ([settlement_invoice_file.py:106](../../src/shoponline/accounting/settlement_invoice_file.py#L106));
  - số phiếu trả hàng: `sales_return.doc_no` → `sales_order_id`.
- Đã có sẵn helper tìm kiếm `search_filter` ([pagination.py](../../src/shoponline/web/pagination.py)), nên phần khớp gần đúng không cần viết mới.

## Contract

- **Outcome:** Từ bất kỳ trang nào, người dùng dán mã đơn sàn, số hóa đơn VAT, số SO, số DO hoặc số phiếu trả hàng vào một ô tìm kiếm duy nhất. Nếu chỉ có một đơn khớp thì mở thẳng trang chi tiết đơn; nếu có nhiều đơn thì hiện danh sách ngắn để chọn; nếu không có đơn nào thì báo rõ là không tìm thấy.
- **Constraints:** Dùng stack hiện có (FastAPI + Jinja + app.js, không thêm framework JS). Chỉ đọc dữ liệu, không thay đổi trạng thái đơn. Mọi người dùng đã đăng nhập đều dùng được (`current_user`). Nếu có migration thêm index thì phải sao lưu DB trước.
- **Non-goals:** Tìm theo tên khách, số điện thoại hay sản phẩm. Tìm trong file lịch sử 2022–2026 (`history_sale_line` không lưu mã đơn sàn). Typeahead/gợi ý khi đang gõ. Bộ lọc nâng cao.
- **Acceptance criteria:**
  1. Dán đúng mã đơn (kể cả khi dính khoảng trắng hoặc tab khi copy từ Excel, hay khác chữ hoa/thường) thì chuyển thẳng tới `/orders/{id}`.
  2. Gõ số hóa đơn VAT (`tax_invoice_doc`) có hoặc không có số 0 ở đầu (`0001234` hay `1234`) đều ra cùng một đơn. Không tra theo số billing SAP.
  2b. Gõ đúng số SO hoặc DO thì ra đơn tương ứng.
  2c. Gõ số phiếu trả hàng, đầy đủ (`012/11.2026 <hậu tố>`) hoặc chỉ phần đầu (`012/11.2026`), không phân biệt khoảng trắng, thì ra đơn của phiếu đó.
  3. Một mã khớp nhiều đơn thì hiện danh sách gồm sàn, shop, lô (có link), trạng thái và ngày đặt.
  4. Không khớp chính xác thì thử khớp một phần (tối thiểu 4 ký tự, tối đa 50 kết quả). Vẫn không có thì báo "Không tìm thấy" và giữ lại từ khóa trong ô.
  5. Ô tìm hiện ở mọi trang khi đã đăng nhập; phím `/` đưa con trỏ vào ô.
  6. Có test route cho các trường hợp: 1 kết quả (redirect), nhiều kết quả, khớp một phần, không có kết quả, số hóa đơn có số 0 ở đầu, SO, DO, phiếu trả (đầy đủ và chỉ phần đầu).

## Các phương án

| | A. Ô tra cứu toàn cục + nhảy thẳng (khuyến nghị) | B. Thêm lọc theo mã đơn vào trang Lô đơn | C. A cộng typeahead (gợi ý khi gõ) |
|---|---|---|---|
| Thao tác | Dán mã → Enter → đang ở trang đơn | Vào Lô đơn → gõ → ra lô → mở lô → tìm đơn | Gõ → chọn gợi ý |
| Số bước | 1 | 3–4 | 1 |
| Chi phí | 1 route, 1 template, sửa base.html, vài dòng JS | Sửa truy vấn trang Lô đơn | Như A, thêm endpoint JSON và JS dropdown, xử lý bàn phím, khả năng truy cập |
| Giả định chính | Người dùng thường có mã đầy đủ (dán từ file sàn, hóa đơn, Zalo) | Người dùng vẫn muốn xem theo lô | Người dùng thường chỉ nhớ một phần mã |
| Hỏng đầu tiên khi | Mã không đầy đủ. Đã có bước khớp một phần làm dự phòng | Luôn chậm hơn A; vẫn là "vô từng lô" | JS phức tạp hơn, dễ lỗi trên mạng chậm, lợi ích thêm nhỏ |

Khuyến nghị **A**: chi phí nhỏ nhất mà giải quyết đúng vấn đề, và nếu sau này cần thì C xây tiếp được trên A mà không phải làm lại.

### Thiết kế A

- `GET /search?q=` (file mới `web/routes/search.py`). Chuẩn hóa từ khóa: bỏ mọi khoảng trắng, đổi sang chữ hoa. Sau đó tra theo thứ tự:
  1. **Khớp chính xác (UNION):** `upper(platform_order_id) = q`; `ltrim(tax_invoice_doc,'0') = ltrim(q,'0')` nối sang đơn qua `do_number`; `so_number = q`; `do_number = q`; `replace(upper(doc_no),' ','') LIKE q || '%'` của `sales_return`, tính cả phiếu đã hủy (`VOIDED`) và đánh dấu trạng thái trên trang kết quả. Số phiếu trả có khoảng trắng bên trong nên phải so sau khi bỏ khoảng trắng ở cả hai phía. Trường hợp khác: phiếu có ký tự `/`, cần escape `%` và `_` trong LIKE.
  2. Đúng 1 đơn → `303` sang `/orders/{id}`. Nhiều đơn → trang `search.html`, ghi rõ khớp theo trường nào ("mã đơn", "hóa đơn", ...).
  3. 0 đơn và `len(q) >= 4` → khớp một phần bằng `search_filter`, giới hạn 50. 0 đơn → báo không tìm thấy.
- `base.html`: thêm form GET `/search` ở đầu sidebar và trên topbar mobile, kèm `placeholder="Mã đơn / số hóa đơn"`. Trong `app.js`: phím `/` để focus (bỏ qua khi đang gõ trong input khác).
- `order_detail.html` đã có sẵn link quay về lô của đơn ([order_detail.html:5](../../src/shoponline/web/templates/order_detail.html#L5)), không cần sửa.
- Index (migration `0020`): `sales_order (upper(platform_order_id))`, `sales_order (do_number)`, `sap_tax_invoice (ltrim(tax_invoice_doc,'0'))`. Lượng dữ liệu hiện tại có lẽ quét tuần tự vẫn đủ nhanh; index chủ yếu để giữ tốc độ khi dữ liệu tăng qua nhiều năm.

## Trade-offs

- A dựa vào giả định "có mã đầy đủ". Bước khớp một phần che phần lớn trường hợp còn lại, đổi lại có thể ra nhiều kết quả với chuỗi ngắn, nên cần giới hạn 4 ký tự và 50 kết quả.
- Đã chốt gộp SO/DO/phiếu trả vào cùng ô. Đánh đổi: một chuỗi số ngắn có thể khớp nhiều loại mã cùng lúc. Trang nhiều kết quả phải ghi rõ khớp theo trường nào để người dùng chọn đúng.

## Better approaches

Không có. Hướng khuyến nghị đúng là hướng anh/chị yêu cầu (đi thẳng tới đơn), và mã nguồn đã có sẵn trang đơn cùng helper tìm kiếm.

## Quyết định của người dùng

1. Ô tìm kiếm gồm cả SO, DO và số phiếu trả hàng: **có**.
2. "Số hóa đơn" là số hóa đơn VAT (`tax_invoice_doc`), không phải số billing SAP.
