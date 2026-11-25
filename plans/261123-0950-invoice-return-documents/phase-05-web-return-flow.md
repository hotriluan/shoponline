---
phase: 5
title: "Luồng web lập phiếu trả hàng"
status: completed
priority: P1
effort: "6h"
dependencies: [4]
---

# Phase 5: Luồng web lập phiếu trả hàng

## Goal

Admin lập, xem trước, phát hành, tải lại và hủy phiếu trả hàng trên web; retention không xóa phiếu và file của nó.

## Context

- Trang đơn: [orders.py](../../src/shoponline/web/routes/orders.py), `order_detail.html`. Quyền: `require_admin` cho thao tác ghi, `current_user` cho xem.
- Mẫu tải file: `download_final_file` trong [accounting.py](../../src/shoponline/web/routes/accounting.py) (dùng `current_user`; route trả hàng dùng `require_admin` vì file chứa tên và địa chỉ người mua).
- Xếp robot đọc zrsd003 theo tháng: `request_zrsd003`, `split_range` ở [report_requests.py](../../src/shoponline/sapjobs/report_requests.py). Route `/sales-history/read-zrsd003` tính khoảng ngày từ các đơn đang chờ Tax Invoice nên không dùng được cho đơn đã có hóa đơn; phase này thêm route riêng.
- Giữ file: `kept_files` trong [retention.py](../../src/shoponline/maintenance/retention.py). Sao lưu: `_copy_accounting_files` trong [archive.py](../../src/shoponline/backup/archive.py) chỉ chép kind `accounting_file`.

## Files to Create / Modify

- Create: `src/shoponline/web/routes/returns.py`
- Create: `src/shoponline/web/templates/return_form.html`, `returns.html`, `return_detail.html`
- Modify: `src/shoponline/web/app.py`, `src/shoponline/web/templates/_nav.html` (mục "Phiếu trả hàng" trong nhóm "Kế toán")
- Modify: `src/shoponline/web/routes/orders.py`, `src/shoponline/web/templates/order_detail.html`
- Modify: `src/shoponline/maintenance/retention.py`, `src/shoponline/backup/archive.py`
- Create: `tests/web/test_returns_routes.py`; Modify: `tests/maintenance/` (test giữ file), `tests/backup/` (test sao lưu chép file phiếu)

## Tasks & Steps

1. `order_detail.html`: khối "Trả hàng". Đơn đã có phiếu `ISSUED` → link tới phiếu. Đơn `DELIVERED` có hóa đơn → nút "Lập phiếu trả hàng" (admin). Còn lại không hiện.
2. `GET /orders/{id}/return`: form gồm lý do (hủy đơn / trả hàng), bảng dòng (tên trên hóa đơn, ĐVT, SL hóa đơn, ô số trả mặc định bằng SL hóa đơn), tên và địa chỉ người mua (điền sẵn từ `customer_info`), trường ẩn `fingerprint` của bản xem trước, và bảng xem trước tiền (trước điều chỉnh, điều chỉnh, thuế, tổng). Khi bị chặn, hiện từng lý do kèm hành động:
   - thiếu master → form tải PDF hóa đơn (`POST /orders/{id}/return/invoice-pdf`);
   - thiếu tiền zrsd003 → nút `POST /orders/{id}/return/read-zrsd003` (admin): gọi `request_zrsd003(db, target, first, last, actor)` với khoảng là tháng của ngày hóa đơn, kèm kiểm `robot_refusal` như route của `sales_history`; có link tải file ở `/sap-reports`;
   - chưa nhập số bắt đầu → hướng dẫn lệnh CLI cho admin.
   Thay đổi lựa chọn (lý do, số trả) gửi lại bằng GET để làm mới xem trước; không lưu nháp.
3. `POST /orders/{id}/return/invoice-pdf` (admin): từ chối sớm theo `Content-Length` > 5 MB, đọc file, gọi `read_invoice_pdf` qua `run_in_threadpool` với timeout, rồi `learn_from_pdf`. Nếu có tên hoặc ĐVT khác master thì **không ghi**, hiện bảng cũ → mới với nút xác nhận gửi `confirm_overwrite=1` (POST thứ hai kèm lại PDF); commit, flash kết quả, quay lại form. Không lưu PDF vào kho file (máy chủ có thể spool tạm, xem phase 3). Thông báo lỗi không chứa tên hay địa chỉ người mua.
4. `POST /orders/{id}/return` (admin): gọi `service.issue` kèm `fingerprint`, commit, chuyển tới `/returns/{rid}`. Bị chặn hoặc fingerprint lệch thì quay lại form với lý do; commit lỗi thì xóa file đã ghi.
5. `GET /returns`: danh sách phân trang (số biên bản, ngày, sàn, mã đơn, số hóa đơn, lý do, tổng điều chỉnh, trạng thái), tìm theo số biên bản, mã đơn, số hóa đơn. Dùng `pagination.py` và `table_tools.html` như các trang khác.
6. `GET /returns/{rid}`: chi tiết, hai nút tải (`/returns/{rid}/docx`, `/returns/{rid}/xlsx`), form hủy với lý do (admin). **Tải file chỉ admin** (`require_admin`), media type theo hậu tố. Viewer xem được danh sách và chi tiết nhưng chi tiết ẩn tên và địa chỉ người mua.
7. Độ bền của phiếu và file:
   - `retention.kept_files`: giữ mọi `generated_file` được `sales_return.docx_file_id` hoặc `xlsx_file_id` trỏ tới (luật theo dữ liệu, không theo danh sách kind trong mã), nên revert mã không làm sweep xóa phiếu đã phát hành. Việc xóa `customer_info` không đổi (phiếu đã có bản chụp).
   - `backup/archive.py`: `_copy_accounting_files` chép thêm hai kind `invoice_adjustment`, `return_request` để bản sao lưu `db` hằng ngày có file phiếu.
   - Quy trình: không revert phase này hay `downgrade` migration `0012` trên máy chạy thật khi đã có phiếu mà chưa sao chép tay thư mục `exports/` các file phiếu (ghi ở phase 6).
8. Tests `test_returns_routes.py`: viewer thấy danh sách nhưng không lập, không tải PDF, không hủy, **không tải được file phiếu**, không thấy tên người mua; luồng đầy đủ với dữ liệu tự dựng (form → tải PDF giả qua monkeypatch `read_invoice_pdf` → phát hành → tải hai file → hủy); lý do chặn hiển thị đúng; tải file quá cỡ bị từ chối; PDF khác tên master hiện bản xác nhận và chưa ghi; route đọc lại zrsd003 xếp đúng tháng cho đơn đã có hóa đơn; fingerprint lệch bị từ chối. `tests/maintenance`: file được phiếu trỏ tới không bị sweep xóa kể cả khi kind lạ. `tests/backup`: bản sao `db` chứa file phiếu.

## Verification

- `uv run pytest tests/web/test_returns_routes.py tests/maintenance`
- Chạy web dev (`uv run shoponline web`, cổng 8750, kiểm tra cổng trước khi chạy và tắt sau khi thử), đi hết luồng với đơn `261115BUCPCSEN` trên database dev.

## Risk Assessment

- Phát hành hai lần do bấm đúp: partial unique index chặn ở database; route bắt lỗi và báo.
- Trang form dài với đơn nhiều dòng: chấp nhận được (shop online thường 1–3 dòng).
