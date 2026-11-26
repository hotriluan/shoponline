---
title: "Phase 2: Tài liệu và kiểm tra trên máy chạy thật"
status: in-progress
priority: P2
effort: "1h"
dependencies: [1]
---

# Phase 2: Tài liệu và kiểm tra trên máy chạy thật

## Overview

Ghi quy tắc mới vào tài liệu vận hành, rồi xác nhận trên máy chạy thật rằng đợt gửi kế toán bỏ đúng phiếu `ZDE1`.

## Context

- `docs/daily-operations.md` bước 12 (dòng 42) đã nói "số dòng không vào file theo từng lý do"; đây là chỗ sở hữu quy tắc.
- Máy chạy thật: `AlkanaDuongPC` (`192.168.18.123`, SSH alias `prod-win10`). Deploy qua GitHub Actions khi push lên `main` (`docs/deployment-guide.md`).
- Đã kiểm tra trên máy chạy thật (26/11): 5 delivery 1960001310 đến 1960001314 nằm trong `accounting_sent_delivery` với `run_id = 8`, vì sổ ghi theo `merged.deliveries` của đợt 8. Chúng sẽ không quay lại ở đợt sau. Sổ ghi chúng là "đã gửi" dù người dùng đã bỏ tay khỏi file; việc này vô hại nên để nguyên, không sửa dữ liệu.

## Requirements

- [x] `docs/daily-operations.md` bước 12: thêm một câu: phiếu nhập hàng trả về (`Delivery Type` khác `ZDA1`, ví dụ `ZDE1` vào kho QC `0301`) không vào file kế toán và được đếm ở lý do "không phải phiếu giao bán".
- [ ] Sau deploy, đọc thử một đợt có phiếu `ZDE1` mới (hoặc chạy builder chỉ đọc trên một file thật) và thấy lý do mới, không có cảnh báo thiếu mã đơn cho dòng `ZDE1`.

## Implementation Steps

1. Sửa `docs/daily-operations.md` (đọc trước khi sửa, giữ đúng giọng văn tiếng Việt hiện có).
2. Commit theo conventional commit, ví dụ `fix(accounting): keep only sales deliveries in the accounting file`. Push lên `main` khi người dùng đồng ý.
3. Theo dõi job deploy xanh (`gh run list --limit 3`).
4. Trên máy chạy thật, qua SSH, chạy script chỉ đọc: gọi `build_merged_accounting_workbook` trên file kế toán đợt 8 (`C:\shoponline-data\exports\20261126-104255-accounting_file-593fccbc.xlsx`, đã có ba cột chèn; dùng `exclude_deliveries=set()`, `cutoff=None`). Kỳ vọng `dropped` có 5 dòng lý do mới và không có dòng `ZDE1` trong kết quả. Xóa script tạm sau khi chạy.
5. Lần đọc ZRSD004 kế tiếp có phiếu `ZDE1`: xem trang Robot SAP không còn cảnh báo cho SO `2000…`.

## Todo

- [x] Cập nhật `docs/daily-operations.md`
- [x] Commit và push (sau khi người dùng đồng ý)
- [x] Deploy xanh
- [x] Kiểm tra chỉ đọc trên máy chạy thật với file đợt 8

## Verification

- `gh run list --limit 3` cho thấy deploy thành công.
- Kết quả script kiểm tra trên máy chạy thật in `dropped` có lý do mới với 5 dòng.

## Success Criteria

Tài liệu khớp hành vi mới. Trên dữ liệu thật của đợt 8, builder mới bỏ đúng 5 phiếu `ZDE1`.

## Risks

- File đợt 8 đã có ba cột chèn; `_insert_columns` nhận ra và không chèn lại, nên đọc lại được. Nếu header lệch, dùng một file ZRSD004 gốc mới từ robot thay thế.

## Rollback

Revert commit tài liệu cùng commit mã; push lại để deploy bản cũ.
