---
title: Lên plan chọn tháng trên trang File Shop Online và đọc zrsd003 theo tháng
date: 2026-11-19
summary: Plan 2 phase đổi ô ngày sang ô tháng đặt hàng; zrsd003 đọc từ ngày 1 của tháng (hoặc đơn tồn sớm hơn) đến hôm nay
---

# Lên plan chọn tháng trên trang File Shop Online và đọc zrsd003 theo tháng

## What happened
Chủ dự án làm file `Shop Online 2022-2026` mỗi tháng một lần, vào khoảng ngày 10 của tháng sau, và đề xuất đọc zrsd003 trọn tháng (ngày 1 đến ngày cuối tháng). Plan ở `plans/261119-0854-month-pick-zrsd003-read/plan.md`: phase 1 đổi tham số trang từ `until` sang `month` và tính khoảng đọc mới, phase 2 cập nhật docs và kiểm một lần đọc thật.

## Decision
Giữ đơn vị tháng nhưng không chốt khoảng đọc ở ngày cuối tháng. zrsd003 lọc theo Billing Date, còn trang gom đơn theo ngày đặt; hóa đơn ra sau DO, nên đơn đặt 30/10 có thể có hóa đơn 2/11 và sẽ bị chặn oan nếu chỉ đọc tới 31/10. Khoảng đọc là `min(ngày 1 của tháng, ngày đặt sớm nhất của đơn chờ hóa đơn)` đến hôm nay, để vẫn phủ đơn tồn tháng trước. Chủ dự án xác nhận tháng gom đơn theo ngày đặt.

## Next steps
Chủ dự án xác nhận tháng mặc định (đề xuất: tháng trước), rồi chạy `/ak-cook plans/261119-0854-month-pick-zrsd003-read/plan.md`.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
