---
phase: 6
title: "Chuyển máy chạy thật"
status: completed
priority: P1
effort: "1.5d"
dependencies: [1, 2, 3]
---

# Phase 6: Chuyển máy chạy thật

<!-- Updated: Red Team 2026-11-23 - thứ tự migrate → kết nối Drive → nhập gói, chế độ máy mới thay import-bundle, kiểm runner theo nhãn kể cả offline, rào máy cũ, bỏ -DryRun -->

## Goal

Chuyển máy bằng hai lệnh: máy cũ `server-export.ps1 [-Prepare | -Rollback]`, máy mới `setup-production-machine.ps1 -Bundle <file | drive:latest>`; tự đối chiếu số dòng và bảo đảm không bao giờ có hai runner nhãn `shoponline-prod` hay hai robot cùng chạy.

## Context

- Quy trình tay hiện tại: [deployment-guide.md](../../docs/deployment-guide.md#chuyển-máy-chạy-thật-sang-máy-khác).
- [setup-production-machine.ps1](../../scripts/windows/setup-production-machine.ps1) có `-Archive`, `-DataSource`, `-Prepare`; dòng 215–228 kiểm database trống bằng số bảng `public` rồi gọi `restore-db.ps1` (giữ nguyên đường này).
- Runner: tên `$COMPUTERNAME-shoponline`, nhãn `shoponline-prod` (`install-deploy-runner.ps1:26-27`). Khóa robot là advisory lock trên từng database (`saprobot/worker.py:488`), nên hai máy hai database không chặn nhau.
- Credential Manager không đi theo bản sao lưu: máy mới nhập lại cùng Client ID/Secret, kết nối lại Drive, `sap-password set`.
- Phase 3 đã có `restore_public_schema`. Brainstorm: lựa chọn D, tiêu chí 8. Red-team: mục 2, 3, 15 và phát hiện rào máy cũ.

## Files to Create / Modify

- Create: `scripts/windows/server-export.ps1` — dot-source `service-control.ps1`
- Modify: `scripts/windows/setup-production-machine.ps1` — tham số `-Bundle`; giữ `-Archive`, `-DataSource`
- Modify: `src/shoponline/backup/restore.py` — chế độ `new_machine`: dùng `restore_public_schema`, rồi chép `ops.app_user` và `ops.backup_settings` từ gói (các bảng `ops` khác giữ của máy mới), chép thư mục dữ liệu, ghi `.env`
- Modify: `src/shoponline/cli.py` — `backup restore <file> --new-machine [--force]`; `backup fetch-latest --kind full --to <thư mục>`
- Create: `tests/backup/test_new_machine_restore.py`

## Tasks & Steps

1. `server-export.ps1 -Prepare` (máy cũ vẫn chạy): `backup run --kind full --reason migration`, in đường dẫn ở máy chủ và tên trên Drive. Không dừng gì.
2. `server-export.ps1` (ngày chuyển), dừng ngay khi một bước lỗi và in bước tiếp theo:
   1. Không có job Actions đang chạy (`gh run list --status in_progress`); ghi đánh dấu bảo trì `migration`.
   2. Dừng và Disable `shoponline-deploy-runner` (cả `Runner.Listener`), `shoponline-robot`, `shoponline-web`, `shoponline-backup`, `shoponline-restore`; đợi tiến trình Python của các tác vụ này thoát.
   3. `backup run --kind full --reason migration` (khóa chờ có hạn, mã 3 là lỗi). Phải thành công cả máy chủ và Drive, không thì dừng ở đây, in lệnh `-Rollback`.
   4. Disable `shoponline-retention`.
   5. Gỡ runner khỏi repo, kiểm `gh api repos/hotriluan/shoponline/actions/runners` không còn runner tên máy này.
   6. Ghi `<SHOPONLINE_DATA_DIR>\released.json` (thời điểm, tên bản). Để ở file, không ở database: database được chép sang máy mới, cờ trong đó sẽ đi theo sang máy mới.
3. `server-export.ps1 -Rollback`: từ chối nếu GitHub có runner nhãn `shoponline-prod` (bất kể online hay offline) không phải của máy này; Enable lại tác vụ, `install-deploy-runner.ps1`, bật web và robot qua `service-control.ps1`, xóa `released.json` và đánh dấu bảo trì.
4. `setup-production-machine.ps1 -Bundle`, theo thứ tự:
   1. Cài công cụ, `uv sync --frozen --no-dev --extra robot`, tạo database, `.env` tối thiểu (hỏi mật khẩu sao lưu), `migrate` — database có schema rỗng dữ liệu.
   2. `drive:latest`: `drive set-client` (cùng Client ID/Secret của project cũ), `drive connect`, `backup fetch-latest --kind full`. Đường dẫn file: dùng trực tiếp.
   3. `backup restore <gói> --new-machine`: từ chối khi `public` đã có dữ liệu nghiệp vụ (`sales_order` > 0) trừ `--force`; thay `public`; chép `ops.app_user`, `ops.backup_settings`; chép thư mục dữ liệu; ghi `.env` từ gói cho các dòng chưa có, với `SHOPONLINE_WEB_HOST` = IP máy mới; `migrate`; so số dòng với manifest — lệch thì dừng trước bước runner.
   4. Trước khi cài runner và bật robot (không `-Prepare`): GitHub không còn runner nào mang nhãn `shoponline-prod`, kể cả offline. Còn thì dừng và hướng dẫn chạy `server-export.ps1` trên máy cũ, hoặc nếu máy cũ đã hỏng: gỡ runner cũ trên GitHub bằng tay (Settings → Actions → Runners) **và rào máy cũ** trước khi bật nó lên lần nào nữa (rút mạng, đăng nhập, Disable mọi tác vụ `shoponline-*`).
   5. Bảng kiểm tra cuối thêm: kết nối Drive (đã làm hay chưa), `sap-password set`, kiểm tra SAP.
5. Test chế độ máy mới: `.env` có sẵn dòng thì không ghi đè; `SHOPONLINE_WEB_HOST` được thay; database có dữ liệu thì từ chối; `ops.drive_connection` của máy mới không bị ghi đè; tài khoản từ gói đăng nhập được.

## Verification

- `uv run pytest tests/backup/test_new_machine_restore.py -q`
- Trên máy dev: `server-export.ps1 -Prepare` tạo bản `full`; database trống `shoponline_migrate_test` + thư mục dữ liệu tạm, `migrate`, `backup restore <gói> --new-machine` khớp số dòng và đăng nhập được bằng tài khoản trong gói.
- `server-export.ps1` và `setup-production-machine.ps1` parse không lỗi (`[ScriptBlock]::Create`).
- Diễn tập đầy đủ trên máy thật ở phase 7.

## Risks

- Máy cũ hỏng hẳn: máy mới dùng bản `full` tuần gần nhất trên Drive; dữ liệu sau thời điểm đó mất (đã biết, chấp nhận theo non-goal PITR). Kiểm runner chặn cho tới khi người quản trị gỡ runner cũ và rào máy cũ.
- `gh` chưa đăng nhập trên máy mới: script dừng ở bước kiểm runner và hướng dẫn `gh auth login`, không bỏ qua kiểm tra.

## Rollback

`server-export.ps1 -Rollback` trên máy cũ; trên máy mới Disable tác vụ và gỡ runner như hướng dẫn hiện tại.
