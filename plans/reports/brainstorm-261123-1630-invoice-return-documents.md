# Brainstorm: Trả hàng sau khi đã xuất hóa đơn — tự lập Biên bản điều chỉnh hóa đơn và REQUEST to RETURN GOODS

Ngày 2026-11-23, cập nhật 16:42 sau vòng trả lời thứ hai. Đầu vào cho bước lập kế hoạch. Mẫu gốc: [docs/bbdchd/](../../docs/bbdchd/).

## Bối cảnh đã kiểm chứng

- **Biên bản điều chỉnh (Word, `BBDC_*.docx`)**: trường đỏ là số biên bản `077/11.2026`, tên và địa chỉ người mua, tên sàn, số và ngày hóa đơn, bảng "trước điều chỉnh" và "điều chỉnh" (tên hàng, ĐVT, SL, đơn giá, thành tiền, cộng tiền hàng, thuế, tổng), mã đơn sàn. Bảng mẫu chỉ có một dòng hàng.
- **REQUEST to RETURN GOODS (`FM-LG-Q004.01_*.xls`, định dạng Excel 97)**: sheet in là `RRG ENGLISH`; ô động `H6` (sàn), `D14` (tên hàng), kèm `N14` số lượng, `P14` ĐVT, `AL14` lý do `KHÁCH TRẢ HÀNG`. Các sheet khác ẩn hoặc rỗng.
- **Hóa đơn PDF (Bkav)**: `pdfplumber` đọc bảng thành cột sạch, ví dụ `['1', 'SƠN V-09 REDDISH CLAY 2004 VN', 'LON 0.8 LT', '1', '111.111', '111.111']`, và phần đầu có ký hiệu `1C26TAL`, số `00008038`, ngày, số DO, số PO (= mã đơn sàn), người mua, địa chỉ, cộng tiền hàng, thuế suất, tiền thuế, tổng. `pypdf` chỉ ra một chuỗi liền nên không tách được tên hàng với ĐVT.
- **Mẫu Word gõ tay đã lệch hóa đơn**: Word ghi `SƠN V-09 REDDISH CLAY VN` / `LON 1 LT`, hóa đơn ghi `… 2004 VN` / `LON 0.8 LT`.
- **zrsd003** chỉ có cấp hóa đơn: `Billing Date`, `Billing Doc.`, `OD Doc.` (DO), `Tax Invoice Doc.`, `Bill-to`, `Net Value (VND)` 111111, `Tax (VND)` 8889. Không có dòng hàng hay người mua.
- **Database** (đã kiểm với hai đơn mẫu `261115BUCPCSEN`, `534218339824472`): `customer_info` có tên và địa chỉ khớp hóa đơn; `sap_so_ref_item` có mã vật tư, số lượng, `net_value_incl` 120000; `sales_order_item.sap_name` là `V-09 REDDISH CLAY 2004 VN-0.8L`; `sap_tax_invoice` có số hóa đơn, billing doc, ngày nhưng **chưa lưu** tiền hàng và thuế; `customer_info` bị xóa sau 90 ngày.

## Quyết định của người dùng

- Số biên bản `NNN/MM.YYYY`: `NNN` reset mỗi năm, chỉ hệ thống cấp. Số bắt đầu được nhập **một lần duy nhất** khi triển khai.
- Trả cả đơn hoặc một phần (chọn dòng, số lượng). **Mỗi đơn chỉ trả một lần.**
- Câu lý do chọn giữa "hủy đơn hàng" và "trả lại hàng".
- Bản chụp tên, địa chỉ người mua và file đã phát hành giữ lâu dài, không bị quét 90 ngày.
- Word: dòng "Hôm nay, ngày … tháng … năm" để trống ngày, tháng. Excel: ô `No`, `Date` để trống.
- Tên hàng, ĐVT trên hóa đơn lấy từ **master riêng**. Khi lập phiếu, tra master trước; vật tư nào chưa có thì yêu cầu tải PDF hóa đơn của đơn đó lên, đọc ra và ghi vào master.
- Ô tên hàng `D14` của file Excel dùng **tên SAP**; biên bản Word dùng tên trên hóa đơn từ master (sửa lại lúc 16:58).
- Hai file xuất ra giống mẫu 100% về bố cục và định dạng; vẫn `.xlsx`, chữ trường động màu đen.

## Hợp đồng

**Outcome.** Với một đơn `DELIVERED` đã có hóa đơn trong `sap_tax_invoice` và chưa có phiếu trả hàng, admin mở đơn, chọn lý do, chọn dòng và số lượng trả (mặc định cả đơn). Nếu master thiếu vật tư nào của đơn, màn hình yêu cầu tải PDF hóa đơn, đọc và ghi vào master. Sau khi xem trước, admin bấm Phát hành. Hệ thống cấp số, lưu phiếu kèm bản chụp dữ liệu, sinh Biên bản điều chỉnh hóa đơn (`.docx`) và REQUEST to RETURN GOODS (`.xlsx`) để in. Trang danh sách phiếu cho tải lại và hủy phiếu. Trang master cho xem và sửa tên trên hóa đơn.

**Constraints.**
- Số liệu lấy từ database, zrsd003 và master; thiếu giá trị nào thì chặn và nói rõ thiếu gì, không đoán.
- Một đơn có tối đa một phiếu chưa hủy. Số đã cấp không dùng lại, kể cả khi phiếu bị hủy.
- Hệ thống không ghi gì vào SAP hay Bkav.
- Cập nhật [security-and-data-retention.md](../../docs/security-and-data-retention.md) cho phần dữ liệu cá nhân giữ lâu dài.

**Non-goals.**
- Lập hóa đơn điều chỉnh trên Bkav, tạo return order hay credit memo trong SAP.
- Xuất PDF hoặc gửi lệnh in tự động; người dùng in từ file tải về.
- Sửa file gửi kế toán hay file lịch sử Shop Online cho đơn bị trả.
- Đổi trạng thái đơn trong `domain/states.py`; việc trả hàng nằm ở bảng riêng và `event_log`.
- Nạp master hàng loạt từ nhiều PDF không gắn với phiếu nào.
- Lưu file PDF hóa đơn đã tải lên (chỉ đọc rồi bỏ, như các file nhập khác hết dùng).

**Acceptance criteria.**
1. Với hai đơn mẫu, file sinh ra khớp từng trường đỏ của mẫu; tên hàng, ĐVT khớp PDF hóa đơn (`SƠN V-09 REDDISH CLAY 2004 VN`, `LON 0.8 LT`), còn ô `D14` của Excel là tên SAP `V-09 REDDISH CLAY 2004 VN-0.8L`; số hóa đơn `00008038` / `00008020`; ký hiệu `1C26TAL`; ngày `17/11/2026`; tiền 111.111 / 8.889 / 120.000; dòng điều chỉnh mang dấu âm.
2. Master rỗng: lập phiếu bị chặn tới khi tải PDF; PDF đúng đơn thì master có dòng `100001787 → SƠN V-09 REDDISH CLAY 2004 VN / LON 0.8 LT`; đơn sau cùng vật tư lập phiếu không cần PDF.
3. PDF không khớp đơn (số DO, số PO, số hóa đơn khác; số dòng, số lượng hoặc tiền dòng khác dữ liệu SO) bị từ chối, master không đổi.
4. Trả cả đơn: cộng tiền hàng và thuế điều chỉnh bằng đúng `Net Value (VND)` và `Tax (VND)` của zrsd003, đổi dấu. Trả một phần: chỉ dòng trả có ở bảng điều chỉnh.
5. Đơn nhiều dòng: bảng Word và bảng Excel có đủ số dòng.
6. Đơn đã có phiếu chưa hủy thì không lập thêm được; hủy phiếu (cần lý do, giữ số, ghi `event_log`) thì lập lại được với số mới.
7. Hai lần phát hành đồng thời không nhận trùng số; số đầu năm mới là `001`; phát hành bị chặn khi chưa nhập số bắt đầu của năm đầu tiên.
8. Đơn thiếu hóa đơn hoặc thiếu tiền zrsd003, hay có tổng SO lệch tổng hóa đơn, thì bị chặn với lý do cụ thể.
9. Quét thời hạn lưu không xóa phiếu trả hàng và file của nó.
10. `uv run pytest` và `uv run ruff check` đạt.

## Ánh xạ trường

| Trường trên biểu mẫu | Nguồn |
|---|---|
| Số `077/11.2026` | Bộ đếm theo năm + tháng, năm phát hành |
| "Hôm nay, ngày … tháng … năm" | Để trống ngày, tháng. Năm: mẫu đang cứng `2026` (không tô đỏ); đề xuất điền năm phát hành để sang 2027 không sai |
| Người mua, địa chỉ | `customer_info`, chụp vào phiếu; được sửa khi lập nếu dữ liệu đã bị xóa |
| Tên sàn (Word), Plant/Sloc `H6` (Excel) | `platform_setting.display_name` |
| Mẫu số ký hiệu `1C26TAL` | `1C` + 2 số cuối năm của `billing_date` + `TAL` (mẫu đặt trong cấu hình) |
| Số hóa đơn `00008038`, ngày hóa đơn | `sap_tax_invoice.tax_invoice_doc` đệm 8 chữ số, `billing_date` |
| Tên hàng, ĐVT trên hóa đơn | Master `invoice_item_text` theo mã vật tư |
| Số lượng | `sap_so_ref_item.quantity`; số trả do người lập chọn |
| Đơn giá, thành tiền chưa thuế | Tính từ `sap_so_ref_item.net_value_incl` và thuế suất, cân về tổng zrsd003 |
| Cộng tiền hàng, thuế, tổng | zrsd003 `Net Value (VND)`, `Tax (VND)`: cột mới trong `sap_tax_invoice` |
| Thuế suất `8%` | `Tax / Net` của zrsd003, phải ra số phần trăm nguyên |
| Mã đơn bị hủy | `sales_order.platform_order_id` |
| Câu lý do (Word), `AL14` (Excel) | Lựa chọn "hủy đơn hàng" / "trả lại hàng" → `KHÁCH HỦY ĐƠN` / `KHÁCH TRẢ HÀNG` |
| Excel `D14` tên hàng, `P14` ĐVT | **Tên SAP** `sales_order_item.sap_name` (sửa lại 16:58: người dùng nhầm ở lượt trước); ĐVT kho `stock_unit` trong master, mặc định `PC` |
| Excel `No`, `Date` | Để trống |

**Tính tiền.** Thuế suất `r = Tax / Net`. Mỗi dòng `net_i = round(net_value_incl_i / (1 + r))`; nếu tổng khác `Net Value (VND)` thì dồn phần lệch vào dòng lớn nhất; lệch quá số dòng, hoặc tổng `net_value_incl` khác `Net + Tax`, thì chặn. Đơn giá = `net_i / qty_i`. Trả cả đơn lấy đúng `Net` và `Tax` của zrsd003. Trả một phần: thành tiền trả = đơn giá × số trả, thuế = `round(thành tiền × r)`. Khi có PDF tải lên, số tiền tính ra được so với PDF từng dòng; lệch thì báo, nhờ vậy cách tính được kiểm bằng hóa đơn thật.

## Master tên trên hóa đơn

- Bảng `invoice_item_text` (khóa `material_number`): `invoice_name`, `invoice_unit`, `stock_unit` (mặc định `PC`), nguồn (số hóa đơn PDF đã đọc hoặc "sửa tay"), người và lúc sửa.
- **Đọc PDF**: dùng `pdfplumber` lấy phần đầu (số hóa đơn, ký hiệu, ngày, DO, PO, tổng) và bảng dòng hàng. Kiểm PDF đúng đơn: DO = `sales_order.do_number`, PO = `platform_order_id`, số hóa đơn = `sap_tax_invoice.tax_invoice_doc`. Ghép dòng PDF với `sap_so_ref_item` theo thứ tự `item_no`; số dòng phải bằng nhau, số lượng từng dòng phải khớp, tiền từng dòng phải khớp tiền tính ra. Đúng hết thì ghi hoặc cập nhật master cho mọi vật tư của đơn, trong một giao dịch, ghi `event_log`.
- **Trang master**: danh sách, tìm theo mã hoặc tên, sửa tay (admin), hiện `sap_name` bên cạnh để soát. Theo mẫu trang `/report-names`.
- Nếu tên trong master khác tên trên một PDF mới tải lên, master lấy theo PDF mới và báo cho người dùng thấy tên cũ, tên mới.

## Thiết kế còn lại

**Dữ liệu (một migration).**
- `sap_tax_invoice`: thêm `net_value_vnd`, `tax_vnd` (nullable). `read_zrsd003` đọc thêm hai cột. Hóa đơn cũ chưa có giá trị thì trang lập phiếu chặn và cho xếp việc robot `read_zrsd003` theo tháng (cơ chế đang có).
- `invoice_item_text` như trên.
- `sales_return`: đơn (unique trong các phiếu chưa hủy, bằng partial unique index), lý do (`CANCEL`/`RETURN`), trạng thái (`ISSUED`/`VOID`), `doc_year`, `doc_seq` (duy nhất theo năm), `doc_no`, bản chụp hóa đơn (số, ký hiệu, ngày, net, tax, thuế suất), bản chụp người mua, file Word và Excel (`generated_file`), người và lúc phát hành, hủy, lý do hủy.
- `sales_return_line`: số dòng SO, mã vật tư, tên và ĐVT trên hóa đơn, SL trên hóa đơn, SL trả, đơn giá, thành tiền trước và sau.
- `document_counter` (`doc_type`, `year`, `next_seq`): khóa dòng `FOR UPDATE` khi phát hành. Số bắt đầu nhập một lần bằng lệnh `shoponline` khi triển khai (không có nút trên web để tránh sửa số giữa chừng).

Không lưu bản nháp: trang lập phiếu tính xem trước từ dữ liệu sống; Phát hành là một giao dịch (cấp số, ghi phiếu và dòng, sinh hai file, ghi `event_log`).

**Mã.** `src/shoponline/returns/` (tính số liệu, kiểm tra chặn, cấp số, phát hành, hủy), `importers/invoice_pdf.py` (đọc PDF Bkav), `exports/invoice_adjustment_doc.py`, `exports/return_request_workbook.py`, route và template trong `web/`, nút trên `order_detail.html`, hai mục mới trong sidebar (Phiếu trả hàng, Tên trên hóa đơn). Retention bỏ qua `generated_file` của phiếu trả hàng. Thêm thư viện `pdfplumber` và `docxtpl`.

**Mẫu.** Chép mẫu vào `src/shoponline/exports/templates/`: Word đổi chữ đỏ thành chỗ giữ chỗ Jinja và bảng hàng thành vòng lặp dòng (`docxtpl`); Excel chuyển một lần từ `.xls` sang `.xlsx`, chỉ giữ sheet `RRG ENGLISH`, điền bằng `openpyxl`.

## Trade-offs

**Nguồn tên hàng trên hóa đơn.** Người dùng chọn master nạp theo nhu cầu từ PDF.
- Phụ thuộc lớn nhất: tên trên Bkav cố định theo mã vật tư, và thứ tự dòng trên PDF trùng thứ tự `item_no` của SO.
- Hỏng đầu tiên khi: kế toán đổi tên vật tư trên Bkav (master cũ in tên cũ tới khi có PDF mới hoặc sửa tay), hoặc Bkav đổi bố cục PDF (parser từ chối, vẫn còn đường sửa tay trên trang master).
- So với tải PDF mỗi phiếu: ít bước tay hơn khi vật tư lặp lại, đổi lại phải thêm cột tiền zrsd003 và tự tính tiền theo dòng, nên có rủi ro làm tròn khác Bkav ở đơn nhiều dòng. Rủi ro này được kiểm mỗi lần có PDF.

**Sinh file Word.** `docxtpl` (đề xuất) phụ thuộc vào việc mỗi chỗ giữ chỗ nằm trọn trong một run, và hỏng khi ai đó sửa mẫu trong Word làm tách run; test đọc lại file sinh ra để bắt lỗi này. Phương án sửa OOXML tay không thêm thư viện nhưng phải tự viết nhân dòng bảng và gộp run.

**File Excel.** Giữ `.xls` đòi `xlwt`/`xlutils` đã ngừng phát triển; chuyển mẫu sang `.xlsx` có rủi ro mất logo hoặc thiết lập trang in, nên bước đầu của kế hoạch là chuyển, điền thử và in thử.

Better approaches: none — hướng chọn là việc người dùng yêu cầu (database, zrsd003 và master nạp từ PDF; đã kiểm đủ trường với hai đơn mẫu và PDF đọc được bằng `pdfplumber`).

## Rủi ro

- Tên trong master lỗi thời khi kế toán đổi tên trên Bkav.
- Hóa đơn cũ chưa có `net_value_vnd`, `tax_vnd`: cần đọc lại zrsd003 các tháng liên quan.
- Đơn giá chia lẻ khi số lượng > 1 và giá chưa thuế không chia hết; kiểm khi có PDF của đơn như vậy.
- `pdfplumber` kéo theo `pdfminer.six`, `pypdfium2`, `pillow`, `cryptography`.
