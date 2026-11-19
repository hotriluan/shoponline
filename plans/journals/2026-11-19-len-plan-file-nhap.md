---
title: Lên plan file nháp Shop Online
date: 2026-11-19
summary: Plan 2 phase thêm nút Tải file nháp gồm cả đơn chờ hóa đơn và chờ tiền vô, có cột Trạng thái, không lưu và không xác nhận được
---

# Lên plan file nháp Shop Online

## What happened
Chủ dự án muốn xem trước cả các đơn đang bị chặn vì chờ Tax Invoice Doc. hoặc chờ tiền vô. Plan nằm ở `plans/261119-0828-draft-history-file/plan.md`. Phase 1 thêm cờ `draft` cho `collect_rows` và `build_history_workbook`, route `/sales-history/draft` và nút trên trang. Phase 2 cập nhật docs.

## Decision
Chủ dự án chọn hai điều. Nháp chỉ chấp nhận đơn mà mọi lý do chặn là `tax_invoice` hoặc `settlement`; đơn thiếu tên khách hay tên báo cáo thì không dựng được cột, nên vẫn bị loại. Nháp có thêm cột 21 `Trạng thái`. Nháp trả từ bộ nhớ, không qua `save_generated`, để không bao giờ vào bảng File đã tải hay đánh dấu đơn đã dán. Mình chọn thêm cờ vào hàm có sẵn thay vì viết hàm riêng, để file nháp và file thật không lệch nhau về sau. Vì trả `Response` thay cho `FileResponse`, tên file có dấu phải tự mã hóa theo RFC 5987.

## Next steps
Chạy `/ak-cook plans/261119-0828-draft-history-file/plan.md` khi chủ dự án đồng ý.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
