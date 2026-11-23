---
phase: 6
title: "Phase 6: Plan chưa làm: robot đọc khi cần (261113-1142)"
status: completed
priority: P2
effort: 2h
dependencies: []
---

# Phase 6: Plan chưa làm: robot đọc khi cần

## Overview

`261113-1142-robot-manual-run-on-demand` còn `pending`. Phase này red team (2 phase, 2 lens, cộng lens trùng/sót) và validate trên văn bản plan theo quy trình chuẩn của `ak-plan`. Trước đó, phải kiểm xem plan còn cần không: các plan sau đã thêm nút "Robot đọc zrsd003" và form "Ra lệnh cho robot" trên trang Robot SAP, nên một phần phạm vi có thể đã được làm.

## Files

- Đọc plan: `plans/261113-1142-robot-manual-run-on-demand/plan.md` và 2 phase; `plans/reports/brainstorm-261113-1142-robot-manual-run-on-demand.md`
- Đọc mã (để biết phần nào đã có): `src/shoponline/web/routes/robot.py`, `src/shoponline/web/templates/robot.html`, `src/shoponline/sapjobs/report_requests.py`, `src/shoponline/sapjobs/queue.py`
- Đọc test: `tests/web/test_robot_web.py`
- Sửa: `plans/261113-1142-robot-manual-run-on-demand/plan.md` và phase file của nó (áp dụng phát hiện đã duyệt, có marker)
- Tạo: `plans/reports/data-integrity-audit-261123-<HHmm>-robot-on-demand.md`

## Implementation Steps

1. So phạm vi plan với mã hiện có. Ghi từng mục: đã có (commit nào), có một phần, hoặc chưa có.
2. Nếu phần lớn phạm vi đã có, hỏi chủ dự án nên đóng plan (`completed` hoặc `cancelled`, ghi lý do) hay thu hẹp phạm vi phần còn lại. Chỉ red team phần còn lại.
3. Red team phần còn lại: 2 reviewer (Security, Assumption), cộng lens trùng/sót. Chú ý: lệnh đọc khi cần chồng lên lịch đọc tự động hoặc lên lệnh khác cùng khoảng ngày có thể ghi trùng.
4. Cổng duyệt; áp dụng phát hiện được chấp nhận vào phase file với marker `<!-- Red Team: ... -->`; ghi `## Red Team Review`.
5. Validate theo `validate-workflow.md` (3–8 câu nếu cần); ghi `## Validation Log` và đưa quyết định vào phase file.

## Todo

- [x] Đối chiếu phạm vi với mã hiện có
- [x] Quyết định giữ, thu hẹp hay đóng plan (chủ dự án)
- [x] Red team và cổng duyệt
- [x] Validate

## Success Criteria

- Plan `261113-1142` có trạng thái đúng với thực tế, `## Red Team Review` và `## Validation Log` (hoặc lý do đóng plan, nếu chủ dự án chọn đóng).
