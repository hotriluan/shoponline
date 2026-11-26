---
title: Lên kế hoạch bỏ phiếu nhập hàng trả về ZDE1 khỏi file kế toán
date: 2026-11-26
summary: ZRSD004 có phiếu ZDE1 (hàng trả về vào kho QC 0301) gây cảnh báo thiếu mã đơn và lọt vào file kế toán; kế hoạch chỉ giữ ZDA1.
---

# Lên kế hoạch bỏ phiếu nhập hàng trả về ZDE1 khỏi file kế toán

## Chuyện gì xảy ra
Đợt gửi kế toán số 8 (26/11) báo "thiếu mã đơn, tên khách, địa chỉ" cho SO 20001989 đến 20001993. Kiểm tra qua SSH trên máy chạy thật: 5 dòng này có `Delivery Type = ZDE1`, kho `0301`, `Req. Type` trống, SO dải `2000…`, delivery dải `196…`, và không có trong `sales_order` hay `sap_so_ref`. Người dùng xác nhận `ZDE1` là phiếu nhập hàng trả về, còn `0301` là kho tạm của QC. Họ đã bỏ tay 5 dòng khỏi file 26/11 trước khi gửi.

## Quyết định
- File gộp gửi kế toán chỉ giữ phiếu thuộc danh sách cho phép `ZDA1`. Dòng loại khác bị bỏ với lý do riêng, hiện trên trang đợt.
- Bản xem trước một file (`ingest_zrsd004`), nơi sinh cảnh báo trên trang Robot SAP, sẽ không cảnh báo cho dòng không phải giao bán.
- Lọc theo loại phiếu, không theo dấu hiệu thiếu thông tin khách.

## Điều cần nhớ
- Fixture `zrsd004_row` để trống `Delivery Type`. Phải cho nó mặc định `ZDA1` trước khi bật bộ lọc, nếu không mọi test hiện có sẽ mất dòng.
- 5 delivery `ZDE1` đã nằm trong `accounting_sent_delivery` (run 8). Việc này vô hại, nên để nguyên.

## Bước tiếp theo
`/ak-cook plans/261126-0615-exclude-return-deliveries-from-accounting-file/plan.md`

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
