---
title: Làm ô chọn tháng trên trang File Shop Online và đọc zrsd003 theo tháng
date: 2026-11-19
summary: Trang dùng tham số month (mặc định tháng trước); robot đọc zrsd003 từ ngày 1 của tháng hoặc đơn tồn sớm hơn đến hôm nay; form tay trên trang Robot SAP không đổi
---

# Làm ô chọn tháng trên trang File Shop Online và đọc zrsd003 theo tháng

## What happened
Phase 1 của `plans/261119-0854-month-pick-zrsd003-read/plan.md` xong. Năm route của trang File Shop Online dùng `month=YYYY-MM` thay `until`. FastAPI kiểm dạng bằng regex, nên tháng sai dạng trả 422. Mặc định là tháng trước theo giờ Việt Nam. `_invoice_range` bắt đầu ở `min(ngày 1 của tháng, đơn chờ hóa đơn sớm nhất)` và kết thúc ở hôm nay. Phase 2 sửa `daily-operations.md` và `robot-runbook.md`; phần kiểm lần đọc thật trên production còn chờ deploy. Toàn bộ 445 test qua, ruff sạch.

## Decision
Chủ dự án yêu cầu form "Ra lệnh cho robot" trên trang Robot SAP vẫn chọn tự do từ ngày đến ngày, nên chỉ nút trên trang File Shop Online theo tháng. Ngày test cố định là 13/11, nên mặc định tháng trước làm các test cũ mất đơn tháng 11; test giờ truyền `month=2026-11` qua hằng `PAGE`. Một file đã tải mà chưa xác nhận vẫn để đơn ở trạng thái chờ, nên trang tháng 11 vẫn đếm đơn 31/10 vừa tải trong file tháng 10.

## Next steps
Commit khi chủ dự án đồng ý. Sau khi deploy, đọc thật tháng 10/2026 và ghi thời gian chạy cùng số dòng.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
