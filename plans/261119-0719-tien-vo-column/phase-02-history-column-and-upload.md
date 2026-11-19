---
phase: 2
title: "Cột 20, mục chờ tiền vô và form upload"
status: completed
priority: P2
effort: "4h"
dependencies: [1]
---

# Phase 2: Cột 20, mục chờ tiền vô và form upload

## Goal
File Shop Online có cột 20 `Tiền Vô`; đơn Shopee/TikTok chưa có tiền vô ở mục riêng "Đơn chờ tiền vô" kèm form upload file quyết toán.

## Files to Create / Modify
- Modify: `src/shoponline/exports/sales_history_workbook.py` — `COLUMNS` thêm `"Tiền Vô"`; `MONEY_COLUMNS` thêm `"T"`; `HistoryRow.settlement: int | None`; lý do mới `SETTLEMENT = "settlement"`; hằng `SETTLED_PLATFORMS = ("SHOPEE", "TIKTOK")`; docstring module (20 cột).
- Modify: `src/shoponline/web/routes/sales_history.py` — tách đơn chỉ chờ tiền vô ra danh sách riêng; `_fix_link` cho `SETTLEMENT` → `#settlement`; số đơn chờ tiền vô và khoảng ngày cần export; route `POST /sales-history/settlement` (upload). **[Red team]**
- Modify: `src/shoponline/web/templates/sales_history.html` — hộp "Đơn chờ tiền vô" (số đơn, khoảng ngày, bảng, form upload); dòng tóm tắt và câu "Không có đơn nào chờ xuất" tính cả đơn chờ tiền vô. **[Red team]**
- Modify: `tests/sales_history_setup.py` — `order(..., settlement=AUTO)` thêm dòng quyết toán (kèm `ImportBatch` vì FK NOT NULL) cho đơn Shopee/TikTok để test cũ vẫn xuất.
- Modify: `tests/exports/test_sales_history_workbook.py` (gồm assert 19 cột hiện có), `tests/web/test_sales_history_routes.py`.

## Tasks & Steps
1. `collect_rows`: một query `SUM(amount)` nhóm theo `(platform, platform_order_id)` cho các đơn chờ. Đơn thuộc `SETTLED_PLATFORMS` không có dòng quyết toán nào thì thêm `Reason(SETTLEMENT, "Chưa có tiền vô")`, cộng cùng các lý do khác. Có dòng thì xuất với tổng, kể cả tổng 0 hoặc âm (đơn giao không thành công chỉ có "Tiền ra" -2.700 xuất -2.700; chủ dự án chốt 2026-11-19). Lazada: `settlement = None`. **[Red team]**
2. Dòng ra: dòng đầu của đơn (`line_no` nhỏ nhất, vòng lặp hiện đã theo thứ tự) có `settlement` = tổng; các dòng sau `None`.
3. `build_history_workbook`: cột 20 ghi `row.settlement` (trống khi `None`), định dạng `#,##0`.
4. Trang:
   - đơn có **mọi** lý do là `SETTLEMENT` hiện ở hộp "Đơn chờ tiền vô" (sàn, mã đơn, ngày đặt); đơn có lý do khác vẫn ở "Đơn bị chặn" và lý do "Chưa có tiền vô" link tới `#settlement`;
   - số đơn chờ tiền vô và khoảng ngày cần export từ sàn (ngày đặt sớm nhất tới hôm nay) tính trên **mọi** đơn có lý do `SETTLEMENT`, kể cả đơn đang ở "Đơn bị chặn" (như `waiting_invoice` / `_invoice_range`); **[Red team]**
   - dòng tóm tắt hiện cả số đơn chờ tiền vô; "Không có đơn nào chờ xuất" chỉ hiện khi không có đơn sẵn sàng, đơn bị chặn hay đơn chờ tiền vô; route tải file khi không có dòng nào cũng báo đúng như vậy; **[Red team]**
   - câu trên hộp: "Sàn quyết toán vài ngày sau khi giao; đơn tự vào lần tải sau khi đã upload file của sàn."
5. Form upload trong hộp (luôn hiện với admin, để upload trước khi có đơn chờ; bọc trong `{% if user.role == 'admin' %}` như các form admin khác): `<input type="file" accept=".xlsx">`, ghi chú nguồn file (Shopee: Số dư TK Shopee → Báo cáo giao dịch; TikTok: Tài chính → quyết toán, sheet "Chi tiết đơn hàng"; Lazada không dùng được). Quyền phía server: `require_admin` như upload zrsd003. **[Red team]**
6. Route upload: theo mẫu `upload_zrsd003` — `save_upload(kind="settlement", platform=None)` (`ingest_settlement` đặt `record.platform` sau khi nhận sàn), `ingest_settlement`. `FileRejected`/`UploadRejected` thì rollback, xóa file mới, hiện lỗi. **Lỗi bất kỳ khác** cũng rollback và xóa file mới rồi ném tiếp, để file gốc không nằm lại `uploads/`. Thành công thì commit, `retention.discard_unused` file gốc, flash "Tiền vô Shopee: N giao dịch của M đơn (x mới, y đổi, z không đổi), bỏ qua k dòng"; với TikTok kèm danh sách ID bỏ qua và đơn liên quan. Redirect về `/sales-history?until=…`. **[Red team]**
7. Test:
   - Shopee có tiền vô ra cột 20 ở dòng đầu, dòng 2 trống; header 20 cột; định dạng `#,##0`.
   - Đơn có hai dòng quyết toán (vào + ra) ra tổng; đơn tiền vô 0 xuất với 0; đơn chỉ có "Tiền ra" -2.700 xuất -2.700.
   - Shopee/TikTok không có tiền vô không trong file, ở hộp chờ; Lazada xuất với cột 20 trống.
   - Đơn thiếu tên khách và tiền vô ở "Đơn bị chặn" với cả hai lý do và vẫn được đếm trong số đơn chờ tiền vô.
   - Trang chỉ có đơn chờ tiền vô không hiện "Không có đơn nào chờ xuất". **[Red team]**
   - Upload file Shopee qua route: đơn chờ biến mất khỏi hộp và vào file; file Lazada báo lỗi; viewer bị từ chối và không thấy form; file gốc không còn, kể cả khi ingest ném lỗi không phải `FileRejected`. **[Red team]**

## Verification
- `uv run pytest tests/exports/test_sales_history_workbook.py tests/web/test_sales_history_routes.py -q`
- `uv run pytest -q` và `uv run ruff check`
- Mở `/sales-history` trên máy dev, upload `docs/tienvo/shopee.xlsx`, xem hộp chờ và file tải về.

## Risks
- Cột 20 nằm ngoài 19 cột kế toán đang dán; nếu sheet1 của kế toán chưa có header cột T thì họ thêm tay một lần, và bước sắp xếp phải chọn A:T (ghi ở docs, phase 3). **[Red team]**
- Tiền vô đổi sau khi đơn đã xuất và xác nhận dán (ví dụ Shopee ghi "Tiền ra" khi khách trả hàng) không được sửa hay báo lại; file đã xuất giữ số cũ. Nằm ngoài phạm vi ("điền tiền vô cho đơn đã xác nhận dán"); ghi ở docs. **[Red team]**
