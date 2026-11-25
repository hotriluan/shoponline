---
phase: 1
title: "Đọc file và tra số hóa đơn"
status: pending
priority: P1
effort: "4h"
dependencies: []
---

# Phase 1: Đọc file và tra số hóa đơn

## Goal

Một module thuần dữ liệu đọc file Excel 3 cột, tra từng số hóa đơn ra đúng một đơn Lazada và trả về từng dòng kèm lý do khi không lưu được, chưa có route hay giao diện.

## Bối cảnh

- Đường tra: số hóa đơn → `SapTaxInvoice.tax_invoice_doc` → `delivery` → `SalesOrder.do_number` → `platform_order_id` ([manual_settlement.py:205](../../src/shoponline/accounting/manual_settlement.py) tra theo chiều ngược lại). `tax_invoice_doc` không có ràng buộc duy nhất và không đệm số 0; giao diện dùng `zfill(8)` khi hiện.
- [excel_table.py](../../src/shoponline/importers/excel_table.py) đã có `read_table(source, required=...)` (nhận `BinaryIO`, từ chối file thiếu cột bằng `FileRejected`), `cell_text` (số thực nguyên `1234.0` thành `"1234"`, ô ngày thành `YYYY-MM-DD`) và `parse_money` (Decimal chặt, từ chối phần lẻ và số âm).
- Không dùng `manual.parse_amount` cho ô số thực: nó coi dấu chấm là dấu ngăn nghìn nên `1234.5` thành `12345`.
- Ghi chú dữ liệu test: `setup.order` mặc định tạo hóa đơn `"HD" + mã đơn` (không phải số) và DO `"80" + 8 ký tự cuối mã đơn` chỉ cho đơn `DELIVERED`. Test truyền `invoice="00001234"` để có số hóa đơn dạng thật.

## Thiết kế

Module mới `src/shoponline/accounting/settlement_invoice_file.py` (tách khỏi `manual_settlement.py` vì phần đọc Excel và phần tra DB cùng một chủ đề riêng, còn `manual_settlement` giữ phần lưu).

- `normalize_invoice(text) -> str`: cắt khoảng trắng, bỏ số 0 đầu (`lstrip("0")`). Dùng cho cả hai phía của phép so khớp; phía SQL dùng `func.ltrim(SapTaxInvoice.tax_invoice_doc, "0")`.
- `FileLine(line_no, invoice, amount, settled_on, error)`: `line_no` là số dòng trong Excel (`Row.number`).
- `read_file(data: bytes) -> list[FileLine]`: `read_table(BytesIO(data), required=("Số hóa đơn", "Ngày nhận tiền", "Số tiền"))`; ném `FileRejected` khi không đọc được hoặc thiếu cột. Dòng trống bị bỏ (đã có trong `read_sheet`). Mỗi dòng đọc riêng, lỗi nằm trong `error`:
  - hóa đơn trống: "Số hóa đơn trống".
  - ngày: nhận `YYYY-MM-DD` (ô ngày Excel; nếu có giờ thì lấy 10 ký tự đầu) hoặc `dd/mm/yyyy` (ô chữ, dùng `manual.parse_date`); khác thì "Ngày '…' không đúng dạng".
  - số tiền: trống là lỗi (khác `0`, được phép). Thử `parse_money` trước; nếu lỗi và chuỗi khớp `^\d{1,3}([.,\s]\d{3})+$` thì dùng `manual.parse_amount` (ô chữ kiểu `1.234.567`); còn lại báo lỗi của `parse_money`.
- `ResolvedLine(line: FileLine, order_id: str, error: str)`.
- `resolve(session, lines, today=None) -> list[ResolvedLine]`:
  1. Dòng đã có lỗi đọc giữ nguyên lỗi.
  2. Hóa đơn xuất hiện nhiều hơn một dòng trong file: mọi dòng đó lỗi "Hóa đơn trùng ở các dòng a, b".
  3. Một truy vấn `SapTaxInvoice` LEFT JOIN `SalesOrder` (điều kiện join: `do_number == delivery` và `platform == "LAZADA"`) với `ltrim(tax_invoice_doc,'0') IN (...)`. Không có hàng nào: "Hóa đơn {zfill(8)} chưa có trong dữ liệu SAP". Có hàng nhưng không có đơn: "Hóa đơn … không thuộc đơn Lazada nào". Nhiều đơn: "Hóa đơn … ứng với N đơn (a, b), không tự chia tiền".
  4. Đúng một đơn thì gọi `manual.check(session, order_id, amount, settled_on, today)`; `SettlementError` thành `error`.
  5. Hai hóa đơn khác nhau ra cùng một đơn: các dòng đó lỗi "Cùng đơn {id} ở các dòng a, b".
- `to_carry(lines) -> str` và `from_carry(text) -> list[FileLine]`: chuyển các dòng không lỗi đọc thành văn bản `line_no<TAB>hóa đơn<TAB>số tiền<TAB>YYYY-MM-DD` để form xem trước mang sang bước lưu; `from_carry` chặt (sai dạng thì ném `ValueError`). Dòng lỗi đọc không được mang theo vì không lưu được.

## Files to Create / Modify

- Create: `src/shoponline/accounting/settlement_invoice_file.py`
- Create: `tests/accounting/test_settlement_invoice_file.py`

## Tasks & Steps

- [ ] Viết `normalize_invoice`, `FileLine`, `read_file` với ba bộ đọc ô (hóa đơn, ngày, số tiền).
- [ ] Viết `resolve` với truy vấn một lần và các thông báo trên.
- [ ] Viết `to_carry` / `from_carry`.
- [ ] Test (dựng file `.xlsx` trong bộ nhớ bằng openpyxl; đơn Lazada bằng `setup.order(..., platform="LAZADA", invoice="00001234")`):
  - dòng hợp lệ ra đúng mã đơn và số tiền;
  - hóa đơn `1234`, `1234.0` (số), `"001234"` (chữ) đều khớp `00001234`;
  - ngày là ô ngày Excel và ô chữ `20/11/2026`; ngày tương lai, ngày trước ngày đặt đơn bị từ chối;
  - số tiền: `90000`, `90000.0`, `"1.234.567"`, `0` hợp lệ; trống, `-5`, `1234.5`, `abc` bị từ chối;
  - hóa đơn không có trong SAP; hóa đơn có trong SAP nhưng DO thuộc đơn Shopee hoặc chưa gắn đơn; hai đơn Lazada cùng DO (dựng tay) ra "ứng với 2 đơn";
  - hóa đơn trùng trong file; hai hóa đơn khác nhau cùng một đơn;
  - file thiếu cột, file không phải xlsx (`FileRejected`);
  - `to_carry` rồi `from_carry` trả lại đúng các dòng; chuỗi sai dạng ném `ValueError`;
  - một lần gọi `resolve` chỉ chạy một truy vấn tra hóa đơn (không phải mỗi dòng một truy vấn).

## Verification

- `uv run pytest tests/accounting/test_settlement_invoice_file.py tests/accounting/test_manual_settlement.py`
- `uv run ruff check src/shoponline/accounting tests/accounting`

## Risk

- `ltrim` là hàm chung của PostgreSQL và SQLite, nên test và dev chạy cùng một truy vấn; nếu test chạy trên DB khác thì xác nhận hàm có sẵn trước khi viết tiếp.
- Ô số có nhiều hơn 15 chữ số mất chính xác trong Excel: `cell_text` đã giữ dạng mũ cho số quá `2**53`, nên số hóa đơn bị hỏng như vậy không khớp và bị báo không có trong SAP, không lưu nhầm.

## Rollback

Xóa hai file mới; không có thay đổi schema hay dữ liệu.
