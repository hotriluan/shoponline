---
phase: 1
title: "Phase 1: Chuẩn bị truy cập, trạng thái và số đếm nền"
status: completed
priority: P1
effort: 3h
dependencies: []
---

# Phase 1: Chuẩn bị truy cập, trạng thái và số đếm nền

## Overview

Mở đường truy vấn chỉ đọc tới DB production, sửa trạng thái plan bị lệch, và chụp số đếm nền để các phase sau so sánh.

## Files

- Đọc: `docs/deployment-guide.md`, `docs/system-architecture.md`, `docs/security-and-data-retention.md`, `.env.example`, `src/shoponline/db/models.py`, `migrations/versions/*.py`
- Sửa: `plans/261113-1230-merged-accounting-file/plan.md` (chỉ trạng thái và bảng phase)
- Tạo: `plans/reports/data-integrity-audit-261123-<HHmm>-baseline.md`
- Tạo (scratchpad, không commit): `readonly-session.sql`, `baseline-counts.sql`

## Implementation Steps

1. **Chọn đường truy cập.** Đọc `docs/deployment-guide.md` để biết cách kết nối DB trên `AlkanaDuongPC`.
   - Cách A (ưu tiên): role chỉ đọc nếu đã có. Nếu chưa có, hỏi chủ dự án có muốn tạo role `shoponline_readonly` (`GRANT SELECT` trên schema `public` và `ops`) không. Việc tạo role là thay đổi trên production, nên chỉ làm khi được đồng ý.
   - Cách B: dùng tài khoản ứng dụng với `SET default_transaction_read_only = on;` ở đầu mỗi phiên.
   - Cách C (dự phòng): phục hồi bản `db` mới nhất vào `SHOPONLINE_RESTORE_DATABASE_URL` trên máy dev bằng `uv run shoponline backup restore <bản> --drill`. Ghi ngày giờ của bản.
2. Thử kết nối bằng một câu `SELECT 1`, rồi thử `CREATE TEMP TABLE x(i int)`. Câu thứ hai phải bị từ chối, đó là bằng chứng phiên đang chỉ đọc.
3. **Số đếm nền**: số dòng mỗi bảng trong `public`; số đơn theo `platform` × trạng thái (`domain/states.py`); số lô theo sàn; số DO trong `accounting_sent_delivery`; số dòng `sales_history_exported`, `sap_tax_invoice`, `platform_settlement`. Chỉ ghi số đếm, không ghi dòng dữ liệu.
4. **Sửa trạng thái lệch**: đối chiếu `plans/261113-1230-merged-accounting-file/plan.md` với `git log` (`1db7fdb`), các test `tests/accounting/*`, và journal ngày 2026-11-13. Cập nhật `status` và cột trạng thái phase cho đúng (đã làm, còn chạy thử production nếu chưa có bằng chứng). Quét nhanh 8 plan còn lại để tìm lệch tương tự; nếu thấy thì ghi vào file nền, chưa sửa (phase phụ trách plan đó sẽ quyết).
5. Ghi file nền: đường truy cập đã dùng, thời điểm chụp, bảng số đếm, danh sách lệch trạng thái.

## Todo

- [x] Chọn và thử đường truy cập chỉ đọc (có bằng chứng phiên bị từ chối ghi)
- [x] Chụp số đếm nền
- [x] Sửa trạng thái plan `261113-1230`
- [x] Ghi file nền

## Success Criteria

- Có một lệnh kết nối chỉ đọc chạy được, được ghi trong file nền nhưng không kèm mật khẩu.
- File nền có số đếm mọi bảng `public` và thời điểm chụp.
- Trạng thái plan `261113-1230` khớp với mã và journal.

## Risk

- Ghi nhầm vào production: chỉ chạy câu đã đọc lại; phiên luôn read-only; không có lệnh nào ngoài `SELECT`, `SET`, `SHOW`, `EXPLAIN`.
- Mật khẩu DB lộ vào log hoặc báo cáo: lấy từ `.env` trên máy hoặc `ak secrets`; không in giá trị ra.
