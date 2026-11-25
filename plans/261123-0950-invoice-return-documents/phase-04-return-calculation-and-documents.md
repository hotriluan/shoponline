---
phase: 4
title: "Tính tiền, cấp số, phát hành và sinh file"
status: completed
priority: P1
effort: "6h"
dependencies: [3]
---

# Phase 4: Tính tiền, cấp số, phát hành và sinh file

## Goal

Lõi nghiệp vụ không phụ thuộc web: dựng bản xem trước (hoặc danh sách lý do chặn), phát hành trong một giao dịch (cấp số, ghi phiếu, sinh hai file), và hủy phiếu.

## Context

- Hàm tính dòng hóa đơn `invoice_lines` (phase 3), bộ đếm (phase 2), mẫu (phase 1).
- Lưu file sinh ra: `save_generated` trong [uploads.py](../../src/shoponline/web/uploads.py) chỉ nhận workbook (`workbook.save`) và luôn ghi hậu tố `.xlsx`; bốn nơi gọi nó (`accounting/runs.py`, `web/routes/batches.py`, `web/routes/sales_history.py`, `tests/web/test_uploads.py`) giữ nguyên. Thêm hàm anh em `save_generated_bytes(session, settings, data, suffix, file_name, kind, actor)` cùng file; `accounting/runs.py` đã import `web.uploads` nên không phải tách lớp mới. Tải về chọn media type theo hậu tố (`.docx` → `application/vnd.openxmlformats-officedocument.wordprocessingml.document`).
- Ghi sự kiện: `states.log_event`. `event_log.detail` không chứa tên hay địa chỉ người mua (quy tắc ở `db/models.py`).
- Ngày phát hành luôn là `today_vn()`.
- Mẫu ký hiệu hóa đơn: `Settings.invoice_symbol_pattern` (phase 2), `yy` lấy từ `billing_date`.

## Files to Create / Modify

- Modify: `src/shoponline/web/uploads.py` (thêm `save_generated_bytes`)
- Modify: `src/shoponline/returns/amounts.py` (tính phần trả)
- Create: `src/shoponline/returns/service.py`
- Create: `src/shoponline/exports/invoice_adjustment_doc.py`
- Create: `src/shoponline/exports/return_request_workbook.py`
- Create: `tests/returns/test_service.py`, `tests/exports/test_invoice_adjustment_doc.py`, `tests/exports/test_return_request_workbook.py`

## Tasks & Steps

1. `amounts.returned(lines, selection, invoice)`:
   - Trả cả đơn (mọi dòng, đủ số lượng): `returned_net = net`, `returned_tax = tax` của zrsd003.
   - Trả một phần: `amount_i = round_half_up(net_i * return_qty_i, invoice_qty_i)` (đúng `net_i` khi trả đủ dòng, không phụ thuộc đơn giá làm tròn), `returned_tax = round_half_up(returned_net * vat_rate, 100)`.
   - Số trả mỗi dòng trong `[0, invoice_qty]`, có ít nhất một dòng > 0.
2. `service.build_preview(session, order_id, reason_kind, selection, buyer) -> Preview | Blocked`. Lý do chặn (mỗi lý do một câu tiếng Việt, kèm cách gỡ):
   - đơn không `DELIVERED` hoặc không có `do_number` (đơn hủy trước khi có DO thì không có hóa đơn nên ngoài phạm vi, theo người dùng);
   - không có `sap_tax_invoice` cho DO; tiền zrsd003 `NULL` (gỡ: xếp robot đọc lại zrsd003 tháng của `billing_date` bằng route riêng ở phase 5);
   - không suy ra được ký hiệu hóa đơn (mẫu cấu hình hỏng);
   - không có `sap_so_ref_item` cho SO;
   - các chặn của `invoice_lines`;
   - vật tư thiếu trong master (gỡ: tải PDF hóa đơn);
   - đơn đã có phiếu `ISSUED`;
   - dòng không có tên SAP: lấy `sales_order_item.sap_name` của đơn theo mã vật tư, không có thì `sku_mapping.sap_name` **lọc theo sàn của đơn** (`sku_mapping` duy nhất theo sàn, sản phẩm, biến thể, không theo mã vật tư nên có thể có nhiều dòng); nhiều dòng khác tên thì chặn; vẫn không có thì chặn;
   - tên hoặc địa chỉ người mua trống (lấy mặc định từ `customer_info`, người lập sửa được);
   - chưa nhập số bắt đầu.
   - `Preview.fingerprint`: băm của dòng (mã vật tư, tên hóa đơn, tên SAP, ĐVT, số lượng), số tiền, bản chụp hóa đơn, `delivery`, ký hiệu.
3. `service.issue(session, preview_input, actor) -> SalesReturn`: dựng lại preview trong cùng giao dịch (không tin dữ liệu gửi từ form ngoài lựa chọn, thông tin người mua và `fingerprint`). **Nếu fingerprint dựng lại khác fingerprint admin đã duyệt thì từ chối với "Dữ liệu đã đổi, xem lại bản nháp"** (cùng cách `StaleReview` ở `accounting/runs.py`). Thứ tự: cấp số; ghi và `flush` `sales_return` + `sales_return_line` **trước** khi ghi file (để partial unique index chặn bấm đúp mà chưa có file nào trên đĩa); render hai file; lưu bằng `save_generated_bytes` kind `invoice_adjustment` (`.docx`) và `return_request` (`.xlsx`) (tên file `BBDC <số> <mã đơn>.docx`, `RRG <số> <mã đơn>.xlsx`, ký tự `/` đổi thành `-`); ghi `event_log` `sales_return_issued`. Mọi file đã ghi bị xóa nếu bất kỳ bước nào sau đó lỗi (một `try` bao cả hai lần ghi), và route xóa nốt khi commit lỗi. Chỉ vi phạm partial unique index trên `sales_order_id` (kiểm `diag.constraint_name`) mới báo "đơn đã có phiếu"; lỗi khác của bộ đếm hay `doc_no` được ném nguyên.
4. `service.void(session, return_id, reason, actor)`: lý do bắt buộc, `status = VOID`, giữ số và file, `event_log` `sales_return_voided`.
5. `exports/invoice_adjustment_doc.py` — `render(sales_return) -> bytes` bằng `docxtpl` từ bản chụp đã lưu (không đọc dữ liệu sống, để tải lại luôn ra cùng nội dung):
   - Tiền định dạng `111.111`; dòng và tổng điều chỉnh mang `-`; số lượng điều chỉnh `-1`; số hóa đơn `zfill(8)`; ngày `dd/mm/yyyy`; `year` = năm phát hành; `vat_rate` số nguyên.
   - Nội dung "trước điều chỉnh" là mọi dòng hóa đơn; "điều chỉnh" là các dòng có số trả > 0.
   - `reason_text` / `order_ref_text` theo `reason_kind`.
   - **Escape:** `tpl.render(ctx, autoescape=True)`; bỏ ký tự điều khiển XML 1.0 không hợp lệ khỏi mọi chuỗi trước khi render (tên, địa chỉ người mua do người mua gõ trên sàn). Không bao giờ ghép chuỗi XML thủ công.
6. `exports/return_request_workbook.py` — `render(sales_return) -> bytes` bằng `openpyxl` từ mẫu: `H6` tên sàn; từ dòng 14, mỗi dòng trả một dòng (`C` STT, `D` **tên SAP** `sap_name` của dòng <!-- Updated: Validation Session 2 - Excel D14 dùng tên SAP -->, `N` số trả, `P` ĐVT kho, `AL` `KHÁCH HỦY ĐƠN` / `KHÁCH TRẢ HÀNG`); nhiều hơn một dòng thì chèn dòng, chép kiểu và gộp ô `D:M`, `T:X`, `BA:BI` của dòng 14. `insert_rows` của `openpyxl` chỉ dời giá trị ô, nên phải tự dời thêm: chiều cao dòng (`row_dimensions`), vùng gộp bên dưới, `print_area` và dòng in lặp. Văn bản (`sap_name`, `H6`) đi qua cùng bộ lọc chống công thức mà `exports/sales_history_workbook.py` đã dùng (ô bắt đầu bằng `=`, `+`, `-`, `@` được ghi như chuỗi). `No`, `Date` để trống.
7. Tests:
   - `test_service.py` (database, dữ liệu tự dựng theo đơn mẫu Shopee): preview trả cả đơn ra 111.111 / 8.889 / 120.000; mỗi lý do chặn; phát hành ghi đủ bảng và hai `generated_file`; phát hành lần hai bị chặn và không để lại file mồ côi trong `exports/`; hủy rồi phát hành lại nhận số mới; trả một phần đơn hai dòng; fingerprint khác (master đổi giữa lúc xem và lúc phát hành) bị từ chối; đơn kit có dòng con chỉ lập trên dòng cha; ký hiệu năm 2027 ra `1C27TAL`; `event_log.detail` không chứa tên người mua.
   - `test_invoice_adjustment_doc.py`: render rồi đọc lại bằng `python-docx`; không còn `{{`/`{%`; có đủ số biên bản, số hóa đơn `00008038`, `1C26TAL`, `-111.111`, `-120.000` (giá trị tổng hợp của đơn mẫu); đơn hai dòng có hai dòng ở mỗi bảng; **tên người mua chứa `& < > " '` và `</w:t>` vẫn mở được và đọc lại đúng nguyên văn**.
   - `test_return_request_workbook.py`: ô `H6`, `D14` = `V-09 REDDISH CLAY 2004 VN-0.8L`, `N14`, `P14`, `AL14`; đơn hai dòng có dòng 15 đúng, chữ "Note : Batch No…" bị đẩy xuống một dòng, **chiều cao dòng và `print_area` dời đúng**; tên SAP bắt đầu bằng `=` được ghi như chuỗi.
   - Cả hai test file so sánh với `tests/support/template_baseline.json` bằng `format_compare` (phase 1): một dòng thì không khác định dạng; hai dòng thì dòng thêm giống dòng mẫu và phần dưới chỉ dời xuống, không đổi định dạng.

## Verification

- `uv run pytest tests/returns tests/exports`
- Mở file sinh ra từ test (ghi tạm vào scratchpad) bằng Word và Excel, so với mẫu gốc.

## Risk Assessment

- **Đơn giá chia lẻ** khi `qty > 1` và `net_i` không chia hết: đơn giá làm tròn nhưng thành tiền giữ `net_i` (theo hóa đơn). Dấu hiệu sai: PDF đơn như vậy lệch ở phase 3. Xử lý: dừng và hỏi kế toán; không thêm nguồn đơn giá thứ hai (PDF không được lưu, master không có cột giá).
- Ghi file xảy ra trước commit: lỗi ở bất kỳ bước nào sau lần ghi file đầu tiên thì xóa mọi file đã ghi (một `try` bao cả hai lần ghi) và route xóa nốt khi commit lỗi.
- Đơn kit: Bkav in dòng cha nên chỉ dòng chính tham gia (phase 3); nếu hóa đơn kit thật cho kết quả khác thì dừng và hỏi.
