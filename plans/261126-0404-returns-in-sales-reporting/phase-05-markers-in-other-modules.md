---
phase: 5
title: "Nhãn ở các module khác"
status: completed
priority: P2
effort: "0.5d"
dependencies: [2]
---

# Phase 5: Nhãn ở các module khác

## Goal

Ở mọi module có danh sách đơn liên quan, người dùng thấy ngay đơn đã hủy hoặc trả hàng, kèm số biên bản.

## Files to Create / Modify

- Modify: `src/shoponline/web/templates/_macros.html` (một macro hiện nhãn)
- Modify: `src/shoponline/web/routes/batches.py`, `src/shoponline/web/templates/batch_detail.html`
- Modify: `src/shoponline/web/routes/settlements.py`, `src/shoponline/web/templates/lazada_settlements.html`
- Modify: `src/shoponline/web/routes/accounting.py`, `src/shoponline/web/templates/accounting_run.html` (và `accounting_preview.html` nếu có danh sách DO)
- Modify: `src/shoponline/web/routes/returns.py` hoặc `returns.html` nếu cần liên kết ngược tới đơn
- Modify: các test route tương ứng trong `tests/web/`

## Tasks & Steps

1. Macro `return_flag(flag)` hiển thị nhãn và số biên bản, liên kết tới trang phiếu. Admin thấy liên kết; viewer chỉ thấy nhãn (trang phiếu chỉ cho admin xem tên người mua).
2. Danh sách đơn của lô: gọi `flags.of` một lần cho cả trang, hiện nhãn cạnh trạng thái.
3. Tiền về Lazada:
   - danh sách chờ nhập tiền và bảng xem trước (dán và tải file theo số hóa đơn) hiện nhãn;
   - đơn có phiếu trả cả đơn: dòng xem trước có cảnh báo "Đơn đã hủy hoặc trả cả đơn", vẫn cho lưu (sàn có thể vẫn trả một phần tiền).
4. Đợt gửi kế toán: trang xem trước và trang đợt liệt kê DO thuộc đơn có phiếu trả (nhãn, số biên bản). Chỉ để báo, không đổi nội dung file gửi kế toán.
5. Trang Hôm nay: nếu có bảng đơn thì hiện nhãn. Nếu chỉ có số tổng thì không đổi.
6. Rà các trang danh sách đơn còn lại (tìm theo `order_detail` link) và thêm nhãn ở mỗi chỗ có trạng thái đơn.

## Verification

- `uv run pytest tests/web -q`
- Test route: lô có một đơn trả cả đơn hiện "Hủy sau HĐ" và số biên bản; hủy phiếu thì nhãn mất; Lazada xem trước có cảnh báo; trang đợt kế toán liệt kê DO có phiếu.
- Viewer không thấy liên kết tới phiếu.

## Risks

- Truy vấn nhãn theo từng đơn làm chậm trang dài: luôn gọi `flags.of` một lần cho cả danh sách.
