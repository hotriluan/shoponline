---
phase: 4
title: "Route tải lên và trang xác nhận"
status: done
priority: P1
effort: "4h"
dependencies: [3]
---

# Phase 4: Route tải lên và trang xác nhận

## Goal

Admin chọn một hoặc nhiều PDF trên `/customers`, nhận thông báo tóm tắt; khi có chỗ khác nhau thì xác nhận trên
một trang đối chiếu mà không phải tải lại file. Không PDF nào còn lại trên máy chủ.

## Files

- Modify: `src/shoponline/web/routes/customers.py` (thêm 2 route)
- Modify: `src/shoponline/web/templates/customers.html` (khung tải lên, chỉ admin, đặt sau khung "Thêm khách theo mã đơn")
- Create: `src/shoponline/web/templates/customer_labels_confirm.html`
- Create: `tests/web/test_customer_label_routes.py`

## Steps

1. `POST /customers/labels` (`require_admin`), `pdfs: list[UploadFile] = File(...)`:
   - Theo khuôn `upload_invoice_pdf` (`web/routes/returns.py:236`): từ chối sớm nếu `content-length` vượt
     `MAX_FILES × MAX_BYTES` (giới hạn 10 file mỗi lần); đọc từng file `await f.read(MAX_BYTES + 1)`; đọc bằng
     `asyncio.wait_for(run_in_threadpool(read_label_pdf, data), timeout=LABEL_PDF_SECONDS)` với
     `LABEL_PDF_SECONDS = 60` (500 trang ≈ 35 giây).
   - **Không lưu file:** không ghi gì vào `SHOPONLINE_DATA_DIR`; `finally` đóng mọi `UploadFile` (`await f.close()`)
     ở cả nhánh thành công, `FileRejected` và `TimeoutError`, để file tạm của upload > 1 MB bị xóa ngay; xóa
     biến `data` sau khi đọc.
   - Một file lỗi thì từ chối cả lần tải, không ghi gì (thông báo nêu tên file và lỗi). Không trang nào nhận ra
     cũng từ chối.
   - Gộp nhãn của mọi file, gọi `apply_labels`, `db.commit()`.
   - Không có `pending`: flash tóm tắt ("Đã ghi N đơn, giữ nguyên M, K đơn chưa có trong hệ thống; trang không
     đọc được: file X trang 3, 7") rồi chuyển về `/customers`.
   - Có `pending`: render `customer_labels_confirm.html` cùng tóm tắt phần đã ghi.
2. Trang xác nhận: bảng mã đơn, sàn, tên hiện có / tên trên nhãn, địa chỉ hiện có / địa chỉ trên nhãn; ô chọn
   mỗi dòng (mặc định không chọn); trường ẩn mang `platform`, `order_id`, `name`, `address` của nhãn.
3. `POST /customers/labels/confirm` (`require_admin`): nhận các dòng đã chọn, dựng lại nhãn, gọi `apply_labels`
   với `confirmed` là các dòng đó, commit, flash số đơn đã ghi đè. Dữ liệu đến từ form của admin, cùng mức tin
   cậy như `/customers/save`; vẫn kiểm `platform` có trong `platform_setting`.
4. Khung trên `customers.html`: `<form enctype="multipart/form-data">`, `<input type="file" name="pdfs"
   accept="application/pdf" multiple>`, ghi chú "Phiếu vận đơn Shopee (SPX) và TikTok (J&T); file không được lưu".
5. Không ghi tên, địa chỉ vào flash, log hay `event_log`.

## Todo

- [ ] Route tải lên với giới hạn, timeout, đóng file trong `finally`
- [ ] Trang xác nhận + route xác nhận
- [ ] Khung tải lên trên `/customers`
- [ ] Test

## Verification

Test route (giả `read_label_pdf` bằng monkeypatch như `tests/web/test_returns_routes.py:41`):

- viewer bị từ chối; admin thấy khung tải lên, viewer không thấy.
- Tải 2 file ghi đúng; flash không chứa tên hay địa chỉ nào.
- Có dòng chờ: trang xác nhận hiện; gửi lại dòng đã chọn thì ghi đè đúng dòng đó, dòng không chọn giữ nguyên.
- File sai loại, quá lớn, quá 10 file, timeout: không ghi gì, thông báo đúng.
- Sau mỗi nhánh (thành công, lỗi, timeout) mọi `UploadFile` đã đóng (`file.closed`) và thư mục dữ liệu test
  không có file mới.
- `uv run pytest tests/web -q`.
