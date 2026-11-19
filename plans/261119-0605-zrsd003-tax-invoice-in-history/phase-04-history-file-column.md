---
phase: 4
title: "Chặn đơn chờ hóa đơn, cột 19, nút đọc"
status: completed
priority: P2
effort: "3h"
dependencies: [1, 3]
---

# Phase 4: Chặn đơn chờ hóa đơn, cột 19, nút đọc

## Goal
File Shop Online có cột 19 `Tax Invoice Doc.`; đơn chưa có hóa đơn bị chặn; trang có nút xếp robot đọc zrsd003 đúng khoảng ngày.

## Files to Create / Modify
- Modify: `src/shoponline/exports/sales_history_workbook.py` — `COLUMNS` thêm `"Tax Invoice Doc."` sau `"Mã đơn"`; `HistoryRow.tax_invoice_doc`; lý do mới `TAX_INVOICE = "tax_invoice"`; `collect_rows` tra `SapTaxInvoice` theo `order.do_number`; docstring module (19 cột).
- Modify: `src/shoponline/web/routes/sales_history.py` — `_fix_link` cho `TAX_INVOICE` (về chính trang, phần nút đọc); route `POST /sales-history/read-zrsd003` (`require_admin`) xếp `request_zrsd003`.
- Modify: `src/shoponline/web/templates/sales_history.html` — số đơn chờ hóa đơn, nút "Robot đọc zrsd003" (chỉ admin), link sang Báo cáo SAP để tải tay.
- Modify: `tests/exports/test_sales_history_workbook.py`, `tests/web/test_sales_history_routes.py`, `tests/sales_history_setup.py` (thêm hóa đơn cho đơn mẫu để test cũ vẫn xuất được).

## Tasks & Steps
1. `collect_rows`: một query lấy `SapTaxInvoice` cho mọi `do_number` của đơn chờ; thiếu thì `Reason(TAX_INVOICE, f"DO {do} chưa có Tax Invoice Doc.")`. Lý do này cộng thêm cùng các lý do khác, không thay chúng.
2. `build_history_workbook`: cột 19 ghi `row.tax_invoice_doc` dạng text (set `number_format = "@"` hoặc giữ chuỗi), cột 18 giữ nguyên.
3. Khoảng ngày cho nút: `date_from` = ngày đặt sớm nhất trong các đơn bị chặn vì `TAX_INVOICE`, `date_to` = `today_vn()`. Không có đơn chờ thì ẩn nút. Xếp job xong flash "Robot sẽ đọc zrsd003 từ … đến … (việc #N)".
4. Test: đơn có hóa đơn ra cột 19 đúng; đơn không có hóa đơn bị chặn và không tải được file; header 19 cột; khoảng ngày của nút đúng; viewer không xếp job.

## Verification
- `uv run pytest tests/exports/test_sales_history_workbook.py tests/web/test_sales_history_routes.py -q`
- `uv run pytest -q` và `uv run ruff check`

## Risks
- Đơn đã có DO trước khi tính năng chạy đều bị chặn tới khi đọc zrsd003 lần đầu: phase 5 chạy đọc một lần khoảng rộng trên production.
