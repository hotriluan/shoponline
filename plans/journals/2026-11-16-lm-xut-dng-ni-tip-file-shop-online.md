---
title: Làm phần xuất dòng nối tiếp file Shop Online
date: 2026-11-16
summary: Phase 1-4 và tài liệu đã xong trên máy dev; chạy thử production chờ deploy
---

# Làm phần xuất dòng nối tiếp file Shop Online

## What happened
Làm phase 1-4 của plan `plans/261116-1354-shop-online-history-export/plan.md`: migration `0007_sales_history` (ba bảng `report_item_name`, `sales_history_file_order`, `sales_history_exported`), `province_of` và gợi ý tên báo cáo, retention giữ tên khách tới khi đơn đã vào file lịch sử, bộ dựng file 17 cột, trang **Tên báo cáo** và trang **File Shop Online** có xác nhận và gỡ xác nhận. Tài liệu vận hành, kiến trúc, bảo mật đã cập nhật. `uv run pytest` 367 passed, `uv run ruff check` sạch.

## Lỗi bắt được nhờ test
Lúc xác nhận, `INSERT … VALUES (nhiều dòng) ON CONFLICT DO NOTHING` qua psycopg trả `rowcount = -1`, nên thông báo ra "Đã xác nhận -1 đơn". Đổi sang `INSERT … SELECT … RETURNING` rồi đếm số dòng trả về.

## Khác plan
- Link sửa khách hàng của đơn bị chặn trỏ tới `/customers?batch_id=<lô>` thay vì `?platform=…&missing=true`: trang theo sàn chỉ liệt kê đơn đã có dòng `customer_info`, còn bộ lọc `missing` thì ẩn đơn có đủ tên và địa chỉ nhưng địa chỉ không ra tỉnh/thành.
- Thêm ràng buộc CHECK để ba cột tên báo cáo không rỗng, và `tests/web/conftest.py` có fixture `app`/`login` dùng chung cho hai file test mới.

## Next steps
Commit, deploy (script deploy sao lưu rồi `migrate`), rồi làm các bước chạy thử ở phase 5: tách tỉnh/thành cho mọi địa chỉ trên production, duyệt khoảng 75 tên báo cáo, bổ sung tên khách, xuất lần đầu, dán thử, xác nhận, kiểm retention ở chế độ liệt kê. Lần này không đọc được production qua SSH vì công cụ không cho phép.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
