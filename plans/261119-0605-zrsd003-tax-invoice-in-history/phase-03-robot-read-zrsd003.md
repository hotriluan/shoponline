---
phase: 3
title: "Job robot đọc ZRSD003"
status: completed
priority: P2
effort: "5h"
dependencies: [1]
---

# Phase 3: Job robot đọc ZRSD003

## Goal
Robot chạy ZRSD003 theo bản ghi 19/11/2026, xuất Excel và nhập bằng `ingest_zrsd003`; xếp được từ trang Robot.

## Context (bản ghi `docs/sap-recordings/zrsd003/Script1.vbs`)
- `/nzrsd003` → `ctxtP_VKORG` = `1000`, Enter → `ctxtP_VKBUR-LOW` = `1401`, Enter → `ctxtP_FKDAT-LOW`, `ctxtP_FKDAT-HIGH` (ngày dạng `dd.mm.yyyy`) → `tbar[1]/btn[8]`.
- Radio "Exist" và "SD" mặc định, không chạm.
- Lưới `wnd[0]/usr/cntlGRID1/shellcont/shell/shellcont[1]/shell`, cột chuột phải `TAXSR`, menu `&XXL` → Select Spreadsheet → Save As → hai hộp SAP GUI Security: giống zrsd004, `export_result` đã xử lý.

## Files to Create / Modify
- Modify: `config/sap_screens.yaml` — screen `zrsd003` (`sales_org`, `sales_office`, `billing_date_from`, `billing_date_to`, `execute`, `result_grid`, `result_column: TAXSR`), ghi nguồn bản ghi.
- Modify: `src/shoponline/saprobot/guard.py` — thêm `ZRSD003` vào `ALLOWED_TRANSACTIONS` và `OPENABLE_TRANSACTIONS`.
- Modify: `src/shoponline/sapjobs/queue.py` — `READ_ZRSD003`, thêm vào `READ_KINDS`.
- Modify: `src/shoponline/sapjobs/report_requests.py` — `zrsd003_key(date_from, date_to)`, `request_zrsd003(session, target, date_from, date_to, actor)`; payload `{"date_from", "date_to"}`.
- Create: `src/shoponline/saprobot/transactions/read_zrsd003.py`.
- Modify: `src/shoponline/saprobot/transactions/__init__.py` — đăng ký `writes=False`.
- Modify: `src/shoponline/saprobot/transactions/report_screen.py` — chỉ khi chưa có: helper gửi Enter (VKey 0) rồi `ctx.step()`.
- Modify: `src/shoponline/saprobot/worker.py` — `_after_zrsd003` (lưu file, `ingest_zrsd003`, gắn `import_batch_id`, `discard_unused` file gốc sau commit); `NoReportData` của zrsd003 là DONE không dữ liệu như zrsd004.
- Modify: `src/shoponline/web/routes/robot.py`, `src/shoponline/web/templates/robot.html` — form "Đọc zrsd003" với Billing Date từ–đến (đến không quá hôm nay, từ ≤ đến).
- Modify: `tests/saprobot/fake_sap.py`, `tests/saprobot/test_report_reads.py`, `tests/saprobot/test_worker.py`, `tests/saprobot/test_guard.py`, `tests/web/test_robot_web.py`, `tests/sapjobs/test_queue.py`.

## Tasks & Steps
1. Thêm screen config và guard allowlist; test guard nhận ZRSD003.
2. `read_zrsd003.run`: `open_report("ZRSD003")`, điền sales org + Enter, sales office + Enter, `fill_date` hai ô, `execute`, `export_result`. Kiểm `fill`/`set_text` hiện có và fake SAP có hỗ trợ Enter; nếu chưa, thêm một helper nhỏ trong `report_screen.py`.
3. Queue + request: khóa `read_zrsd003:{from}:{to}`; job trùng đang mở báo `DuplicateJob` như hiện có.
4. Worker `_after_zrsd003`; xóa file gốc sau khi nhập (zrsd003 không gắn đợt kế toán nên `kept_files` không giữ).
5. Trang Robot: form và hiển thị kết quả job (`kept`, `skipped`).
6. Test fake SAP: điền đúng 4 ô theo thứ tự, Enter sau 2 ô đầu, xuất `zrsd003-job-N.xlsx`; worker nhập file giả và xóa file gốc; trang Robot xếp job, viewer bị từ chối, ngày ngược bị từ chối.

## Verification
- `uv run pytest tests/saprobot tests/sapjobs tests/web/test_robot_web.py -q`
