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

Tài liệu vận hành và kiến trúc mô tả file tải tất cả đơn: dùng để làm gì, gồm đơn nào, cột Trạng thái, và vì sao không được dán.

## Files to Create / Modify

- Modify: `docs/daily-operations.md`, mục "Xuất dòng cho file Shop Online", ngay sau gạch **Tải file nháp** ở bước 4
- Modify: `docs/system-architecture.md`, đoạn `/sales-history` (tìm `/sales-history/draft`)

## Tasks & Steps

1. Đọc lại hai đoạn trên trước khi sửa.
2. `daily-operations.md`: thêm một gạch đầu dòng nói:
   - **Tải tất cả đơn** (từ ngày đến ngày đặt hàng, hai đầu đều tính, không giới hạn độ dài) dùng để đối chiếu với file Excel kế toán.
   - Gồm mọi đơn ở mọi trạng thái, đã và chưa xác nhận dán; ô thiếu để trống.
   - Cột 21 `Trạng thái` ghi trạng thái đơn, `Chờ hóa đơn`/`Chờ tiền vô` nếu có, và `Đã xác nhận dán` hoặc `Chưa xác nhận`.
   - Đơn cũ quá thời hạn lưu có tên khách và tỉnh trống.
   - Không lưu, không xác nhận được, không dán vào file lịch sử; sheet tên `TẤT CẢ ĐƠN - KHÔNG DÁN`.
3. `system-architecture.md`: thêm một câu: `/sales-history/all` gọi `collect_all_rows`, không chặn đơn nào, trả file từ bộ nhớ và không ghi `generated_file`, `sales_history_file_order` hay `sales_history_exported`.
4. Đối chiếu với code phase 1: tên route, tên file, tên sheet, các nhãn trạng thái.

## Verification

- `git diff docs/` chỉ gồm hai đoạn trên.
- Các tên nhắc trong docs (`/sales-history/all`, `collect_all_rows`, `TẤT CẢ ĐƠN - KHÔNG DÁN`, `Đã xác nhận dán`, `Chưa xác nhận`, `Tải tất cả đơn`) tìm thấy trong `src/` bằng Grep.
