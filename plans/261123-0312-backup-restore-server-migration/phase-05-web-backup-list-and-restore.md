---
phase: 5
title: "Web: danh sách, nhật ký, phục hồi, tải lên"
status: completed
priority: P1
effort: "1.5d"
dependencies: [3, 4]
---

# Phase 5: Web: danh sách, nhật ký, phục hồi, tải lên

<!-- Updated: Red Team 2026-11-23 - hàng đợi duy nhất backup_request, upload stream không qua multipart, bắt buộc mã hóa, cache Drive không tạo dòng trùng, quyền admin cho GET -->

## Goal

Bảng "Danh sách bản sao lưu & nhật ký" trên `/backup` theo thiết kế đã chốt: mỗi `ops.backup_run` một dòng (cả lỗi), đối chiếu với máy chủ và Drive, các thao tác Tải về, Kiểm tra, Thử lại Drive, Xóa, Phục hồi… (diễn tập hoặc thật), Tải lên; banner kết quả phục hồi.

## Context

- Phân trang và tìm kiếm phía server: [pagination.py](../../src/shoponline/web/pagination.py), [pager.html](../../src/shoponline/web/templates/pager.html), [table_tools.html](../../src/shoponline/web/templates/table_tools.html).
- `UploadFile` của Starlette ghi cả body multipart xuống file tạm trước khi handler chạy ([uploads.py](../../src/shoponline/web/uploads.py) dòng 31–33), nên giới hạn kích thước kiểu đó không chặn được body lớn.
- Mọi thao tác chạy nền đi qua `ops.backup_request` (phase 1); phục hồi là `action=restore` (phase 3).
- Brainstorm: "Danh sách bản sao lưu và nhật ký", tiêu chí 19–23; quyết định 4. Red-team: mục 4, 8, 11, 14.

## Files to Create / Modify

- Modify: `src/shoponline/web/routes/backup.py` — danh sách, tải về, kiểm tra, thử lại Drive, xóa, phục hồi, tải lên, trạng thái dòng (JSON)
- Create: `src/shoponline/web/templates/backup_list.html` — partial bảng + hộp thoại Phục hồi, Xóa
- Create: `src/shoponline/backup/inventory.py` — đối chiếu `backup_run` với thư mục máy chủ và `list_backups()` của Drive
- Modify: `src/shoponline/web/app.py` — khi khởi động đọc `restore-status.json` mới, đẩy banner thành công/lùi lại/lỗi cho admin một lần
- Create: `tests/web/test_backup_list.py`, `tests/backup/test_inventory.py`

## Tasks & Steps

1. `inventory.py` + test:
   - Cột Máy chủ: Đang chạy · Thành công · Lỗi · Đã xóa theo số bản giữ · Không có (chỉ trên Drive, hoặc file biến mất ngoài hệ thống).
   - Danh sách Drive cache 5 phút trong tiến trình web; bị bỏ khi có `backup_run.finished_at` mới hơn thời điểm cache, hoặc sau mỗi POST của admin.
   - File trên Drive chưa có trong database → `INSERT … ON CONFLICT (drive_file_id) DO NOTHING` dòng nguồn `drive_found` (index duy nhất từ phase 1).
   - File Drive sai mẫu tên bị bỏ qua.
2. Bảng: cột theo brainstorm (Phạm vi/tên + "DB: N bảng • M bản ghi" + revision; Nguồn·Thời gian·Người thực hiện gộp một ô; Dung lượng; Máy chủ; Google Drive). Bộ lọc loại/nguồn/trạng thái; tổng số theo bộ lọc trong tiêu đề. Dòng đang chạy tự cập nhật qua `GET /backup/runs/<id>/status` mỗi 3 giây.
3. **Tải về** (`GET`, `require_admin`): stream file từ máy chủ; chỉ trên Drive thì tải về máy chủ trước (`restore.prepare` phần lấy file, so MD5). `event_log` `backup_download`.
4. **Kiểm tra** (menu "…"): `enqueue("verify", target_run_id)`; kết quả (`require_encrypted`, `7z t`, SHA-256) ghi vào `backup_run.verified_at`, `verify_result`.
5. **Thử lại** ở cột Drive: `enqueue("retry_drive", target_run_id)` — không tạo bản mới (tiêu chí 19). Thao tác dựa trên `drive_file_id` thì lấy lại file theo id trên Drive trước khi làm.
6. **Xóa**: hộp thoại chọn máy chủ / Drive / cả hai; từ chối bản thành công mới nhất mỗi loại và bản `safety` của lần phục hồi gần nhất; đánh dấu `deleted_by`, `deleted_at`, giữ dòng; `event_log` `backup_delete` (tiêu chí 23).
7. **Phục hồi…**: hộp thoại hai lựa chọn.
   - **Diễn tập** (mặc định): `enqueue("drill", target_run_id)`; hiện bảng so số dòng khi xong.
   - **Phục hồi hệ thống thật**:
     - Nêu rõ thay gì: `db` → dữ liệu nghiệp vụ; `full` → dữ liệu nghiệp vụ và file trong thư mục dữ liệu. Tài khoản người dùng web, lịch sao lưu và kết nối Drive **giữ nguyên**; mọi người phải đăng nhập lại.
     - Bản cũ không manifest: ghi "không kiểm được phiên bản và số dòng trước khi phục hồi; nên diễn tập trước".
     - Cảnh báo nếu người dùng khác có `last_seen_at` trong 5 phút.
     - Nhập lại mật khẩu của chính admin; gõ đúng tên file.
     - Từ chối nếu đã có yêu cầu `restore` đang `pending` hoặc `running`.
     - `enqueue("restore", target_run_id)` rồi `schtasks /Run /TN shoponline-restore`, kiểm mã thoát; lỗi thì đánh yêu cầu `failed` ngay và báo lý do.
     - Trang chuyển sang "Đang phục hồi, web sẽ tạm ngừng 1–3 phút", tự tải lại khi `/login` trả lời; `/login` trả lời mà yêu cầu vẫn `pending` sau 2 phút thì báo "tác vụ phục hồi không chạy".
   - Bản `app` không có nút phục hồi; bản có revision mới hơn mã → nút bị khóa kèm lý do (tiêu chí 21, kiểm lại phía server).
8. **Tải lên** (`require_admin`):
   - Đọc `request.stream()` trực tiếp (không dùng `UploadFile`/multipart), từ chối ngay khi `Content-Length` > 1 GB hoặc thiếu; kiểm dung lượng trống của ổ thư mục dữ liệu ≥ 2 × kích thước.
   - Ghi vào `staging_dir()`, ngừng và xóa khi vượt 1 GB.
   - Kiểm `require_encrypted`, mở được bằng mật khẩu sao lưu, manifest, SHA-256 từng phần, danh sách tên được phép.
   - Hợp lệ: chuyển vào thư mục sao lưu đầu tiên với tên chuẩn, dòng nguồn `upload`. Không hợp lệ: xóa và báo lý do (tiêu chí 22).
9. Banner kết quả phục hồi sau khi web khởi động lại.
10. Viewer: xem bảng; mọi route khác (GET lẫn POST) dùng `require_admin`; JSON trạng thái dòng không chứa nội dung lỗi thô.

## Verification

- `uv run pytest tests/web/test_backup_list.py tests/backup/test_inventory.py -q`: tiêu chí 19, 20, 22, 23; viewer bị chặn ở Tải về và mọi thao tác; tải lên file không mã hóa, sai mật khẩu, sửa một byte đều bị từ chối và không để lại file; body vượt giới hạn bị từ chối trước khi ghi hết; hai lần mở trang cùng lúc không tạo dòng `drive_found` trùng.
- Thủ công trên dev: diễn tập từ web khớp số dòng; phục hồi thật từ web với `migrate` bị ép lỗi → web trở lại với banner "Đã lùi lại" (tiêu chí 7 phần web).

## Risks

- Liệt kê Drive chậm: cache 5 phút; lỗi Drive không chặn render (cột Drive "Không kiểm tra được").
- Tải về/tải lên file lớn giữ worker uvicorn: stream theo khúc.

## Rollback

Revert mã; không có migration mới.
