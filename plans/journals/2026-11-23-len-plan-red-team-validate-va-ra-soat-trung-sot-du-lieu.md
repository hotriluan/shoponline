---
title: Lên plan red team, validate các plan còn thiếu và rà soát trùng/sót dữ liệu
date: 2026-11-23
summary: Plan 8 phase red team và validate 9 plan, kèm kiểm 15 bất biến toàn vẹn dữ liệu bằng SQL chỉ đọc trên production
---

# Lên plan red team, validate và rà soát trùng/sót dữ liệu

## What happened
Quét `plans/` thấy 9 plan còn hiệu lực chưa qua red team hoặc validate. Tám trong số đó đã thành mã, chỉ `261113-1142` là chưa làm. Plan `261113-1230-merged-accounting-file` ghi `pending` dù mã đã commit ở `1db7fdb`. Plan nằm ở `plans/261123-0556-red-team-validate-data-integrity-audit/plan.md`. Phase 1 chuẩn bị truy cập chỉ đọc và chụp số đếm nền. Phase 2–6 red team và validate theo nhóm plan. Phase 7 chạy 15 bất biến xuyên luồng trên production. Phase 8 viết báo cáo tổng hợp.

## Decision
Chủ dự án chọn red team **mã đối chiếu plan** thay vì chỉ đọc văn bản plan, vì plan đã làm mà chỉ soi văn bản thì bỏ sót lỗi nằm trong mã. Được phép truy vấn chỉ đọc trên production, có dự phòng là phục hồi bản sao lưu vào database diễn tập. Plan này chỉ tìm và báo cáo; việc sửa sẽ thành plan hoặc `/ak-fix` riêng. Hai plan ít dính dữ liệu (`261113-1012`, `261116-0944`) chỉ red team nhẹ. Các giả thuyết khởi điểm suy ra từ khóa trong `models.py`, ví dụ hóa đơn khóa theo DO, lịch sử đánh dấu theo đơn, tiền vô khóa theo `line_key`. Chúng chưa được kiểm.

## Next steps
Chạy `/ak-cook plans/261123-0556-red-team-validate-data-integrity-audit/plan.md` khi chủ dự án đồng ý. Phase 1 cần quyết định có tạo role chỉ đọc trên production hay không.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
