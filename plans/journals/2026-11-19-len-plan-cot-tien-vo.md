---
title: Lên plan cột Tiền Vô từ file quyết toán Shopee/TikTok
date: 2026-11-19
summary: Plan 3 phase thêm cột 20 Tiền Vô vào file Shop Online; Shopee và TikTok lấy được theo đơn, Lazada để trống
---

# Lên plan cột Tiền Vô từ file quyết toán Shopee/TikTok

## What happened
Phân tích ba file trong `docs/tienvo/`. Shopee (`Số tiền` theo `Mã đơn hàng`, header ở dòng 18) và TikTok (`Tổng số tiền quyết toán` theo `ID đơn hàng/điều chỉnh`) có tiền theo đơn. File Lazada là Balance Transactions, chỉ có Settlement gộp theo ngày, không có mã đơn. Plan ở `plans/261119-0719-tien-vo-column/plan.md`: bảng `platform_settlement` và bộ đọc, cột 20 cùng hộp "Đơn chờ tiền vô" có form upload, rồi docs và chạy thử production.

## Decision
Ban đầu đề xuất "chặn đơn chờ tiền vô". Chủ dự án lo rằng như vậy sẽ không bao giờ tải được file. Thực tế từ phase 6 của plan zrsd003, đơn bị chặn chỉ bị để lại, file vẫn tải với các đơn đủ dữ liệu, nên dùng lại cơ chế đó và tách đơn chỉ chờ tiền vô ra hộp riêng. Lưu từng dòng giao dịch theo khóa duy nhất thay vì tổng theo đơn, để upload các kỳ chồng nhau không cộng trùng mà cũng không mất dòng. `parse_money` hiện từ chối số âm, trong khi Shopee có dòng -2.700, nên cần thêm bản có dấu.

## Next steps
Chạy `/ak-cook plans/261119-0719-tien-vo-column/plan.md` khi chủ dự án đồng ý.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
