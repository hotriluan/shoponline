---
phase: 7
title: "Phase 7: Bất biến xuyên luồng trên production"
status: completed
priority: P1
effort: 5h
dependencies: [1]
---

# Phase 7: Bất biến xuyên luồng trên production

## Overview

Viết bất biến cho cả 7 luồng và chạy SQL chỉ đọc trên production (hoặc bản phục hồi của phase 1). Phase này cũng phụ trách hai luồng mà plan gốc đã qua red team nhưng mã chưa được rà về trùng/sót: luồng 3 (file kế toán gộp, `261113-1230`) và luồng 6 (tiền vô, `261119-0719`), cùng phần khôi phục của luồng 7 (`261123-0312`). Phase này nhận thêm SQL từ phase 2–5.

## Files

- Đọc mã: `src/shoponline/accounting/{ledger,runs}.py`, `src/shoponline/exports/accounting_workbook.py`, `src/shoponline/web/routes/accounting.py`, `src/shoponline/importers/settlement_files.py`, `src/shoponline/backup/restore.py`, `src/shoponline/db/models.py`, `migrations/versions/0006_accounting_runs.py`, `0009_platform_settlement.py`
- Đọc test: `tests/accounting/*`, `tests/exports/test_merged_accounting_workbook.py`, `tests/importers/test_settlement_files.py`, `tests/reconcile/test_settlement_ingest.py`, `tests/backup/test_restore.py`
- Đọc: `## Red Team Review` của `261113-1230`, `261119-0719`, `261123-0312` (không làm lại; chỉ kiểm xem rủi ro đã chấp nhận có xảy ra trên dữ liệu thật không)
- Tạo (scratchpad): `invariants.sql`
- Tạo: `plans/reports/data-integrity-audit-261123-<HHmm>-invariants.md`

## Bất biến khởi điểm (bổ sung từ phase 2–5)

Tên bảng và cột phải lấy từ `models.py` trước khi viết SQL; danh sách dưới đây mô tả ý nghĩa, không phải tên cột chính xác.

| # | Luồng | Bất biến | Vi phạm nghĩa là |
|---|---|---|---|
| I1 | Đơn | Mỗi `(platform, platform_order_id)` thuộc đúng một lô | trùng |
| I2 | Đơn | Mỗi đơn có ít nhất một dòng sản phẩm; tổng số lượng > 0 | sót dòng |
| I3 | SO/DO | Mỗi DO trong `sap_so_ref` trỏ tới đúng một đơn của ba sàn | trùng hoặc lạc |
| I4 | SO/DO | Đơn ở trạng thái "đã có DO" có ít nhất một DO | trạng thái sai |
| I5 | Kế toán | Mỗi DO được gửi kế toán tối đa một lần qua mọi đợt đã chốt | trùng |
| I6 | Kế toán | DO của ba sàn có PGI trước `max(ngày đợt đã chốt)` mà chưa có trong sổ đã gửi | sót |
| I7 | Lịch sử | Mỗi đơn có tối đa một dòng `sales_history_exported`, và đơn đó nằm trong đúng một file đã xác nhận | trùng |
| I8 | Lịch sử | Đơn "đã có DO", đặt hơn 45 ngày trước, chưa xuất: liệt kê theo lý do chặn | sót hoặc kẹt |
| I9 | Hóa đơn | DO của đơn đã xuất lịch sử đều có hóa đơn | xuất thiếu hóa đơn |
| I10 | Hóa đơn | Hóa đơn có `delivery` không khớp DO nào: đếm (khách ngoài ba sàn là bình thường; khách ba sàn là sót liên kết) | lạc |
| I11 | Tiền vô | Mỗi đơn đã xuất kèm Tiền Vô có tổng `platform_settlement` bằng giá trị đã xuất; đơn có tiền vô thay đổi sau khi xuất: đếm (rủi ro đã chấp nhận) | lệch sau xuất |
| I12 | Tiền vô | Dòng quyết toán có mã đơn không khớp đơn nào: đếm theo sàn | sót đơn hoặc sai mã |
| I13 | Tiền vô | Cùng đơn, cùng số tiền, cùng ngày, khác `line_key`: đếm | trùng do khóa dòng |
| I14 | Xóa | Đơn đã bị xóa dữ liệu khách mà chưa xuất lịch sử hoặc chưa gửi kế toán | xóa sớm |
| I15 | Khôi phục | `backup_run` có lần khôi phục; sau mốc đó có đơn hoặc DO bị xuất lại không (so `generated_file` trước và sau mốc) | trùng do khôi phục |

## Implementation Steps

1. Đọc mã kế toán, tiền vô, khôi phục và red team review của ba plan đã có; thêm bất biến nếu thấy chỗ hở mới.
2. Gộp SQL từ phase 2–5 vào `invariants.sql`. Mỗi câu chỉ trả **số đếm** và tối đa 20 mã đơn/DO làm mẫu, không trả tên, SĐT hay địa chỉ.
3. Đọc lại toàn file SQL; xác nhận chỉ có `SELECT`/`WITH`. Chạy trong phiên read-only (phase 1).
4. Với mỗi vi phạm > 0, lấy 1–3 mẫu, lần theo `event_log` và lịch sử file để tìm nguyên nhân (lỗi mã, thao tác tay, dữ liệu sàn, hay rủi ro đã chấp nhận). Phát hiện có nguyên nhân là lỗi mã thì trích `file:dòng`.
5. Ghi file bất biến: bảng `#`, bất biến, SQL (rút gọn), số đếm, mẫu (chỉ mã), kết luận, mức độ.

## Todo

- [x] Đọc mã kế toán, tiền vô, khôi phục
- [x] Hoàn thiện danh sách bất biến
- [x] Gộp và đọc lại SQL
- [x] Chạy SQL read-only, ghi số đếm
- [x] Lần nguyên nhân các vi phạm
- [x] File bất biến

## Success Criteria

- Mọi bất biến có số đếm thật, ghi kèm nguồn (production hoặc bản phục hồi, có thời điểm).
- Mọi vi phạm > 0 có kết luận nguyên nhân hoặc ghi "chưa rõ" kèm bước tiếp theo.
- File không chứa PII (grep `0\d{9}`, tên cột khách).
