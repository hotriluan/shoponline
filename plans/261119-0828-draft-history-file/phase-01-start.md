---
phase: 1
title: "Dựng dòng nháp, route và nút tải"
status: completed
priority: P2
effort: "2.5h"
dependencies: []
---

# Phase 1: Dựng dòng nháp, route và nút tải

## Goal

`/sales-history/draft` trả về file nháp gồm đơn đủ dữ liệu và đơn chỉ còn chờ hóa đơn hoặc tiền vô, có cột 21 `Trạng thái`, và không ghi gì vào DB hay đĩa.

## Files to Create / Modify

- Modify: `src/shoponline/exports/sales_history_workbook.py`
- Modify: `src/shoponline/web/routes/sales_history.py`
- Modify: `src/shoponline/web/templates/sales_history.html`
- Modify: `tests/exports/test_sales_history_workbook.py`
- Modify: `tests/web/test_sales_history_routes.py`

## Tasks & Steps

1. **Workbook module** (`sales_history_workbook.py`):
   - Thêm `DRAFT_LABELS = {TAX_INVOICE: "Chờ hóa đơn", SETTLEMENT: "Chờ tiền vô"}`. Các loại lý do có trong bảng này là loại nháp chấp nhận.
   - `HistoryRow.tax_invoice_doc` đổi thành `str | None`. Thêm `status: str = ""`.
   - `collect_rows(session, until, draft=False)`:
     - Khi `draft` bật và mọi lý do của đơn đều nằm trong `DRAFT_LABELS`, đơn vẫn được dựng dòng như đơn đủ: `tax_invoice_doc=None` nếu thiếu hóa đơn, `settlement=None` nếu thiếu tiền vô.
     - `status` ghi các nhãn nối bằng `"; "`, theo thứ tự hóa đơn rồi tiền vô.
     - Đơn đó không vào `order_ids` và không vào `blocked`.
     - Khi `draft` tắt, hành vi giữ nguyên từng dòng.
   - `build_history_workbook(rows, draft=False)`: khi `draft` bật thì thêm tiêu đề `Trạng thái` ở cột 21 và ghi `row.status or None`. Cột S trống khi `tax_invoice_doc` là `None`.
   - Thêm `history_draft_file_name(day)` trả về `f"NHÁP {history_file_name(day)}"`, tức `NHÁP SHOP ONLINE LỊCH SỬ ddmmyy.xlsx`.
   - Cập nhật docstring đầu module bằng một câu về file nháp.
2. **Route** (`sales_history.py`): thêm `GET /sales-history/draft?until=` với `current_user`, giống file thật.
   - Gọi `collect_rows(db, until, draft=True)`.
   - Không có dòng nào: flash `"Không có đơn nào để xuất nháp."` (loại `error`) rồi redirect về `/sales-history?until=...`.
   - Có dòng: ghi workbook vào `BytesIO` và trả `Response` với media type `XLSX`, kèm header `Content-Disposition: attachment; filename*=utf-8''<quote(name)>`.
   - Không gọi `save_generated` và không thêm `SalesHistoryFileOrder`.
3. **Trang** (`sales_history_page` và `sales_history.html`):
   - Tính `draft_orders` = số đơn đủ (`len(result.order_ids)`) cộng số đơn trong `result.blocked` mà mọi lý do thuộc `DRAFT_LABELS`. Dùng lại một helper, không lặp điều kiện.
   - Khi `draft_orders` khác 0, hiện link `secondary` **Tải file nháp** cạnh **Tải file**, hoặc đứng một mình khi chưa có dòng sẵn sàng.
   - Thêm một dòng `muted`: "Nháp để kiểm tra, gồm cả đơn chờ hóa đơn hoặc tiền vô (cột Trạng thái). Không dán nháp vào file lịch sử; nháp không có trong bảng File đã tải."
4. **Test workbook** (dùng `tests/sales_history_setup.py`):
   - Có bốn đơn: đủ, chờ hóa đơn, chờ tiền vô, thiếu tên báo cáo. Với `draft=True`, các dòng gồm ba đơn đầu, đúng `status`, và `tax_invoice_doc`/`settlement` là `None` ở đơn còn thiếu.
   - Với `draft=False`, kết quả giữ như cũ.
   - Đơn chờ cả hai có status `Chờ hóa đơn; Chờ tiền vô`.
   - Workbook nháp có 21 cột, tiêu đề T21 `Trạng thái`. Workbook thật vẫn 20 cột.
5. **Test route**:
   - Tải nháp: mở được bằng openpyxl; tên file giải mã bằng `unquote` khớp `NHÁP SHOP ONLINE LỊCH SỬ`; `generated_file` và `sales_history_file_order` không đổi số dòng.
   - Chỉ có đơn chờ: nháp tải được, file thật vẫn redirect kèm flash cũ.
   - Không có đơn nào: nháp redirect kèm flash mới.
   - Tài khoản xem tải được nháp.
   - Trang hiện link **Tải file nháp** khi có đơn chờ, và không hiện khi chỉ có đơn bị chặn vì tên báo cáo.

## Verification

- `uv run pytest tests/exports/test_sales_history_workbook.py tests/web/test_sales_history_routes.py`
- `uv run pytest`
- `uv run ruff check`

## Risk & Rollback

- Rủi ro chính là làm lệch file thật vì hai đường đi chung code. Test file thật hiện có phải chạy qua mà không sửa test.
- Rollback: revert commit. Không có migration và không có dữ liệu mới.
