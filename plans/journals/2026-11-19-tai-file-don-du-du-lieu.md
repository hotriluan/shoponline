---
title: Cho tải file Shop Online khi còn đơn bị chặn
date: 2026-11-19
summary: Phase 6 xong; file lịch sử chứa các đơn đã đủ dữ liệu, đơn bị chặn ở lại chờ lần tải sau
---

# Cho tải file Shop Online khi còn đơn bị chặn

## What happened
Từ khi có cột 19 Tax Invoice Doc., ngày nào cũng có đơn mới có DO mà chưa có hóa đơn. Cổng "còn đơn bị chặn thì không tải được" vì thế gần như luôn đóng. Phase 6 của `plans/261119-0605-zrsd003-tax-invoice-in-history/plan.md` bỏ cổng này ở `download_history_file` và trong template. File chỉ chứa và chỉ ghi nhận các đơn đã đủ dữ liệu; đơn bị chặn vẫn được liệt kê. Bộ test: 401 passed, `ruff check` sạch.

## Decision
Chủ dự án chọn áp dụng cho mọi lý do chặn, không chỉ đơn chờ hóa đơn (xem `plans/reports/brainstorm-261119-1340-history-export-ready-orders.md`). Không chọn "bản nháp", vì bản nháp chỉ để xem, còn file thật vẫn bị kẹt mỗi ngày. Không sửa code để hỗ trợ sắp xếp: sheet1 có `createTime` là text `YYYY-MM-DD HH:MM` ở cả 3.010 dòng, nên sắp xếp theo text đã đúng thứ tự thời gian. Cách sắp xếp đã ghi vào `docs/daily-operations.md`.

## Next steps
Deploy cùng phần zrsd003 của phase 5.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
