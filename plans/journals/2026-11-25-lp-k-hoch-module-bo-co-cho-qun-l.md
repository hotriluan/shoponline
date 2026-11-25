---
title: Lập kế hoạch module báo cáo cho quản lý
date: 2026-11-25
summary: "Kế hoạch 7 phase: giữ dữ liệu khách, tiền về Lazada nhập tay, danh mục shop, nạp lịch sử 2022–2026, view và trang báo cáo"
---

# Lập kế hoạch module báo cáo cho quản lý

## What happened
Brainstorm qua bốn lượt với chủ dự án, rồi lập kế hoạch `plans/261125-0621-management-reporting-module/` (7 phase, khoảng 44h). Người xem chính là quản lý.

Các bằng chứng đã kiểm trong phiên:
- Máy chạy thật là máy dev (`C:\shoponline`). Tác vụ `shoponline-retention` đăng ký không có `--apply` và đã tắt từ 16/11; `event_log` không có dòng `retention_*`. Dữ liệu khách chưa từng bị xóa.
- Đơn sớm nhất trong `shoponline` và `shoponline_dev` đặt lúc 2026-11-11 10:32. File lịch sử kết thúc ở kỳ 10/2026, nên đơn 01–10/11 hiện không có ở nguồn nào.
- File lịch sử có ba dạng `createTime`; các dòng ghi `2026-11-08`/`2026-12-08` mang kỳ 8/2026, tức là đảo ngày với tháng.
- File "chờ giao hàng" của Shopee không có cột nào nhận ra được shop.
- Lệnh phục hồi chạy `DROP SCHEMA public CASCADE` (`backup/restore.py:226`).

## Decision
- Giữ `customer_info` vĩnh viễn; `retention --apply` thành no-op, các quy tắc xóa file giữ nguyên.
- Tiền Lazada nhập tay vào `platform_settlement`: `import_batch_id` cho phép NULL, cột `source=manual`, `line_key = manual:<mã đơn>`. Không chặn đơn Lazada thiếu tiền trong file lịch sử.
- Danh mục `shop`: admin chọn shop khi tải file (bỏ tự nhận). Các shop cùng sàn dùng chung khách hàng SAP, nên robot, đối chiếu và `order_batch` không đổi.
- Kỳ của dòng lịch sử lấy theo cột `month`/`year`. Một mốc duy nhất `REPORTING_CUTOVER = 2026-11-11`; dòng lịch sử kỳ 11/2026 được nhận nếu ngày đặt trước mốc.
- View báo cáo đặt trong `public` (`report_sale_line`, `report_order_revenue`), không trong schema riêng. View ở schema khác sẽ bị `DROP SCHEMA public CASCADE` xóa theo mà không báo lỗi.
- Ba đường doanh thu (giá trị trên sàn, doanh thu hóa đơn, tiền thực nhận) đều tính theo kỳ của ngày đặt đơn.

## Next steps
Validate hoặc red-team kế hoạch nếu cần, rồi chạy `/ak-cook plans/261125-0621-management-reporting-module/plan.md`. Phase 1–3 độc lập với nhau.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
