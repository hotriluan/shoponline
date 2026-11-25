---
phase: 3
title: "Đọc PDF hóa đơn và master tên trên hóa đơn"
status: completed
priority: P1
effort: "5h"
dependencies: [2]
---

# Phase 3: Đọc PDF hóa đơn và master tên trên hóa đơn

## Goal

Đọc PDF hóa đơn Bkav, kiểm đúng đơn, ghi tên hàng và ĐVT vào master `invoice_item_text`; có trang master để xem và sửa tay.

## Context

- `pdfplumber` `extract_tables()` trên PDF mẫu cho bảng hàng sạch `['1', 'SƠN V-09 REDDISH CLAY 2004 VN', 'LON 0.8 LT', '1', '111.111', '111.111']` và ô đầu trang chứa `Mẫu số - Ký hiệu: 1C26TAL`, `Số: 00008038`, `Ngày 17 tháng 11 năm 2026`, `Số DO: …`, `Số PO: …`, người mua, địa chỉ; các ô `Cộng tiền hàng: 111.111`, `Thuế suất GTGT: 8% Tiền thuế GTGT: 8.889`, `Tổng cộng tiền thanh toán: 120.000`.
- Mẫu trang master: [report_names.py](../../src/shoponline/web/routes/report_names.py) + `report_names.html` (lưu tất cả hoặc không, giữ giá trị đã gõ khi lỗi).
- Dòng SO của SAP: `sap_so_ref_item` (`item_no`, `material_number`, `quantity`, `net_value_incl`) qua `sap_so_ref.so_number = sales_order.so_number`.

## Files to Create / Modify

- Create: `src/shoponline/returns/money.py` (`round_half_up` bằng `Decimal`, `format_vnd`)
- Create: `src/shoponline/returns/amounts.py` (chỉ phần tính tiền dòng hóa đơn; phase 4 mở rộng)
- Create: `src/shoponline/importers/invoice_pdf.py`
- Create: `src/shoponline/returns/master.py`
- Create: `src/shoponline/web/routes/invoice_texts.py`, `src/shoponline/web/templates/invoice_texts.html`
- Modify: `src/shoponline/web/app.py` (gắn router), `src/shoponline/web/templates/_nav.html` (mục "Tên trên hóa đơn" trong nhóm "Dữ liệu gốc")
- Create: `tests/importers/test_invoice_pdf.py`, `tests/returns/test_amounts.py`, `tests/returns/test_master.py`, `tests/web/test_invoice_texts_routes.py`

## Tasks & Steps

0. `returns/money.py`: một hàm `round_half_up(numerator, denominator) -> int` thuần số nguyên/`Decimal` (không dùng `round()` của Python, vốn làm tròn nửa chẵn, và không dùng `/` float). Mọi chỗ làm tròn tiền trong `returns/` đều gọi hàm này.
1. `returns/amounts.py` — `invoice_lines(items, net, tax) -> InvoiceLines | Blocked`:
   - **Dòng kit:** Bkav in dòng cha (người dùng xác nhận), nên `items` chỉ gồm dòng chính (`so_link.is_main_line(item_no)`); dòng con của kit (`item_no` 11, 12…) bị bỏ qua ở mọi bước (ghép PDF, tổng, chia tiền, tên SAP). Tổng kiểm `sum(net_value_incl)` chỉ cộng dòng chính; không khớp `net + tax` thì chặn như thường.
   - `vat_rate = round_half_up(tax * 100, net)`; chặn nếu `|net * vat_rate / 100 - tax| > số dòng`.
   - Chặn nếu `sum(net_value_incl) != net + tax` (SO đổi sau hóa đơn).
   - `net_i = round_half_up(net_value_incl_i * 100, 100 + vat_rate)`; dồn phần lệch với `net` vào dòng có `net_i` lớn nhất; lệch quá số dòng thì chặn.
   - `unit_price_i = round_half_up(net_i, qty_i)` (số lượng là `Decimal`). `unit_price_i * qty_i` có thể khác `net_i`; **thành tiền của dòng luôn là `net_i`** khi trả đủ dòng, đơn giá chỉ để hiển thị.
2. `importers/invoice_pdf.py`:
   - `read_invoice_pdf(source: bytes | Path) -> InvoicePdf` gọi `pdfplumber`, chuyển các bảng thành `list[list[str|None]]` rồi gọi `parse_invoice(tables)`. Trước khi parse: byte đầu phải là `%PDF-`; chặn PDF quá 5 trang hoặc quá 5 MB; đây là file không tin cậy nên việc gọi hàm này phải chạy ngoài vòng lặp sự kiện có thời hạn (route ở phase 5 dùng `run_in_threadpool` kèm timeout).
   - `parse_invoice(tables)` là hàm thuần: tìm dòng tiêu đề `STT | Tên hàng hóa, dịch vụ | …`, bỏ dòng `1 | 2 | 3 …`, đọc các dòng có STT là số; bóc phần đầu bằng regex (ký hiệu, số, ngày, DO, PO, người mua, địa chỉ, cộng tiền hàng, thuế suất, tiền thuế, tổng). Số tiền kiểu `111.111` (chấm hàng nghìn) và chấp nhận phần thập phân `,dd` (đơn giá lẻ như `55.555,5`). Tên và ĐVT hàng: không rỗng, tối đa 200 ký tự, không có ký tự điều khiển. Thiếu trường bắt buộc → `FileRejected` với danh sách lỗi tiếng Việt; thông báo lỗi chỉ nêu tên trường và số, **không in tên hay địa chỉ người mua** (vào log và flash).
   - File không phải PDF hoặc PDF scan (không có chữ) → `FileRejected("Không đọc được hóa đơn …")`.
3. `returns/master.py`:
   - `missing_materials(session, order) -> list[str]`.
   - `learn_from_pdf(session, order, pdf, actor, confirm_overwrite=False) -> LearnResult`:
     - Kiểm `pdf.do == order.do_number`, `pdf.po == order.platform_order_id`, `int(pdf.number) == int(tax_invoice.tax_invoice_doc)`, ký hiệu `pdf.symbol` bằng ký hiệu suy ra từ cấu hình (phase 4) — lệch thì từ chối.
     - **Bắt buộc có tiền zrsd003** (`net_value_vnd`, `tax_vnd` khác `NULL`); chưa có thì từ chối với hướng dẫn đọc lại zrsd003. Không có nhánh so "tổng" yếu hơn.
     - Số dòng PDF bằng số dòng chính của `sap_so_ref_item`; theo thứ tự `item_no`, số lượng bằng nhau và tiền dòng PDF bằng `net_i` của `invoice_lines`. Thứ tự lệch thì từ chối (không ghép theo cặp).
     - Đúng hết thì: vật tư **chưa có** trong master được thêm (`source` = số hóa đơn). Vật tư **đã có** mà tên hoặc ĐVT khác thì không ghi đè; trả danh sách khác biệt (cũ → mới) để route hiện bản xác nhận; chỉ khi `confirm_overwrite=True` (lần POST thứ hai, admin bấm xác nhận) mới ghi đè, kể cả dòng `source = manual`. Ghi `event_log` `invoice_text_learned` với mã vật tư, tên sản phẩm cũ/mới (không có tên khách).
     - Sai thì `FileRejected` liệt kê từng chỗ lệch bằng số và tên trường, không ghi gì.
4. Trang `/invoice-texts`: liệt kê mọi vật tư trong `sku_mapping` (mã, `sap_name`, tên trên hóa đơn, ĐVT hóa đơn, ĐVT kho, nguồn, người sửa); lọc "chưa có"; admin sửa và lưu theo kiểu all-or-nothing của `/report-names` (đủ tên và ĐVT hóa đơn mới lưu, `source = manual`).
5. Tests:
   - `test_invoice_pdf.py`: `parse_invoice` với bảng tự dựng (một dòng, hai dòng, số lượng > 1 với đơn giá lẻ `55.555,5`, thiếu số DO, số tiền sai định dạng, tên chứa ký tự điều khiển). Một test đọc PDF thật chạy khi có biến môi trường `SHOPONLINE_SAMPLE_INVOICE_PDF`, bỏ qua khi không có (PDF thật chứa dữ liệu khách, không vào repo). Trước khi nghiệm thu phase này cần thêm ít nhất một hóa đơn thật nhiều dòng và một hóa đơn số lượng > 1 chia không hết; lưu bảng đã ẩn danh (đổi tên) làm fixture chạy mọi lần. PDF không phải `%PDF-`, PDF > 5 trang bị từ chối.
   - `test_money.py`/`test_amounts.py`: `round_half_up(5, 2) == 3`, `round_half_up(25, 10) == 3`; 120000 → 111111 / 8889 / 8%; trường hợp nửa ở thuế 10% và 5%; hai dòng có lệch làm tròn được dồn; tổng SO lệch thì chặn; thuế suất không nguyên thì chặn; SO kit có dòng con: dòng con bị bỏ qua và chỉ dòng cha được ghép, chia tiền.
   - `test_master.py` (database): PDF đúng đơn ghi master; DO sai, PO sai, số hóa đơn sai, ký hiệu sai, số dòng khác, số lượng khác, thiếu tiền zrsd003 đều bị từ chối và master không đổi; vật tư đã có với tên khác không bị ghi đè khi chưa xác nhận, ghi đè khi `confirm_overwrite=True`; dòng `manual` được bảo vệ như vậy.
   - `test_invoice_texts_routes.py`: viewer xem được, không lưu được; lưu dở dang bị từ chối cả lô.

## Verification

- `uv run pytest tests/importers/test_invoice_pdf.py tests/returns tests/web/test_invoice_texts_routes.py`
- Chạy tay: `SHOPONLINE_SAMPLE_INVOICE_PDF=docs/bbdchd/hd_shopee.pdf uv run pytest tests/importers/test_invoice_pdf.py` đạt với cả hai PDF mẫu.

## Risk Assessment

- **Thứ tự dòng PDF khác thứ tự `item_no`.** Dấu hiệu: đơn nhiều dòng bị từ chối dù đúng đơn. Xử lý: từ chối và để admin sửa tay trên trang master; không thêm thuật toán ghép (chưa có yêu cầu).
- **Bkav đổi bố cục PDF.** Dấu hiệu: `FileRejected` với PDF mới. Xử lý: admin sửa tay master; sửa parser trong lần thay đổi sau.
- **Tên dài xuống hai dòng trong ô.** `pdfplumber` trả `\n` trong ô; gộp bằng một dấu cách.
- PDF là file không tin cậy: chỉ admin tải lên, giới hạn 5 MB và 5 trang, kiểm `%PDF-`, parse ngoài vòng lặp sự kiện có timeout, `pdfminer.six` ghim bản vá. Ứng dụng không ghi PDF vào kho file, nhưng máy chủ web (Starlette/python-multipart) có thể spool upload > 1 MB ra file tạm của hệ điều hành trước khi route chạy; tài liệu ghi đúng như vậy (phase 6).
