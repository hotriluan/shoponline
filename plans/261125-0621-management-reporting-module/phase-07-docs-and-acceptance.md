---
phase: 7
title: "Tài liệu và nghiệm thu"
status: completed
priority: P2
effort: "3h"
dependencies: [1, 2, 3, 4, 5, 6]
---

# Phase 7: Tài liệu và nghiệm thu

## Goal

Tài liệu khớp với hệ thống mới, và có bằng chứng nghiệm thu cho từng tiêu chí trong [plan.md](./plan.md).

## Files to Create / Modify

- Modify: `docs/system-architecture.md`:
  - sơ đồ luồng dữ liệu (thêm lịch sử, tiền nhập tay, báo cáo);
  - bảng mô-đun (thêm `reports/`);
  - mục mới: **Danh mục shop**, **Tiền về Lazada nhập tay**, **Lịch sử bán hàng 2022–2026** (quy tắc kỳ, mốc `REPORTING_CUTOVER`, quy tắc chống trùng), **Báo cáo** (hai view, ba đường doanh thu, lý do view nằm trong `public`).
- Modify: `README.md` (cấu trúc thư mục, lệnh `history-import`), `docs/daily-operations.md` (chọn shop khi tải file, nhập tiền Lazada, đọc báo cáo, quy đổi tỉnh), `docs/deployment-guide.md` (các bước deploy kế hoạch này, mục dưới).
- Create: `plans/261125-0621-management-reporting-module/reports/acceptance-report.md`

## Các bước deploy lên máy chạy thật

0. <!-- Updated: Validation Session 1 - các số liệu của kế hoạch chưa kiểm trên production --> Chỉ đọc, trên production: các truy vấn ở [phase 1](./phase-01-keep-customer-data.md), [phase 3](./phase-03-shop-catalog.md) và `plan.md` (mốc `REPORTING_CUTOVER`). Lệch thì dừng và sửa kế hoạch.
1. `pwsh -File scripts\windows\backup-db.ps1` (hoặc `shoponline backup run --kind db`). Bản này cũng là bản `history-import --apply` đòi trong 2 giờ gần nhất.
2. Deploy như thường; `migrate` chạy `0013`–`0016`.
3. Chạy lại `register-tasks.ps1` để tác vụ dọn file không còn `--apply`.
4. **Đã làm ngày 2026-11-25** (chủ dự án đồng ý; SHA-256 hai bên khớp, 297127 byte, đang nằm ở `C:\shoponline-data\incoming\`): <!-- Updated: Validation Session 4 --> Đưa file lịch sử lên máy chạy thật. File `docs/history/Shop Online 2022-2026-10-luan.xlsx` bị `.gitignore` loại nên deploy không mang theo; chép bằng SSH từ máy phát triển: `scp "docs/history/Shop Online 2022-2026-10-luan.xlsx" prod-win10:C:/shoponline-data/incoming/`. File chứa tên và số điện thoại khách, nên chỉ đặt trong thư mục dữ liệu `C:\shoponline-data` (giá trị `data_dir` của ứng dụng trên production, đã kiểm; không phải `C:\shoponline\data`), thư mục con `incoming` tạo trước nếu chưa có, không đặt trong cây mã nguồn. Sau `--apply`, lệnh đã giữ một bản trong `exports/history/`, nên xóa bản trong `incoming/`.
5. Trên máy chạy thật: `shoponline history-import "C:\shoponline-data\incoming\<file>"` (chạy thử), đọc báo cáo, rồi `--apply`. Lệnh đòi bản sao lưu `db` trong 2 giờ gần nhất (bước 1), không dùng `--skip-backup-check` ở production. Sau khi nạp, so số dòng và tổng `Customer paid` theo năm với báo cáo chạy thử.
6. Mở `/province-aliases`, khai các tên huyện còn lại.
7. Tạo tài khoản viewer cho quản lý: `shoponline create-user <tên> --role viewer`.

## Tasks & Steps

- [ ] Sửa tài liệu như trên; mỗi tài liệu dưới 800 dòng.
- [ ] Chạy `uv run pytest` và `uv run ruff check` toàn bộ.
- [ ] Nghiệm thu từng tiêu chí, ghi kết quả và bằng chứng (lệnh, số liệu, ảnh màn hình) vào `acceptance-report.md`:
  - tổng `Customer paid` theo năm và theo Division: file gốc so với `report_sale_line`, chênh lệch đúng bằng các dòng bị loại;
  - ba đường doanh thu của một tháng mẫu so với truy vấn tay;
  - `retention --apply` để nguyên `customer_info`;
  - tiền Lazada nhập tay hiện ở file lịch sử và báo cáo;
  - đơn mới mang đúng shop;
  - viewer mở được mọi trang báo cáo và tải Excel.
- [ ] Cập nhật trạng thái phase bằng `ak plan`.

## Verification

- `uv run pytest`, `uv run ruff check`
- Kiểm tra các link trong tài liệu đã sửa trỏ tới file có thật.

## Kết quả (2026-11-25)

Đã sửa `docs/system-architecture.md`, `README.md`, `docs/daily-operations.md`, `docs/deployment-guide.md`; nghiệm thu ở [acceptance-report.md](./reports/acceptance-report.md). Các bước deploy lên máy chạy thật chưa làm (việc của chủ dự án).
