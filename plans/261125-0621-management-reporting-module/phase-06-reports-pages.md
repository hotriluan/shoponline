---
phase: 6
title: "Trang báo cáo và xuất Excel"
status: completed
priority: P1
effort: "10h"
dependencies: [5]
---

# Phase 6: Trang báo cáo và xuất Excel

## Goal

Quản lý (tài khoản viewer) mở nhóm menu **Báo cáo** và đọc được tình hình bán hàng mà không cần ai giải thích. Mỗi bảng có nút tải Excel cho đúng bộ lọc đang xem.

## Thiết kế

- **Trước khi viết giao diện:** nạp skill `dataviz` (biểu đồ, màu, ô số liệu) và theo các mẫu có sẵn trong `_macros.html` (`page_header`, `stat`), `app.css`.
- **Thư viện biểu đồ:** chép một bản Chart.js UMD đã cố định phiên bản vào `src/shoponline/web/static/vendor/` kèm file giấy phép; không tải từ CDN. Dữ liệu nhúng vào trang dạng JSON (`<script type="application/json">`), không gọi API riêng.
- **Bộ lọc chung** (form GET, giữ trên URL để gửi link được): từ tháng, đến tháng (mặc định 12 tháng gần nhất), sàn, shop.
- **Trang, nhóm menu "Báo cáo"** (đặt đầu, sau "Việc hôm nay"):
  - `/reports`, **Tổng quan:**
    - Hàng ô số liệu cho khoảng đã lọc: giá trị trên sàn, doanh thu hóa đơn, tiền thực nhận, phí sàn, số đơn, giá trị đơn trung bình, tỷ lệ trả.
    - Biểu đồ ba đường theo tháng: trước 11/2026 chỉ có đường giá trị trên sàn, có chú thích lý do.
    - Bảng theo tháng.
  - `/reports/channels`, **Theo sàn và shop:** cột chồng theo tháng và bảng tổng.
  - `/reports/products`, **Theo sản phẩm:** bảng xếp hạng theo giá trị, gom theo tên hàng, mở xem quy cách và màu.
  - `/reports/provinces`, **Theo tỉnh:** bảng xếp hạng 34 tỉnh và dòng "Chưa xác định" (link tới `/province-aliases` cho admin).
  - `/reports/returns`, **Trả hàng:** theo tháng và lý do.
- **Ghi chú dữ liệu:** mọi trang hiện `data_notes` ngay dưới tiêu đề, ví dụ "Tháng 11/2026 thiếu đơn 01–10/11"; "Từ 11/2026 mới có doanh thu hóa đơn và tiền thực nhận"; số đơn còn chờ hóa đơn hoặc chờ tiền trong khoảng đang xem.
- **Xuất Excel:** `?format=xlsx` trên mỗi trang trả file `BAO CAO <TÊN> <từ>-<đến>.xlsx`. Dòng đầu ghi bộ lọc và ghi chú dữ liệu, sau đó là bảng với tiền định dạng `#,##0`. Viết ở `src/shoponline/exports/report_workbook.py`, một hàm chung nhận tiêu đề cột và dòng. File trả từ bộ nhớ, không ghi `generated_file`.
- **Quyền:** viewer và admin đều xem được. Không có thao tác ghi nào trên các trang này.
- **Ô "Việc hôm nay":** không đổi (ngoài phạm vi).

## Files to Create / Modify

- Create: `src/shoponline/web/routes/reports.py`
- Create: `src/shoponline/web/templates/reports/overview.html`, `channels.html`, `products.html`, `provinces.html`, `returns.html`, `_filters.html`
- Create: `src/shoponline/web/static/vendor/chart.umd.min.js`, `src/shoponline/web/static/vendor/chart.LICENSE.txt`, `src/shoponline/web/static/reports.js`
- Create: `src/shoponline/exports/report_workbook.py`
- Modify: `src/shoponline/web/app.py`, `src/shoponline/web/templates/_nav.html`, `src/shoponline/web/static/app.css`
- Create: `tests/web/test_reports.py`, `tests/exports/test_report_workbook.py`

## Tasks & Steps

- [ ] Route và bộ lọc dùng chung; viewer mở được, chưa đăng nhập thì về trang login.
- [ ] Năm trang và biểu đồ.
- [ ] Xuất Excel dùng chung.
- [ ] Ghi chú dữ liệu.
- [ ] Test: mỗi trang trả 200 với bộ lọc rỗng, bộ lọc một shop, khoảng chỉ có lịch sử; file Excel mở được bằng openpyxl và có đúng số dòng; bộ lọc sai (tháng đảo ngược) báo lỗi rõ.
- [ ] Mở trên web dev với dữ liệu thật đã nạp lịch sử; chụp màn hình từng trang để chủ dự án xem.

## Verification

- `uv run pytest tests/web/test_reports.py tests/exports/test_report_workbook.py`
- `uv run ruff check`
- Kiểm tra bằng mắt trên `http://127.0.0.1:8750/reports` cả giao diện sáng và tối, nếu app có hai chế độ.

## Risk

- Bảng sản phẩm có thể dài (12 tên hàng × quy cách × 42 màu trong lịch sử). Gom theo tên hàng mặc định, mở chi tiết khi cần.

## Kết quả (2026-11-25)

Năm trang `/reports`, `/reports/channels`, `/reports/products`, `/reports/provinces`, `/reports/returns`, bộ lọc trên URL, Excel bằng `?format=xlsx`, Chart.js 4.6.2 chép vào `static/vendor/`. Chart.js dùng animation tắt để ảnh chụp và in không bị cắt giữa chừng. Test: `tests/web/test_reports.py`, `tests/exports/test_report_workbook.py`. Đã chụp ảnh cả năm trang trên web dev bằng tài khoản viewer tạm (đã xóa).
