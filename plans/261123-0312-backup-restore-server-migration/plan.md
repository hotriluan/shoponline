---
title: "Sao lưu, khôi phục và chuyển máy chạy thật"
description: "Nâng sao lưu PowerShell hiện có thành module Python có trang quản trị web, tải lên Google Drive qua API, khôi phục an toàn và chuyển máy bằng hai lệnh."
status: in-progress
priority: P1
effort: 11.5d
branch: main
tags: [feature, backend, database, infra, frontend]
blockedBy: []
blocks: []
created: 2026-11-23
---

# Sao lưu, khôi phục và chuyển máy chạy thật

## Overview

Nâng sao lưu PowerShell hiện có thành module Python có trang quản trị web, tải lên Google Drive qua API, khôi phục an toàn và chuyển máy bằng hai lệnh. Thiết kế, các lựa chọn đã so sánh và quyết định của chủ dự án nằm ở [brainstorm report](../reports/brainstorm-261123-0955-backup-restore-server-migration.md). Báo cáo đó là nguồn của 23 tiêu chí nghiệm thu; plan này chỉ chia việc.

Phạm vi: HOLD SCOPE (không có `--yagni`). Bảy phase vì tính năng chạm năm tầng độc lập (lõi sao lưu, Google API, khôi phục, web, PowerShell chuyển máy).

## Quyết định đã chốt

- Ba loại bản sao lưu `db` / `app` / `full`, file `.7z` AES-256 có `manifest.json`; tên `shoponline-<kind>-<db>-yyyyMMdd-HHmmss.7z`, tên cũ hiểu là `db`.
- Lịch: `db` 1 lần/ngày (16:30) + trước mỗi deploy; `full` thứ Sáu 16:30 (chạy ngay sau `db`); `app` chỉ bấm tay. Giữ: `db` 15 bản, `app` 15 bản gần nhất; `full` tối đa 30 ngày (theo tuổi, không theo số bản); như nhau ở máy chủ và Drive. Bản `app`/`full` không chép log.
- Giao hàng từng phase lên `main` (mỗi phase tự deploy).
- Google Drive: Gmail cá nhân, Drive API gọi trực tiếp bằng `httpx`, scope `drive.file`, OAuth device flow, client loại "TVs and Limited Input devices" đã Publish to production. Client Secret và refresh token trong Windows Credential Manager.
- `.env` (trừ `SHOPONLINE_BACKUP_PASSWORD`) nằm trong bản `app`/`full`.
- Phục hồi hệ thống thật có nút trên web, chạy qua tác vụ `shoponline-restore`, tự lùi lại bằng bản an toàn khi lỗi.
- Schema `ops` chứa tài khoản web và sổ sách sao lưu; phục hồi trên cùng máy chỉ thay `public`, nên tài khoản **không** lùi theo bản sao lưu (chủ dự án chốt), mọi người đăng nhập lại. Mọi migration đụng `ops` phải idempotent.
- Bản sao lưu trước deploy chỉ ở máy chủ, không lên Drive (chủ dự án chốt).
- Sao lưu không lấy được khóa thoát mã 3 (không bao giờ 0); deploy và phục hồi loại trừ nhau bằng file đánh dấu bảo trì.
- `restore-db.ps1` giữ nguyên; bản sao lưu cũ không manifest vẫn diễn tập và phục hồi được.

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Lõi sao lưu, lịch và xoay vòng](./phase-01-backup-core.md) | Done |
| 2 | [Google Drive client](./phase-02-google-drive-client.md) | Done |
| 3 | [Khôi phục](./phase-03-restore-engine.md) | Done |
| 4 | [Web: kết nối Drive, sao lưu ngay, cài đặt](./phase-04-web-drive-and-settings.md) | Done |
| 5 | [Web: danh sách, nhật ký, phục hồi, tải lên](./phase-05-web-backup-list-and-restore.md) | Done |
| 6 | [Chuyển máy chạy thật](./phase-06-server-migration.md) | Done |
| 7 | [Tài liệu và diễn tập trên máy thật](./phase-07-docs-and-live-drill.md) | Docs done; live drill pending |

Thứ tự: 1 → 2 → 3 → 4 → 5 → 6 → 7. Phase 4 cần 1 và 2; phase 5 cần 3 và 4; phase 6 cần 1–3.

## Dependencies

- Ngoài repo: Google Cloud project + OAuth client của chủ dự án (cần trước phase 7, không chặn phase 2 vì test giả lập Google).
- Máy chạy thật đã cài 7-Zip, PostgreSQL 16 bin, pywin32 (`--extra robot`).
- Mỗi phase merge được độc lập; deploy giữa chừng không làm hỏng sao lưu hiện có (phase 1 giữ hợp đồng `backup-db.ps1`).

## Success Criteria

- [ ] 23 tiêu chí trong brainstorm report đều có bằng chứng (test, lệnh, hoặc ghi chép diễn tập ở phase 7).
- [ ] `uv run pytest` và `uv run ruff check` xanh; job `deploy` xanh trên máy chạy thật.
- [ ] Diễn tập trên máy thật: sao lưu `full` lên Drive, phục hồi diễn tập khớp số dòng, `server-export -Prepare` + dựng máy thử từ gói.

## Red Team Review

### Session — 2026-11-23
**Findings:** 15 sau khi gộp 40 (15 chấp nhận, trong đó 3 có chỉnh; 2 đề xuất con bị bác)
**Severity breakdown:** 4 Critical, 7 High, 4 Medium
Chi tiết và lý do: [reports/red-team-261123-1020-backup-restore-plan.md](./reports/red-team-261123-1020-backup-restore-plan.md)

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | Phục hồi bản cũ hơn migration luôn lỗi ở `migrate` | Critical | Accept | Phase 3 |
| 2 | Khóa bận thoát 0; bản an toàn không lấy được khóa | Critical | Accept | Phase 1, 3, 6 |
| 3 | `-Bundle drive:latest` sai thứ tự | Critical | Accept | Phase 2, 6 |
| 4 | Phục hồi làm phiên trỏ nhầm tài khoản | Critical | Accept (modified: giữ tài khoản, hủy phiên) | Phase 1, 3, 5 |
| 5 | Nạp lại sổ sách bằng JSON dễ vỡ | High | Accept (schema `ops`) | Phase 1, 2, 3, 5 |
| 6 | Wrapper `restore-db.ps1` và bản cũ không manifest | High | Accept | Phase 3, 6 |
| 7 | Deploy chạy chồng phục hồi | High | Accept | Phase 3 |
| 8 | Vòng đời tác vụ và yêu cầu | High | Accept | Phase 1, 3, 4, 5, 7 |
| 9 | Tác vụ sao lưu giữ venv lúc `uv sync`; `--extra robot` | High | Accept | Phase 1, 2 |
| 10 | Số dòng manifest khác thời điểm dump | High | Accept | Phase 1 |
| 11 | Chấp nhận gói không mã hóa; giải nén không giới hạn | High | Accept (modified: bỏ ghim phiên bản 7-Zip) | Phase 1, 3, 5 |
| 12 | Dữ liệu giải mã nằm trong `%TEMP%` | High | Accept | Phase 1, 3 |
| 13 | Xoay vòng đưa lại "giữ mọi bản hôm nay" | High | Accept | Phase 1 |
| 14 | Quyền GET, giới hạn upload, banner, cache, `last_seen_at`, mật khẩu trong log | Medium | Accept | Phase 1, 3, 4, 5 |
| 15 | Phình phạm vi, lặp code, rollback, tài liệu thiếu | Medium | Accept (modified: giữ migration riêng mỗi phase) | Phase 1–7 |

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01 … phase-07
- Decision deltas checked: 9 (schema `ops`, bỏ `restore_request`, bỏ JSON reload, mã thoát 3, `restore-db.ps1` giữ nguyên, chế độ `--new-machine` thay `import-bundle`/`verify-counts`, bỏ biến `PG_BIN`/`7ZIP`, `service-control.ps1` thay `tasks.py`, xoay vòng N bản thuần)
- Reconciled stale references: 0 còn lại (grep các thuật ngữ cũ chỉ còn trong ghi chú lịch sử)
- Unresolved contradictions: 0

## Validation Log

### Session 1 — 2026-11-23

#### Verification Results
- **Tier:** Full (7 phase)
- **Claims checked:** 26 (bởi bốn reviewer red-team, cộng kiểm lại sau khi sửa)
- **Verified:** 26 | **Failed:** 0 | **Unverified:** 1 — tiến trình web quyền thường có chạy được `schtasks /Run` cho tác vụ đăng ký bằng quyền quản trị không; phase 7 kiểm trên máy thật, có đường dự phòng là tác vụ 15 phút.

#### Questions & Answers
1. **Giao hàng:** từng phase lên `main` hay nhánh riêng? → Từng phase lên `main`.
2. **Thời hạn bản `full`:** 15 bản ≈ 15 tuần vượt 90 ngày → Chủ dự án chốt **giữ 4 bản `full`**; `db` và `app` giữ 15. Áp vào phase 1, 4, 7.
3. **Log trong bản `app`/`full`:** → Không chép log. Áp vào phase 1.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01 … phase-07
- Decision deltas checked: 3 (`keep_*` theo loại thay `local_keep`/`drive_keep`; `full` giữ 4; loại `logs` khỏi gói)
- Reconciled stale references: 3 (phase 1 data model, phase 4 form cài đặt, phase 7 tài liệu bảo mật)
- Unresolved contradictions: 0

### Session 2 — 2026-11-23

#### Questions & Answers
1. **Thời hạn bản `full`:** chủ dự án đổi "giữ 4 bản" thành **"giữ tối đa 30 ngày"**. Áp dụng theo tuổi vì đếm số bản không bảo đảm được giới hạn 30 ngày khi lịch tuần ngừng chạy. Hệ quả đã ghi: bản `full` cuối cùng cũng bị xóa khi quá 30 ngày; banner cảnh báo khi 8 ngày không có bản `full` thành công. Áp vào phase 1, 4, 7.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01, phase-04, phase-07
- Decision deltas checked: 1 (`keep_full` → `full_max_days`)
- Reconciled stale references: 4 (data model, retention, form cài đặt, tài liệu bảo mật); Session 1 giữ nguyên làm lịch sử
- Unresolved contradictions: 0

### Session 3 — 2026-11-23

#### Questions & Answers
1. **Giờ sao lưu tự động:** chủ dự án đổi từ nửa đêm sang **16:30**. Áp cho cả `db` (hằng ngày) và `full` (Chủ nhật); hai loại cùng tới hạn thì chạy `db` trước, `full` sau. Sao lưu không dừng web hay robot (`pg_dump` đọc trên snapshot), nên chạy trong giờ làm việc không làm gián đoạn người dùng; manifest vẫn nhất quán nhờ snapshot. Giờ vẫn sửa được trên web. Áp vào phase 1, 7.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01, phase-04, phase-07
- Decision deltas checked: 1 (giờ mặc định 23:00/23:15 → 16:30)
- Reconciled stale references: 3 (data model phase 1, diễn tập phase 7, quyết định trong plan.md); phase 4 không ghi giờ cụ thể
- Unresolved contradictions: 0

### Session 4 — 2026-11-23

#### Questions & Answers
1. **Ngày chạy bản `full` hằng tuần:** chủ dự án đổi từ Chủ nhật sang **thứ Sáu** (16:30, ngay sau bản `db` cùng ngày). Ngày vẫn sửa được trên web. Áp vào phase 1.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01, phase-04, phase-07
- Decision deltas checked: 1 (`full_weekday` 6 → 4)
- Reconciled stale references: 3 (data model và bước chạy cùng hạn ở phase 1, quyết định trong plan.md); Session 3 giữ nguyên làm lịch sử
- Unresolved contradictions: 0

<!-- slug: backup-restore-server-migration -->
