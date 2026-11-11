---
title: "Phase 3: Web UI và file đơn hàng cho sales admin"
status: in-progress
priority: P1
effort: 4d
dependencies: [2]
---

# Phase 3: Web UI và file đơn hàng cho sales admin

## Overview

Dựng web để admin shop online tải file sàn lên, xử lý đơn thiếu ánh xạ, nhập tên khách hàng, và tải về file `ĐƠN HÀNG ONLINE` đúng mẫu sales admin đang dùng. Sau phase này admin không còn chép tay và VLOOKUP để làm file đơn hàng.

## Key Insights

Mẫu lấy từ `docs/ĐƠN HÀNG ONLINE SHOPEE 111126.1.xlsx` và `docs/ĐƠN HÀNG ONLINE TIKTOK 111126.xlsx`:

- Một sheet mang tên sàn viết hoa (`SHOPEE`, `TIKTOK`).
- `E3` là tiêu đề `ĐƠN HÀNG THÁNG mm/yyyy`; `D5`/`E5` tên khách hàng là tên sàn; `D6`/`E6` mã khách hàng SAP; `D7` địa chỉ khách hàng.
- Dòng 9 là tiêu đề bảng: `Ngày`, `Đơn Hàng`, `Mã Số Đơn Hàng`, `Tên Sản Phẩm`, `Mã SP`, `Số Lượng`, `Đơn Giá`, `Thành Tiền`, `Sale`. Dữ liệu từ dòng 10.
- File tay dùng công thức VLOOKUP sang sheet `price`. File hệ thống sinh ghi giá trị, không ghi công thức.
- Sales admin phải tạo SO không giảm giá trước, SO có giảm giá sau, vì bản ghi `ZDI1` dùng chung cho cả khách hàng SAP.

## Requirements

- Tải file sàn lên, chọn sàn; kết quả hiện số đơn mới, cập nhật, không đổi, và danh sách đơn lỗi.
- Một lô là một sàn và một ngày xử lý D. Màn hình lô hiện đơn, trạng thái, ngày goods issue đề xuất; admin sửa được ngày này cho cả lô.
- Sinh file `ĐƠN HÀNG ONLINE <SÀN> ddmmyy.xlsx` cho một lô, chỉ gồm đơn `READY`. Đơn không giảm giá xếp trước, đơn có giảm giá xếp sau; trong mỗi nhóm theo thứ tự ngày đặt.
- Cột `Mã Số Đơn Hàng` là ô dạng văn bản. Cột `Sale` ghi trợ giá một đơn vị, để trống khi bằng 0.
- Lô còn đơn `MAPPING_ERROR` hoặc `NEED_REVIEW` thì vẫn sinh được file, kèm cảnh báo số đơn bị bỏ ra.
- Quản lý bảng ánh xạ: thêm, sửa, và nhập từ Excel theo từng sàn.
- Nhập tên khách hàng và sửa địa chỉ theo từng đơn; thêm được khách hàng theo mã đơn cho sàn chưa có bộ đọc (Lazada).
- Đăng nhập và hai vai trò: `admin` (mọi việc) và `viewer` (chỉ xem).
- Admin đánh dấu được một đơn là `CANCELLED`.

## Architecture

```
exports/order_workbook.py   lô → file ĐƠN HÀNG ONLINE
web/app.py                  FastAPI, phiên đăng nhập, phân quyền
web/routes/imports.py       tải file sàn
web/routes/batches.py       danh sách lô, chi tiết lô, tải file đơn hàng, sửa ngày goods issue
web/routes/orders.py        chi tiết đơn, lịch sử sự kiện, đánh dấu hủy
web/routes/sku_mapping.py   bảng ánh xạ, nhập từ Excel
web/routes/customers.py     tên khách hàng, địa chỉ
web/templates/              Jinja2, không SPA
```

File tải lên và file sinh ra lưu trong thư mục dữ liệu ngoài repo; database lưu đường dẫn và mã băm.

## Related Code Files

- Create: `src/shoponline/exports/order_workbook.py`
- Create: `src/shoponline/web/app.py`, `web/auth.py`, `web/routes/imports.py`, `batches.py`, `orders.py`, `sku_mapping.py`, `customers.py`, `web/templates/`
- Modify: `src/shoponline/cli.py` (lệnh `web`, `create-user`)
- Create: `tests/exports/test_order_workbook.py`, `tests/web/`

## Implementation Steps

1. Viết `order_workbook.py`. Test đọc lại file sinh ra: đúng tên sheet, đúng ô tiêu đề, đúng thứ tự cột, mã đơn là chuỗi, đơn không giảm giá đứng trước, `Thành Tiền` bằng số lượng nhân đơn giá.
2. So file sinh ra với `docs/ĐƠN HÀNG ONLINE SHOPEE 111126.1.xlsx` trên máy phát triển: cùng các đơn, cùng tên SAP, mã SP, số lượng, đơn giá.
3. Viết `app.py`, đăng nhập, vai trò; mật khẩu băm bằng thuật toán chuẩn của thư viện.
4. Viết màn hình tải file và màn hình lô.
5. Viết màn hình bảng ánh xạ và nhập từ Excel. Sau khi thêm ánh xạ, các đơn `MAPPING_ERROR` liên quan được xét lại.
6. Viết màn hình khách hàng: danh sách đơn của lô với ô tên và địa chỉ sửa tại chỗ; lọc đơn chưa có tên.
7. Viết màn hình chi tiết đơn và nút đánh dấu hủy.
8. Sales admin dùng thử file sinh ra cho một ngày đơn thật và góp ý về bố cục.

## Todo

- [x] Sinh file `ĐƠN HÀNG ONLINE` và test
- [x] So với file tay ngày 11/11 (cùng 8 đơn, cùng tên SAP, mã SP, số lượng, đơn giá)
- [x] Đăng nhập và vai trò
- [x] Màn hình tải file và màn hình lô
- [x] Bảng ánh xạ và nhập từ Excel
- [x] Màn hình khách hàng
- [x] Chi tiết đơn và đánh dấu hủy
- [ ] Sales admin dùng thử

## Success Criteria

- Sales admin tạo được SO cho một ngày đơn thật chỉ từ file hệ thống sinh.
- Đơn thiếu ánh xạ được xử lý xong trên web mà không cần lập trình viên.

## Verification

- `uv run pytest tests/exports tests/web` thoát mã 0.
- Mở file sinh ra bằng Excel: mã đơn TikTok hiện đủ 18 chữ số.

## Risk Assessment

- **Cột ghi trợ giá chưa được xác nhận.** Kế hoạch dùng cột `Sale`; tên cột đích nằm ở một chỗ trong `order_workbook.py` để đổi nhanh.
- **Sales admin cần thêm cột.** Bước dùng thử ở cuối phase để phát hiện sớm.

## Security Considerations

- Web chỉ nghe trong mạng nội bộ; mọi trang yêu cầu đăng nhập.
- Tên file tải lên không dùng làm đường dẫn lưu; kiểm tra đuôi file và kích thước.

## Next Steps

Phase 4 thêm bước xác nhận lô và file gửi kế toán.
