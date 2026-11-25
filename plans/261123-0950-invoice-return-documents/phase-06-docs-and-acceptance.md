---
phase: 6
title: "Tài liệu và nghiệm thu"
status: completed
priority: P1
effort: "2h"
dependencies: [5]
---

# Phase 6: Tài liệu và nghiệm thu

## Goal

Tài liệu phản ánh tính năng mới và chính sách lưu mới; nghiệm thu với hai đơn mẫu trên database dev.

## Files to Create / Modify

- Modify: `README.md` (bước nghiệp vụ trả hàng, mô-đun `returns/`, lệnh `return-number`)
- Modify: `docs/system-architecture.md` (mục "Trả hàng sau hóa đơn": bảng, luồng, master, bộ đếm; sơ đồ luồng dữ liệu thêm nhánh)
- Modify: `docs/daily-operations.md` (các bước lập phiếu, khi nào cần tải PDF, khi nào đọc lại zrsd003; đơn hủy trước khi có DO không có hóa đơn nên không lập phiếu; đơn kit lập theo dòng cha như hóa đơn)
- Modify: `docs/security-and-data-retention.md` (phiếu trả hàng giữ tên, địa chỉ người mua và file lâu dài, ngoài quy tắc 90 ngày, chỉ admin tải; PDF tải lên không được ứng dụng lưu vào kho file nhưng máy chủ web có thể spool tạm; bảng "giữ gì" cập nhật theo luật giữ theo dữ liệu; sao lưu `db` chép file phiếu)
- Modify: `src/shoponline/maintenance/retention.py` (docstring đầu module liệt kê những gì được giữ)
- Modify: `docs/deployment-guide.md` (bước một lần: `shoponline return-number start <N>`; biến `SHOPONLINE_INVOICE_SYMBOL_PATTERN`; đọc lại zrsd003 các tháng có hóa đơn cần trả; **không `downgrade` migration `0012` khi đã có phiếu**; sau khi khôi phục sao lưu chạy `shoponline return-number repair` và so với số cao nhất đã in)

## Tasks & Steps

1. Đọc từng tài liệu trước khi sửa; cập nhật phần nhỏ nhất sở hữu nội dung; link tới mã thay vì chép chi tiết.
2. Nghiệm thu trên database dev:
   - Đặt số bắt đầu (ví dụ `080`) trên database dev.
   - Đọc lại zrsd003 tháng 11/2026 (file `docs/bbdchd/zrsd003.XLSX` qua `/sap-reports`) để có tiền hóa đơn.
   - Đơn Shopee: master rỗng → bị chặn → tải `hd_shopee.pdf` → master có `100001787` → phát hành lý do "hủy đơn" → so file với `BBDC_shopee.docx`, `FM-LG-Q004.01_shopee.xls` và `hd_shopee.pdf`.
   - Đơn Lazada: không cần PDF (cùng vật tư) → phát hành → so với mẫu Lazada.
   - Với mỗi file phát hành: chạy `format_compare` với file mẫu tương ứng trong `docs/bbdchd/` (Word so trực tiếp; Excel so với mẫu `.xlsx`); xuất PDF bản phát hành và bản mẫu, đặt cạnh nhau. Excel `D14` phải là tên SAP, Word là tên trên hóa đơn.
   - Hủy một phiếu, kiểm tra không lập trùng, lập lại nhận số mới.
   - Quét lại file `.docx`, `.xlsx` sinh ra: không có metadata hay chuỗi dữ liệu khách ngoài trường động.
   - Viewer không tải được file phiếu; bản sao lưu `db` chứa file phiếu.
   - Xóa dữ liệu nghiệm thu khỏi database dev nếu cần (sau khi sao lưu), hoặc giữ làm dữ liệu thật nếu người dùng muốn.
3. `uv run ruff check`, `uv run pytest` toàn bộ.
4. Đối chiếu với Success Criteria trong [plan.md](./plan.md) và đánh dấu.

## Verification

- `uv run ruff check` và `uv run pytest` đạt.
- Bảng so sánh trường theo trường giữa file sinh ra và mẫu, ghi vào báo cáo `plans/reports/`.
- Link trong các tài liệu đã sửa trỏ đúng file.

## Risk Assessment

- Số bắt đầu trên máy chạy thật phải lấy từ người dùng lúc triển khai; số dùng thử trên dev không được mang sang.
