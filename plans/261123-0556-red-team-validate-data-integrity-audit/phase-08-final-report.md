---
phase: 8
title: "Phase 8: Báo cáo tổng hợp"
status: completed
priority: P1
effort: 2h
dependencies: [2, 3, 4, 5, 6, 7]
---

# Phase 8: Báo cáo tổng hợp

## Overview

Gộp file nền và sáu file phát hiện thành một báo cáo cho chủ dự án, xếp theo mức độ, kèm danh sách việc sửa đề xuất để duyệt.

## Files

- Đọc: `plans/reports/data-integrity-audit-261123-*-{baseline,orders-sap,history-file,tax-invoice,deletion-machine,robot-on-demand,invariants}.md`, `## Red Team Review` và `## Validation Log` mới của 9 plan
- Tạo: `plans/reports/data-integrity-audit-261123-<HHmm>-final.md`
- Sửa: `plan.md` của plan này (trạng thái)
- Tạo: một journal qua `/ak-journal`

## Implementation Steps

1. Gộp phát hiện; bỏ trùng giữa phase (cùng gốc lỗi, khác triệu chứng thì gộp một dòng và liệt kê triệu chứng).
2. Xếp hạng: **Critical** khi đã có dữ liệu trùng hoặc sót thật trên production; **High** khi tái hiện được bằng test hoặc đường đi rõ trong mã nhưng production chưa gặp; **Medium** khi cần điều kiện hiếm hoặc thao tác tay sai; **Low** cho vấn đề tài liệu hoặc trạng thái plan.
3. Mỗi dòng ghi: mức, luồng, plan gốc, mô tả một câu, bằng chứng (`file:dòng`, test, hoặc `I#` + số đếm), đề xuất (`/ak-fix`, plan mới, chấp nhận rủi ro, hay sửa dữ liệu bằng tay có sao lưu trước).
4. Phần đầu báo cáo: trả lời trực tiếp câu hỏi của chủ dự án cho từng nhóm dữ liệu (đơn hàng, báo cáo, hóa đơn, tiền vô, file kế toán): hiện có trùng/sót không, bao nhiêu, rủi ro còn lại.
5. Bảng trạng thái 9 plan: red team (số phát hiện Accept/Reject), validate (Verified/Failed/Unverified).
6. Kiểm cuối: `git diff --stat main -- src tests migrations` rỗng; grep PII trên mọi file báo cáo; link trong báo cáo mở được.
7. Đặt plan này `completed`, ghi journal.

## Todo

- [x] Gộp và xếp hạng phát hiện
- [x] Trả lời theo nhóm dữ liệu
- [x] Bảng trạng thái 9 plan
- [x] Kiểm cuối (không đổi mã, không PII, link đúng)
- [x] Journal

## Success Criteria

Chủ dự án đọc phần đầu báo cáo là biết, với từng nhóm dữ liệu, hiện có trùng hoặc sót hay không, và việc gì cần duyệt để sửa.
