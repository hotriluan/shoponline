---
phase: 2
title: "Trang tải file và tài liệu"
status: pending
priority: P1
effort: "3h"
dependencies: [1]
---

# Phase 2: Trang tải file và tài liệu

## Goal

Admin tải file ở trang Tiền về Lazada, xem trước từng dòng rồi lưu; viewer không thấy và không gọi được; tài liệu vận hành và kiến trúc mô tả cách làm.

## Bối cảnh

- Luồng dán hiện có: `POST /settlements/lazada/preview` dựng lại trang với `preview` và `paste` (đưa vào ô ẩn), rồi `POST /save-paste` kiểm lại và lưu từng dòng ([settlements.py:126](../../src/shoponline/web/routes/settlements.py)). Luồng file đi theo cùng hình dạng, thay ô `paste` bằng văn bản `carry` của `to_carry`.
- Route nhận file: mẫu ở [sku_mapping.py:206](../../src/shoponline/web/routes/sku_mapping.py) (`async def`, `file: UploadFile = File(...)`, `require_admin`). Giới hạn kích thước dùng `MAX_UPLOAD_BYTES` của [uploads.py](../../src/shoponline/web/uploads.py); không dùng `save_upload` vì nó lưu file và tạo `ImportBatch`, còn luồng này không lưu file.
- Bản tuyên bố "File Lazada không có mã đơn" ở đầu [lazada_settlements.html](../../src/shoponline/web/templates/lazada_settlements.html) vẫn đúng với file Balance Transactions của Lazada; câu mô tả chỉ cần thêm đường tải file kế toán.

## Thiết kế

- `POST /settlements/lazada/preview-file` (`async`, `require_admin`): đọc tối đa `MAX_UPLOAD_BYTES + 1` byte, từ chối nếu quá lớn hoặc đuôi không phải `.xlsx` ("Chỉ nhận file .xlsx", "File lớn hơn 20 MB", "File rỗng"); `read_file` ném `FileRejected` thì `flash` thông báo và quay lại trang; còn lại gọi `resolve` và dựng trang với `file_preview` và `carry`.
- `POST /settlements/lazada/save-file` (`require_admin`): `from_carry(carry)` (sai dạng thì flash "Dữ liệu xem trước không đọc được, hãy tải lại file"), `resolve` lại, `manual.set_amount` cho dòng không lỗi, `commit` một lần; flash "Đã lưu N đơn." và liệt kê dòng bị bỏ ("dòng a: lý do"), cùng kiểu `save_paste`.
- Template: trong khối admin thêm form `enctype="multipart/form-data"` với `<input type="file" accept=".xlsx">` và nói rõ ba tên cột, kèm ví dụ một dòng. Bảng xem trước file: Dòng, Số hóa đơn (`zfill(8)`), Mã đơn, Số tiền, Ngày nhận, Kết quả; dòng lỗi dùng lớp `attention` như bảng xem trước hiện có; nút "Lưu N dòng đúng" tắt khi không có dòng nào đúng. Dòng lỗi đọc (ngày hay tiền sai) hiện số hóa đơn nếu đọc được, các ô còn lại để trống.
- Các route cũ (`/set`, `/preview`, `/save-paste`, `/remove`) không đổi.

## Files to Create / Modify

- Modify: `src/shoponline/web/routes/settlements.py` (hai route, mở rộng `_page` nhận `file_preview` và `carry`)
- Modify: `src/shoponline/web/templates/lazada_settlements.html`
- Modify: `tests/web/test_lazada_settlements.py`
- Modify: `docs/daily-operations.md` (mục "Tiền về Lazada (admin)", dòng 86)
- Modify: `docs/system-architecture.md` (mục "Tiền về Lazada nhập tay", dòng 89; thêm [settlement_invoice_file.py](../../src/shoponline/accounting/settlement_invoice_file.py))

## Tasks & Steps

- [ ] Hai route và phần mở rộng `_page`.
- [ ] Template: form tải file, bảng xem trước, nút lưu.
- [ ] Test web (gửi file bằng `files={"file": (...)}` của `TestClient`; file dựng bằng openpyxl):
  - admin tải file hợp lệ, xem trước hiện đúng mã đơn và "lưu được", `save-file` ghi `platform_settlement` với `source = 'manual'` và `entered_by` đúng;
  - file lẫn dòng đúng và dòng sai: chỉ dòng đúng được lưu, dòng sai được nêu tên;
  - tải lại cùng file thì không thêm dòng (`_typed` vẫn một dòng mỗi đơn) và `event_log` có số cũ;
  - file thiếu cột, file không phải xlsx, file rỗng: có thông báo, không ghi gì;
  - `carry` bị sửa sai dạng: có thông báo, không ghi gì;
  - viewer: trang không có form tải file, và `POST` hai route mới bị từ chối như các route admin khác trong file test này;
  - sau khi lưu, `collect_rows` (hoặc file Shop Online) của đơn Lazada có `Tiền Vô` đúng số (một ca trong `tests/exports/test_sales_history_workbook.py` đã có sẵn cho tiền nhập tay; chỉ cần xác nhận không bị hỏng).
- [ ] Cập nhật hai file tài liệu: cách chuẩn bị file (ba cột, tên cột, một dòng một hóa đơn), vì sao dòng bị từ chối, và hai đơn có DO nhưng chưa có hóa đơn SAP phải đợi hóa đơn về hoặc nhập tay.
- [ ] Đọc lại hai file tài liệu, kiểm các liên kết và tên hàm với mã nguồn.

## Verification

- `uv run pytest tests/accounting tests/web/test_lazada_settlements.py tests/exports`
- `uv run pytest` (cả bộ, vì đổi `_page` và template dùng chung bởi nhiều route)
- `uv run ruff check src tests`
- Chạy ứng dụng, tải một file mẫu ba dòng (một đúng, một hóa đơn lạ, một ngày tương lai) và đối chiếu bảng xem trước. Dùng cổng và tiến trình đang chạy của dự án nếu có; dừng tiến trình đã khởi động khi xong.

## Risk

- Form tải file dùng `python-multipart`: đã có vì `sku_mapping.py` và các route khác nhận file.
- Văn bản `carry` nằm trong HTML: Jinja đã tự thoát. Kích thước tỉ lệ với số dòng, nhưng file kế toán thực tế chỉ vài trăm dòng; không thêm giới hạn số dòng ngoài giới hạn 20 MB của file.

## Rollback

Gỡ hai route, khối template và phần tài liệu; không có thay đổi schema hay dữ liệu. Các dòng đã lưu là dòng `manual` bình thường, xóa được từng đơn trên trang.
