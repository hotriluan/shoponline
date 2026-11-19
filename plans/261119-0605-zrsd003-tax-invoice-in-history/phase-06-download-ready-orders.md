---
phase: 6
title: "Tải file với các đơn đã đủ dữ liệu khi còn đơn bị chặn"
status: completed
priority: P2
effort: "1h"
dependencies: [4]
---

# Phase 6: Tải file với các đơn đã đủ dữ liệu

## Goal
Còn đơn bị chặn (vì bất kỳ lý do nào) thì vẫn tải được file gồm các đơn đã đủ dữ liệu. Đơn bị chặn vẫn được liệt kê, không có trong file, và vào file sau khi đủ dữ liệu.

Nguồn quyết định: [brainstorm-261119-1340-history-export-ready-orders.md](../reports/brainstorm-261119-1340-history-export-ready-orders.md).

## Files to Modify
- `src/shoponline/web/routes/sales_history.py` — bỏ cổng `if result.blocked` trong `download_history_file`.
- `src/shoponline/web/templates/sales_history.html` — hiện nút **Tải file** khi có dòng, kèm câu "N đơn bị chặn chưa có trong file này".
- `tests/web/test_sales_history_routes.py` — thay test cổng chặn bằng test tải các đơn đủ dữ liệu.
- `docs/daily-operations.md` — bước 3–4 theo hành vi mới; cách sắp xếp sheet1 theo createTime.

## Verification
- File tải về chỉ có dòng của đơn đủ dữ liệu; `sales_history_file_order` chỉ ghi đơn đó.
- Đơn bị chặn có lại ở lần tải sau khi đủ dữ liệu.
- Không có đơn nào đủ dữ liệu thì vẫn báo "Không có đơn nào chờ xuất".
- `uv run pytest` và `uv run ruff check` thoát mã 0.
