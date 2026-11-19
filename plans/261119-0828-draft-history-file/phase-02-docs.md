---
phase: 2
title: "Tài liệu"
status: completed
priority: P2
effort: "0.5h"
dependencies: [1]
---

# Phase 2: Tài liệu

## Goal

Tài liệu vận hành và kiến trúc mô tả file nháp: dùng để làm gì, gồm đơn nào, và vì sao không được dán vào file lịch sử.

## Files to Create / Modify

- Modify: `docs/daily-operations.md`, mục "Xuất dòng cho file Shop Online"
- Modify: `docs/system-architecture.md`, đoạn `/sales-history` (dòng 71)

## Tasks & Steps

1. `daily-operations.md`: thêm một gạch đầu dòng ngay sau bước 4 (**Tải file**). Gạch này nói:
   - **Tải file nháp** để kiểm tra trước khi chốt tháng.
   - Nháp gồm đơn đủ dữ liệu và đơn chỉ còn chờ hóa đơn hoặc tiền vô; ô còn thiếu để trống.
   - Cột 21 `Trạng thái` ghi đơn đang chờ gì.
   - Đơn bị chặn vì lý do khác không có trong nháp.
   - Nháp không lưu, không xác nhận được, và không được dán vào file lịch sử.
2. `system-architecture.md`: thêm một câu. `/sales-history/draft` gọi `collect_rows(draft=True)`: chấp nhận đơn chỉ có lý do `tax_invoice` hoặc `settlement`, ghi thêm cột 21, trả file từ bộ nhớ và không ghi `generated_file` hay `sales_history_file_order`.
3. Đọc lại hai đoạn vừa sửa và đối chiếu với code của phase 1: tên route, tên file, nhãn trạng thái.

## Verification

- `git diff docs/` chỉ gồm hai đoạn trên.
- Các tên được nhắc trong docs (`/sales-history/draft`, `Trạng thái`, `Chờ hóa đơn`, `Chờ tiền vô`, `NHÁP SHOP ONLINE LỊCH SỬ`) phải tìm thấy trong `src/` bằng Grep.
