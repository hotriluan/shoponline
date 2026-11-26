---
phase: 3
title: "File Shop Online: dòng âm và dòng đảo"
status: completed
priority: P1
effort: "1.5d"
dependencies: [1, 2]
---

# Phase 3: File Shop Online: dòng âm và dòng đảo

## Goal

File Shop Online có dòng âm cho phiếu trả hàng và dòng đảo khi hủy phiếu, để SUM cả file là giá trị bán thật và số đơn thật.

## Context

- File chính dựng lại từ đầu mỗi lần tải (`collect_rows`). Đơn trong file được ghi ở `sales_history_file_order`; xác nhận đã dán ghi `sales_history_exported` (`web/routes/sales_history.py`: `confirm_file`, `unconfirm_file`, `delete_file`, `_unconfirmed_files_holding`).
- Cột H, I là công thức của kế toán; cột I đếm giao dịch.

## Files to Create / Modify

- Modify: `src/shoponline/exports/sales_history_workbook.py`
- Modify: `src/shoponline/web/routes/sales_history.py`
- Modify: `src/shoponline/web/templates/sales_history.html` (đếm dòng trả đang chờ)
- Modify: `tests/exports/test_sales_history_workbook.py`, `tests/web/test_sales_history_routes.py`, `tests/sales_history_setup.py`

## Rules

- **Dòng âm (ISSUE)** của phiếu `ISSUED` (hoặc `VOID` mà ISSUE đã dán, xem dòng đảo) ra khi: chưa có `sales_return_history_exported(return_id, ISSUE)`, và đơn của phiếu đã có `sales_history_exported` hoặc có mặt trong chính file này.
- **Dòng đảo (VOID)** ra khi phiếu `VOID`, ISSUE đã dán, VOID chưa dán.
- Phiếu `VOID` mà ISSUE chưa dán: không ra dòng nào.
- Mỗi dòng âm hoặc dòng đảo lấy từ `sales_return_sale_line`, một dòng cho mỗi dòng sàn: tên khách, tỉnh, tên báo cáo, size, variation, mã đơn, `Tax Invoice Doc.` như dòng gốc; `createTime`, `month`, `year` theo ngày đặt đơn gốc; `Quantity` và `Customer paid` âm (đảo thì dương); `unitPrice` như dòng gốc; `Tiền Vô` trống.
- Cột I: dòng đầu của phiếu trả cả đơn ghi −1 (đảo: +1); các dòng khác ghi 0. Cột H vẫn là công thức.
- Thứ tự: các dòng bán theo thứ tự hiện tại, sau đó các dòng trả theo số biên bản.
- Đơn có phiếu trả cả đơn đang `ISSUED` thì không bị chặn vì "Chưa có tiền vô" (sàn có thể không bao giờ trả tiền cho đơn đã hủy). Các lý do chặn khác giữ nguyên.

## Tasks & Steps

1. `HistoryRow` thêm `transaction: int | None` (None = dùng công thức) và `return_doc: str | None`. `build_history_workbook` ghi hằng số vào cột I khi `transaction` khác None.
2. `collect_rows` trả thêm `return_rows` và `return_ids: list[tuple[int, str]]` (phiếu, loại). Tính sau khi đã biết `order_ids` của file để áp quy tắc "đơn đã dán hoặc cùng file".
3. Dòng trả không bị chặn bởi thiếu dữ liệu khách hay tên báo cáo, vì đơn gốc đã qua các kiểm tra đó khi dán. Nếu dữ liệu đã bị xóa theo retention thì lấy lại từ dòng gốc có trong `sales_return` (tên người mua) và `report_item_name`; thiếu nữa thì chặn phiếu đó và ghi lý do vào danh sách chặn.
4. `download_history_file`: tải được khi chỉ có dòng trả (không có đơn mới). Ghi `sales_history_file_return` cho từng `(return_id, kind)`.
5. `confirm_file`: ghi thêm `sales_return_history_exported` từ `sales_history_file_return` (bỏ qua trùng). Xóa file chưa xác nhận khác chứa cùng `(return_id, kind)`, giống cách làm với đơn.
6. `unconfirm_file`: xóa luôn `sales_return_history_exported` của file. Nếu gỡ một file mà dòng đảo của phiếu đó đã xác nhận ở file sau thì từ chối, nêu file sau phải gỡ trước.
7. `delete_file` và `_unconfirmed_files_holding`: xét cả `sales_history_file_return`.
8. File NHÁP: thêm dòng trả, cột Trạng thái ghi "Hủy đơn / Trả hàng (cả đơn / một phần) – biên bản …". File TẤT CẢ ĐƠN: cột Trạng thái của dòng đơn có nhãn từ `returns.flags`, và có thêm dòng trả theo ngày đặt đơn trong khoảng (đánh dấu đã dán hay chưa).
9. Trang File Shop Online: hiện số dòng trả đang chờ dán.

## Verification

- `uv run pytest tests/exports/test_sales_history_workbook.py tests/web/test_sales_history_routes.py -q`
- Kịch bản test:
  - phiếu lập trước khi dán (cùng file có dòng gốc và dòng âm; SUM J = 0; SUM I = 0);
  - trả một phần sau khi dán (file sau chỉ có dòng âm; cột I = 0);
  - hủy phiếu sau khi dòng âm đã dán (dòng đảo; I = +1 nếu trả cả đơn);
  - hủy phiếu trước khi dòng âm được dán (không có dòng);
  - đơn chưa dán vì chờ hóa đơn khi lập phiếu: không có dòng âm đứng một mình;
  - Shopee trả cả đơn, không có tiền vô: không bị chặn;
  - xác nhận, gỡ xác nhận, xóa file, hai file chưa xác nhận chứa cùng phiếu;
  - tên khách có `=` ở dòng âm không thành công thức.
- Mở file sinh ra bằng openpyxl: cột I của dòng trả là số, không phải công thức.

## Risks

- Quy tắc theo dõi đã dán của phiếu phải soi gương đúng quy tắc của đơn. Viết test cho từng nhánh của confirm, unconfirm, delete trước khi sửa route.
