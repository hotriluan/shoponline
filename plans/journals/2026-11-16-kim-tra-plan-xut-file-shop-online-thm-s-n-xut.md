---
title: "Kiểm tra plan xuất file Shop Online, thêm sổ đơn đã xuất"
date: 2026-11-16
summary: "Validate plan 261116-1354: thêm sổ đơn đã xuất, giữ tên khách tới khi xuất, viewer được tải"
---

# Kiểm tra plan xuất file Shop Online, thêm sổ đơn đã xuất

## What happened
Chạy validate cho `plans/261116-1354-shop-online-history-export`. Kiểm 32 dẫn chứng trong code: tất cả đúng. Phát hiện hai lỗ hổng thiết kế. Thứ nhất, lọc theo khoảng ngày đặt hàng làm sót đơn đặt cuối tháng mà có DO sang tháng sau. Thứ hai, retention 90 ngày có thể xóa tên khách trước khi đơn được xuất.

## Decision
Thêm sổ đơn đã xuất: bảng `sales_history_file_order` ghi danh sách đơn trong từng file tải, bảng `sales_history_exported` ghi đơn đã xác nhận. Mỗi lần xuất lấy mọi đơn đã có DO mà chưa xác nhận; bỏ ô "từ ngày". Retention chỉ xóa tên của đơn DELIVERED khi DO đã gửi kế toán và đơn đã vào sổ. Viewer được tải file; chỉ admin xác nhận và gỡ xác nhận. Migration đổi tên thành `0007_sales_history`; phase 4 phụ thuộc thêm phase 2.

## Next steps
`/ak-cook plans/261116-1354-shop-online-history-export/plan.md`.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
