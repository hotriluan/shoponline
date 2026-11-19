---
title: Lên plan thêm Tax Invoice Doc. từ zrsd003 vào file Shop Online
date: 2026-11-19
summary: Plan 5 phase để robot và upload tay đọc zrsd003, chặn đơn chờ hóa đơn và thêm cột 19 vào file lịch sử
---

# Lên plan thêm Tax Invoice Doc. từ zrsd003

## What happened
Đọc `docs/zrsd003.XLSX` (650 dòng, 650 OD Doc. khác nhau, mỗi DO một hóa đơn). `OD Doc.` trùng `Delivery` của zrsd004, và database đã lưu DO của đơn ở `sales_order.do_number`, nên nối thẳng với đơn mà không cần đọc lại zrsd004. Bản ghi SAP do chủ dự án làm cho thấy ZRSD003 không có ô lọc Bill-to; chỉ lọc được Sales Org, Sales Office, Billing Date.

## Decision
Chủ dự án chốt: robot đọc ZRSD003 kèm ô upload tay dự phòng; đơn có DO chưa có hóa đơn thì chặn (hóa đơn luôn xuất sau DO); cột 19 sau Mã đơn. Kiến trúc: robot đọc cả sales office 1401 theo Billing Date, bộ nhập chỉ giữ Bill-to của ba sàn (243/650 dòng trong file mẫu) và xóa file gốc ngay vì nó chứa dữ liệu khách doanh nghiệp. Một job cho mọi sàn, khóa theo khoảng ngày.

Plan: `plans/261119-0605-zrsd003-tax-invoice-in-history/plan.md`, 5 phase: bảng và bộ nhập, upload tay, job robot, chặn đơn và cột 19, tài liệu và chạy thử production.

## Next steps
`/ak-cook plans/261119-0605-zrsd003-tax-invoice-in-history/plan.md`. Cần kiểm khi chạy thử: Enter sau ô Sales Org/Sales Office, câu "không có dữ liệu" của ZRSD003.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
