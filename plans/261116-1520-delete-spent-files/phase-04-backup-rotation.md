---
phase: 4
title: "Mỗi ngày giữ một bản sao lưu, giữ 14 ngày"
status: completed
---

# Phase 04: Mỗi ngày giữ một bản sao lưu, giữ 14 ngày

Quyết định của chủ dự án (2026-11-16): sao lưu tự động mỗi ngày một lần, giữ 14 ngày; vẫn sao lưu trước mỗi lần deploy.

## Hiện trạng

`C:\shoponline-backup` có 17 bản trong 4 ngày (ngày 13/11 có 8 bản). Nguyên nhân: [update-production.ps1:144](../../scripts/windows/update-production.ps1#L144) sao lưu trước mỗi lần deploy, và tác vụ 23:00 chạy bù khi máy bật lại (StartWhenAvailable). [backup-db.ps1:61-63](../../scripts/windows/backup-db.ps1#L61-L63) chỉ xóa bản cũ hơn `SHOPONLINE_BACKUP_KEEP_DAYS` (mặc định 30).

## Files

- Sửa: [scripts/windows/backup-db.ps1](../../scripts/windows/backup-db.ps1)
- Sửa nếu có ghi số 30: `docs/`, [setup-production-machine.ps1](../../scripts/windows/setup-production-machine.ps1) phần ghi `.env`

## Steps

1. Mặc định `SHOPONLINE_BACKUP_KEEP_DAYS` = 14.
2. Sau khi chép bản mới thành công vào một thư mục: nhóm các file `shoponline-<db>-yyyyMMdd-HHmmss.7z` theo ngày trong tên file; với các ngày trước hôm nay chỉ giữ bản mới nhất; xóa mọi bản của ngày cũ hơn 14 ngày. Hôm nay giữ hết (bản lúc deploy là điểm lùi của lần migrate đó).
3. Không đổi lịch tác vụ và bước sao lưu lúc deploy.
4. Không xóa gì khi sao lưu lỗi (giữ như hiện tại: chỉ dọn sau khi chép xong).

## Validation

- Chạy script với một thư mục thử chứa file giả có tên trải trên 20 ngày, nhiều bản mỗi ngày: còn đúng một bản mỗi ngày trong 14 ngày, hôm nay còn đủ.
- Chạy thật một lần trên máy này; `C:\shoponline-backup` còn một bản cho mỗi ngày 12, 13 và tất cả bản của hôm nay.

## Risk và rollback

- `C:\shoponline-backup` nằm cùng ổ với database. Cần xác nhận `SHOPONLINE_BACKUP_DIRS` có ít nhất một nơi ngoài máy (thư mục mạng hoặc Google Drive); việc này do chủ dự án kiểm tra, không nằm trong code.
- Rollback: revert script; bản đã xóa không lấy lại được.
