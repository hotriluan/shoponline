---
title: "Phase 2: Tài liệu và kiểm trên production"
status: in-progress
---

# Phase 2: Tài liệu và kiểm trên production

## Overview

Cập nhật tài liệu vận hành cho ô chọn tháng và khoảng đọc zrsd003 mới, rồi kiểm một lần đọc thật.

## Files

- Sửa: `docs/daily-operations.md` (bước 2 mục file Shop Online, dòng ~45: thay "Ô Đến ngày đặt hàng mặc định là hôm nay; khi chốt tháng thì chọn ngày cuối tháng" bằng ô Tháng đặt hàng, mặc định tháng trước)
- Sửa: `docs/robot-runbook.md` (dòng ~13: Billing Date từ ngày 1 của tháng chọn, hoặc ngày đặt sớm hơn của đơn tồn, đến hôm nay)
- Kiểm: `docs/system-architecture.md` có nhắc khoảng đọc zrsd003 hay `until` không; sửa nếu có.

## Implementation Steps

1. Đọc từng file trước khi sửa; chỉ sửa câu nói về ô ngày và khoảng đọc.
2. Ghi rõ lý do khoảng kết thúc ở hôm nay: hóa đơn của đơn cuối tháng ra trong tháng sau.
3. Sau khi deploy (chủ dự án quyết định thời điểm), chọn tháng 10/2026, bấm "Robot đọc zrsd003" một lần; ghi thời gian chạy và số dòng đọc vào journal. Nếu robot hết giờ chờ, báo chủ dự án trước khi đổi gì.

## Todo

- [x] `daily-operations.md`
- [x] `robot-runbook.md`
- [x] `system-architecture.md` (không nhắc khoảng đọc hay ô ngày; không sửa)
- [ ] Kiểm lần đọc thật trên production và ghi journal

## Success Criteria

Tài liệu khớp hành vi của phase 1; lần đọc thật cho tháng 10/2026 xong và đơn tháng 10 có hóa đơn không còn bị chặn vì thiếu Tax Invoice Doc.
