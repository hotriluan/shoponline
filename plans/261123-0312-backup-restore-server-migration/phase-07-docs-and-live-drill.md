---
phase: 7
title: "Tài liệu và diễn tập trên máy thật"
status: in-progress
priority: P1
effort: "1d"
dependencies: [1, 2, 3, 4, 5, 6]
---

# Phase 7: Tài liệu và diễn tập trên máy thật

<!-- Updated: Red Team 2026-11-23 - thêm .env.example, system-architecture, diễn tập bản cũ và bản trước migration, rollback tác vụ đầy đủ -->

## Goal

Tài liệu khớp hệ thống mới, và mọi tiêu chí chưa test tự động được kiểm chứng trên máy chạy thật, ghi lại thành báo cáo diễn tập.

## Context

- Tài liệu hiện tại: [README.md](../../README.md) (bảng biến và lệnh), [deployment-guide.md](../../docs/deployment-guide.md) (mục 4, 5, 6, chuyển máy, khi máy hỏng), [security-and-data-retention.md](../../docs/security-and-data-retention.md) (bảng dữ liệu, mục Bản sao lưu, bảng bí mật, người rời vai trò), [operations-runbook.md](../../docs/operations-runbook.md), [daily-operations.md](../../docs/daily-operations.md).
- Cần chủ dự án: tạo OAuth client (hướng dẫn 4 bước) trên Gmail cá nhân, cất Client ID/Secret vào kho bí mật.

## Files to Create / Modify

- Modify: `README.md` (dòng 44, 65–67) — lệnh `backup …`, `drive …`; bỏ `SHOPONLINE_BACKUP_KEEP_DAYS` (ghi rằng biến này không còn tác dụng)
- Modify: `.env.example` (dòng 15–21) — bỏ `SHOPONLINE_BACKUP_KEEP_DAYS`, sửa chú thích sao lưu
- Modify: `docs/system-architecture.md` (dòng 14, 94, 98) — schema `ops` và quy tắc migration `ops` idempotent; tác vụ sao lưu 15 phút, tác vụ phục hồi; bỏ `last-backup.txt` khỏi mô tả cảnh báo
- Modify: `docs/deployment-guide.md` — mục 4–6 theo hệ thống mới (dòng 69 `-BackupTime`, 75, 98 về `-OnlyMissing` giữ trigger trừ `shoponline-backup`); thay quy trình chuyển máy 8 bước bằng hai lệnh, giữ "Hai điều không được xảy ra cùng lúc"; "Khi máy hỏng" dùng `-Bundle drive:latest` và bước rào máy cũ; ghi rằng web, các tác vụ và lệnh `drive connect` phải cùng một tài khoản Windows
- Modify: `docs/security-and-data-retention.md` — bản sao lưu gồm thư mục dữ liệu (trừ log) và `.env`; giữ mặc định `db` 15 bản (≈15 ngày), `app` 15 bản, `full` tối đa 30 ngày, đều trong 90 ngày; web chỉ cho đặt `full_max_days` tới 90; phục hồi không lùi tài khoản web và buộc đăng nhập lại; bảng bí mật thêm Client ID/Secret và refresh token Drive (Credential Manager); bản sao lưu phụ thuộc Gmail cá nhân; thủ tục khi người rời vai trò thêm ngắt Drive
- Modify: `docs/operations-runbook.md`, `docs/daily-operations.md` — trang Sao lưu thay cho kiểm tra thư mục tay (chỉ chỗ có nhắc sao lưu)
- Create: `plans/reports/live-check-<yyMMdd-HHmm>-backup-restore.md` — kết quả diễn tập

## Tasks & Steps

1. Deploy lên máy thật qua push `main`; job `deploy` xanh (tiêu chí 9 — bản `deploy` mới xuất hiện trong bảng).
2. Chủ dự án tạo OAuth client; trên web lưu Client ID/Secret, kết nối bằng mã thiết bị, kiểm tra kết nối (tiêu chí 11).
3. Bấm ba nút sao lưu; cả ba lên Drive, MD5 khớp (tiêu chí 1, 2, 16).
4. Ngắt mạng Internet tạm hoặc ngắt kết nối Drive: bản mới chỉ ở máy chủ, mã thoát 2, cột Drive báo lỗi dễ hiểu; nối lại, **Thử lại** thành công (tiêu chí 3, 19).
5. Diễn tập phục hồi bản `full` từ web: số dòng khớp. Diễn tập thêm một bản cũ (định dạng trước phase 1) để kiểm đường "legacy".
6. Phục hồi thật từ web ngoài giờ xử lý đơn, với một bản `db` tạo **trước** migration gần nhất (để kiểm đường thay schema `public` + `migrate`): web tắt, bật lại, banner thành công, số dòng khớp, mọi người phải đăng nhập lại, tài khoản và nhật ký sao lưu không đổi. Ghi lại `schtasks /Run` từ tiến trình web có chạy được tác vụ không.
7. `server-export.ps1 -Prepare` trên máy thật; dựng máy thử (máy phụ hoặc máy ảo) bằng `-Bundle drive:latest -Prepare`; số dòng khớp; không cài runner. Gỡ máy thử.
8. Sau 24 giờ: lịch `db` 16:30 đã chạy tự động trong giờ làm việc mà web và robot vẫn chạy bình thường, xoay vòng đúng.
9. Cập nhật tài liệu, kiểm tra mọi link trong các file đã sửa còn đúng.
10. Ghi báo cáo diễn tập: mỗi tiêu chí 1–23 với bằng chứng (test, ảnh màn hình, lệnh) hoặc lý do chưa đạt.

## Verification

- Báo cáo diễn tập có đủ 23 dòng.
- `uv run pytest` và `uv run ruff check` xanh trên main.
- Link trong tài liệu đã sửa trỏ tới file và mục có thật.

## Risks

- Phục hồi thật trên máy thật là thao tác rủi ro: làm ngoài giờ, với bản vừa tạo, sau khi diễn tập thành công; bản an toàn tự tạo trước.
- Không có máy phụ để thử chuyển máy: dùng máy dev với database và thư mục dữ liệu riêng, ghi rõ trong báo cáo.

## Rollback

Tài liệu revert được bằng git. Tác vụ trên máy thật: `-OnlyMissing` giữ trigger nên không đủ để lùi; chạy `register-tasks.ps1 -AtLogOn` **không** có `-OnlyMissing` từ commit trước (trả trigger hằng ngày cho `shoponline-backup`) và `Unregister-ScheduledTask shoponline-restore`. Migration giữ nguyên (roll-forward, xem phase 1).
