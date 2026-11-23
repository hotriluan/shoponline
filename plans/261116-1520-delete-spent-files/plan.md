---
title: "Dọn file toàn diện và xoay vòng sao lưu"
description: "Mọi file trong SHOPONLINE_DATA_DIR bị xóa khi hết dùng (ngay tại chỗ và bằng lượt quét đêm theo một bộ quy tắc giữ); sao lưu giữ một bản mỗi ngày trong 14 ngày."
status: in-progress
priority: P2
effort: 2d
branch: main
tags: [maintenance, robot, web, backup]
blockedBy: []
blocks: []
created: 2026-11-16
---

# Dọn file toàn diện và xoay vòng sao lưu

## Overview

> **Cập nhật 2026-11-23** (sửa chữ lệch mã, không đổi hợp đồng gốc): quyết định 4 (sao lưu một bản mỗi ngày, giữ 14 ngày) đã được plan [261123-0312](../261123-0312-backup-restore-server-migration/plan.md) thay: mã giữ 15 bản `db`, 15 bản `app`, bản `full` theo tuổi (tối đa 30 ngày), số bản đặt trên trang **Sao lưu**, và `SHOPONLINE_BACKUP_KEEP_DAYS` không còn tác dụng (`docs/deployment-guide.md`). Quy tắc giữ file kế toán cũng đã đổi: giữ mọi file `accounting_file`, kể cả file không thuộc đợt nào (plan [261123-0732](../261123-0732-data-integrity-fixes-accepted-findings/plan.md)).

Rà ngày 2026-11-16 trên `C:\shoponline-data` và `C:\shoponline-backup`:

- `robot-work/job-N/*.xlsx` là bản sao: robot chép nội dung sang `uploads/` khi nhập ([worker.py:99-104](../../src/shoponline/saprobot/worker.py#L99-L104)).
- `uploads/<sha256>.xlsx`: file sàn, ánh xạ SKU và zrsd001 chỉ được đọc một lần lúc nhập; zrsd004 còn được đọc lại tới khi đợt kế toán chốt hoặc hủy. Upload bị từ chối để lại file mồ côi.
- `exports/`: file đơn hàng không bao giờ được tải lại; file Shop Online hết dùng khi mọi đơn trong file đã được xác nhận; file kế toán đã chốt phải giữ.
- `robot-evidence/` chỉ được dọn khi robot khởi động. `logs/retention.log` không bao giờ bị cắt.
- File dọn theo tuổi 90 ngày qua `shoponline retention`, nhưng tác vụ đang ở chế độ chỉ liệt kê, nên không file nào từng bị xóa.
- `C:\shoponline-backup`: 17 bản trong 4 ngày, do mỗi lần deploy sao lưu một lần; bản cũ chỉ bị xóa sau 30 ngày.
- Đã xóa (2026-11-16, chủ dự án đồng ý): `C:\shoponline-data\backups\shoponline_dev-before-0004-20261112-083110.dump`, bản dump tạo tay không mã hóa, và thư mục `backups` rỗng.

## Hợp đồng

- **Kết quả:** không còn file nào trong `uploads/`, `exports/`, `robot-work/`, `robot-evidence/` mà không có quy tắc giữ. File hết dùng bị xóa ngay tại thời điểm hết dùng; lượt quét hằng đêm dọn mọi file còn sót theo cùng bộ quy tắc. Thư mục sao lưu còn một bản mỗi ngày trong 14 ngày, cộng các bản của hôm nay.
- **Ràng buộc:**
  - Một bộ quy tắc giữ duy nhất (bảng ở phase 03), dùng cho cả xóa ngay lẫn quét đêm.
  - Không xóa file kế toán mà một đợt trỏ tới, zrsd004 của đợt `OPEN`, zrsd004 upload tay chờ gắn, file Shop Online còn đơn chưa xác nhận, thư mục và ảnh của việc robot lỗi trong `evidence_keep_days`.
  - Quét đêm chỉ xóa file cũ hơn 1 giờ. Xóa lỗi chỉ ghi log.
  - Quét file xóa thật, không chờ `--apply`. `--apply` chỉ còn quyết việc xóa tên và địa chỉ khách.
  - Vẫn sao lưu trước mỗi lần deploy. Chỉ dọn sao lưu sau khi bản mới chép thành công.
  - Không đổi schema.
- **Ngoài phạm vi:** bật `--apply` cho dữ liệu khách (chủ dự án để sau); dọn dòng trong database (`event_log`, `sap_job`); log của GitHub runner (`C:\actions-runner\_diag`, do runner tự quản); dựng file đơn hàng trong bộ nhớ.
- **Tiêu chí nghiệm thu:** test cho từng dòng quy tắc giữ và từng điểm xóa ngay, gồm trường hợp lỗi và file dùng chung; thử xoay vòng sao lưu trên thư mục giả; `uv run pytest` xanh; `uv run ruff check` sạch; tài liệu khớp hành vi; sáng sau deploy `retention.log` và `C:\shoponline-backup` đúng như mô tả.

## Quyết định của chủ dự án (2026-11-16)

1. Không giữ file gốc của sàn và zrsd001 làm bằng chứng.
2. Quét file hằng đêm xóa thật ngay.
3. File Shop Online bị xóa khi mọi đơn trong file đã được xác nhận.
4. Sao lưu: mỗi ngày giữ bản mới nhất, 14 ngày; giữ bước sao lưu lúc deploy.
5. Bật `--apply` cho dữ liệu khách: để sau.

## Trade-offs

- Chỉ bật `--apply`: không sửa code, nhưng file nằm 90 ngày và kéo theo xóa dữ liệu khách. Không chọn.
- Chỉ quét đêm, không xóa ngay: một chỗ sửa, nhưng file nằm thêm tới một ngày. Không chọn vì yêu cầu là xóa ngay; quét đêm giữ vai trò lưới an toàn.
- Dựng file đơn hàng trong bộ nhớ: phải đổi `save_generated` và cột `stored_path` dùng chung. Xóa sau khi gửi rẻ hơn. Không chọn.
- Sao lưu đúng một bản mỗi ngày và bỏ bản lúc deploy: gọn nhất, nhưng mất điểm lùi ngay trước migrate. Không chọn.
- Hệ quả đã chấp nhận: đợt đã chốt bị gỡ thì zrsd004 upload tay của đợt đó phải upload lại; lệnh `shoponline retention` không `--apply` nay vẫn xóa file.

## Phases

| # | Phase | Status |
|---|---|---|
| 01 | [Xóa robot-work và file đơn hàng ngay](phase-01-delete-spent-files.md) | completed |
| 02 | [Xóa file trong uploads khi hết dùng](phase-02-delete-spent-uploads.md) | completed |
| 03 | [Quét file hằng đêm, file Shop Online, log retention](phase-03-nightly-sweep-and-history-files.md) | completed |
| 04 | [Mỗi ngày giữ một bản sao lưu, giữ 14 ngày](phase-04-backup-rotation.md) | completed |
| 05 | [Cập nhật tài liệu](phase-05-docs.md) | completed |

Phase 02 và 03 cùng sửa `retention.py`: làm tuần tự. Phase 04 độc lập, làm song song được.

## Kết quả thực hiện (2026-11-16)

- Code, test và tài liệu xong: `uv run pytest` 379 passed, `uv run ruff check` sạch.
- Xoay vòng sao lưu: thử trên thư mục giả 21 ngày × 3 bản, còn đúng một bản cho mỗi ngày trong 14 ngày trước và mọi bản hôm nay; file khác tên không bị đụng. Chạy `-WhatIf` trên `C:\shoponline-backup`: sẽ xóa 3 bản ngày 12/11 và 7 bản ngày 13/11, giữ bản mới nhất mỗi ngày và 5 bản hôm nay. Chưa xóa thật; lần sao lưu đầu tiên sau deploy sẽ dọn.
- Còn chờ deploy: đọc `retention.log` và `C:\shoponline-backup` sáng hôm sau. Lượt quét đầu tiên sẽ xóa toàn bộ file cũ không còn quy tắc giữ.
- `.env.example` đổi `SHOPONLINE_BACKUP_KEEP_DAYS` thành 14. Nếu `.env` của máy chạy thật đang đặt 30, giá trị đó vẫn thắng mặc định mới và phải sửa tay.

## Câu hỏi còn mở

- `SHOPONLINE_BACKUP_DIRS` có nơi nào ngoài máy không? `C:\shoponline-backup` nằm cùng ổ với database.

## Red Team Review

Ngày 2026-11-23. Ba lens (Failure Mode Analyst, Assumption Destroyer, Scope & Complexity Critic) cộng lens trùng/sót dữ liệu, chạy bằng cách soi mã và test thật; một người soi, tự phân xử, plan đã làm nên đối chiếu mã với plan. Số đếm là dev DB, 2026-11-23 (production không mở được). Chi tiết và SQL: [báo cáo](../reports/data-integrity-audit-261123-1320-deletion-machine.md).

| # | Phát hiện | Mức | Bằng chứng trong mã | Disposition | Hướng xử lý |
|---|-----------|-----|---------------------|-------------|-------------|
| 1 | Đường dẫn tuyệt đối trong DB; quét đêm so với gốc `SHOPONLINE_DATA_DIR` hiện tại. DB khôi phục lên máy có thư mục dữ liệu khác thì mọi file quá 1 giờ bị xóa, gồm file kế toán đã chốt (kết luận từ mã; test tái hiện viết sẵn trong scratchpad nhưng chưa chạy được vì test DB dùng chung đang bị khóa) | Medium | `maintenance/retention.py:169`, `:226-235`; `web/uploads.py:48,59,73`; `backup/` không sửa `stored_path`. Dev: 125/125 dòng dưới `C:\shoponline-data` | Accept (chủ dự án duyệt 2026-11-23) | Quét từ chối chạy khi có dòng `stored_path` mà không dòng nào dưới gốc hiện tại, hoặc lưu đường dẫn tương đối |
| 2 | File kế toán cũ không thuộc đợt nào không có quy tắc giữ, lượt quét đầu tiên xóa (7 dòng dev, sổ nền 12 DO) | Medium | `retention.py:155-157`. Dev: 7 dòng `accounting_file` không có `accounting_run` | Accept (chủ dự án duyệt 2026-11-23) | Chủ dự án quyết có giữ; nếu có, thêm quy tắc giữ hoặc chép ra ngoài. Chạy SQL S2 trên production |
| 3 | File kế toán đã chốt chỉ ở `exports/`; sao lưu `db` hằng ngày không chứa thư mục dữ liệu, chỉ bản `full` hằng tuần | Medium | `backup/schedule.py:15`; `backup/archive.py:3-10`; `docs/operations-runbook.md:116` | Accept (chủ dự án duyệt 2026-11-23) | Đưa `exports/` vào bản hằng ngày, hoặc chấp nhận tới 6 ngày và ghi vào docs |
| 4 | Quét đêm không đọc `maintenance.json`, không bị tạm dừng khi khôi phục/deploy; khôi phục bản `db` rồi quét xóa file mới hơn DB (bản `full` an toàn còn giữ) | Medium | `cli.py:392-408`; `backup/restore.py:392-393,557`; `scripts/windows/update-production.ps1:63-70` | Accept (chủ dự án duyệt 2026-11-23) | `retention` thoát sớm khi `maintenance.active`; ghi docs nơi lấy lại file |
| 5 | Gỡ xác nhận file lịch sử sau khi tên khách đã bị xóa: đơn bị chặn mãi "Thiếu tên khách" | Medium | `web/routes/sales_history.py:414-432`; `retention.py:103-105`; `exports/sales_history_workbook.py:215-217` | Accept (chủ dự án duyệt 2026-11-23) | Báo số đơn đã mất tên khi gỡ xác nhận, hoặc chặn gỡ quá hạn dữ liệu |
| 6 | `discard_unused` không có thời gian ân hạn; hai upload cùng nội dung đồng thời có thể làm một lượt lỗi "không có file" | Low | `retention.py:186-205` so với `:223`; `web/uploads.py:49-53` | Reject (chấp nhận rủi ro; không mất dữ liệu, người dùng tải lại) | Không đổi |
| 7 | `path.stat()` sau `is_file()`: file biến mất giữa hai lệnh làm cả lượt quét dừng | Low | `retention.py:229-231`; `web/routes/batches.py:164` | Accept (chủ dự án duyệt 2026-11-23) | Bắt `FileNotFoundError` quanh `stat()` |
| 8 | Plan lệch mã: sao lưu "một bản mỗi ngày, 14 ngày" đã bị plan 261123-0312 thay bằng 15 bản `db`/`app`, `full` ≤ 30 ngày | Low | `plan.md:30,46,72` so với `backup/retention.py:19-24`; `docs/deployment-guide.md:64` | Accept (chủ dự án duyệt 2026-11-23) | Ghi chú ở plan rằng quyết định 4 đã được thay |
| 9 | Retention xóa tên khách của đơn READY/chưa có DO/chưa gửi kế toán | Low | `retention.py:102-108`; test `tests/maintenance/test_retention.py:160`; dev: 10 READY được giữ | Reject (đã kiểm: điều kiện xóa cần hủy, không có đơn, hoặc đã gửi kế toán và đã vào lịch sử) | Không đổi |
| 10 | Quét đêm xóa file Shop Online chưa xác nhận, hoặc thư mục `robot-work` của việc lỗi | Low | `retention.py:158-166`, `:267-269`; test `:244`, `:280`; `tests/web/test_sales_history_routes.py:59-60` | Reject (đã kiểm: quy tắc giữ và test) | Không đổi |

## Validation Log

Ngày 2026-11-23. Chỉ đối chiếu mã, test và dev DB (production không mở được); không hỏi chủ dự án trong lượt này, câu hỏi nằm ở cuối. Không xóa hay sửa file nào trên đĩa.

### Tiêu chí hoàn thành

| # | Tiêu chí | Kết quả | Bằng chứng |
|---|----------|---------|------------|
| 1 | Một bộ quy tắc giữ duy nhất cho cả xóa ngay lẫn quét đêm | VERIFIED (mã) | `discard_unused` và `sweep_files` cùng gọi `kept_files` (`maintenance/retention.py:200,224`) |
| 2 | Test cho từng dòng quy tắc giữ và từng điểm xóa ngay, gồm lỗi và file dùng chung | VERIFIED một phần | `tests/maintenance/test_retention.py` (7 test, 7 passed ngày 2026-11-23): đợt mở, zrsd004 chờ gắn, file đợt và file lịch sử, thư mục việc chưa xong, `discard_unused`; web: `tests/web/test_web_flow.py:98,125,150,211`, `tests/web/test_accounting_routes.py:351,361`, `tests/web/test_sales_history_routes.py:59-60,178,238`; robot: `tests/saprobot/test_worker.py:389`. Chưa có test cho hai lô nhập dùng chung một file (dev có 9 giá trị `sha256` như vậy) và cho gốc thư mục dữ liệu khác |
| 3 | Không xóa file kế toán mà một đợt trỏ tới, zrsd004 đợt OPEN, zrsd004 chờ gắn, file Shop Online còn đơn chưa xác nhận, thư mục việc lỗi | VERIFIED (mã và test), trừ D1 và D2 | `retention.py:131-170`, `:267-269`. Ngoại lệ: gốc đường dẫn khác (phát hiện 1) và file kế toán không thuộc đợt (phát hiện 2) |
| 4 | Quét đêm chỉ xóa file cũ hơn 1 giờ | VERIFIED cho quét; FAILED một phần cho xóa ngay | `retention.py:223,231`; `discard_unused` không có ân hạn (`:186-205`, phát hiện 6) |
| 5 | Vẫn sao lưu trước mỗi lần deploy; chỉ dọn sao lưu sau khi bản mới chép thành công | VERIFIED (mã) | `scripts/windows/update-production.ps1` (bước 3, sao lưu trước migrate); `docs/security-and-data-retention.md:53` ("chỉ nơi nào đã nhận bản mới mới được dọn") |
| 6 | Xoay vòng sao lưu: một bản mỗi ngày, 14 ngày | FAILED (đã bị thay) | Mã giữ 15 bản `db`/`app`, `full` theo tuổi (`backup/retention.py:19-24`; test `tests/backup/test_naming_retention_schedule.py:42-76`); plan 261123-0312 thay quyết định 4 |
| 7 | `uv run ruff check` sạch | VERIFIED một phần | `ruff check src/shoponline/maintenance src/shoponline/web/uploads.py` sạch; không chạy toàn bộ `pytest` ở lượt này vì test DB dùng chung với các phase khác |
| 8 | Tài liệu khớp hành vi | VERIFIED (mã) | `docs/security-and-data-retention.md:22-39` khớp `retention.py:1-25`; lệch ở sao lưu đã ghi ở tiêu chí 6 |
| 9 | Sáng sau deploy, `retention.log` và `C:\shoponline-backup` đúng như mô tả | UNVERIFIED | `retention.log` trên máy dev chỉ có hai lượt chế độ liệt kê (2026-11-13, 2026-11-16); lượt quét thật đầu tiên trên máy chạy thật chưa đọc được |

### Giả định đang dùng

| # | Giả định | Kết quả | Bằng chứng |
|---|----------|---------|------------|
| 1 | File sàn, ánh xạ SKU, zrsd001 chỉ được đọc một lần lúc nhập | VERIFIED | `web/routes/imports.py:65`, `sap_reports.py:70,102,132`, `sku_mapping.py:235` xóa ngay sau commit; dev: dòng `import_batch` còn `sha256` nhưng file không còn đọc lại |
| 2 | zrsd004 còn được đọc lại tới khi đợt chốt hoặc hủy | VERIFIED | `retention.py:134-149` (giữ theo đợt OPEN); `web/routes/accounting.py:340` xóa khi đợt đóng |
| 3 | File đơn hàng không bao giờ được tải lại | VERIFIED | `web/routes/batches.py:157-165` sinh lại từ DB mỗi lần tải và xóa sau khi gửi; dev: 27 dòng `generated_file` kind `order_file` còn lại với đường dẫn không dùng nữa (không gây hại) |
| 4 | Đơn và dòng hàng không chứa dữ liệu cá nhân; tên và địa chỉ chỉ ở `customer_info` | VERIFIED | `db/models.py:165-178`; `EventLog` ghi chú không lưu tên |
| 5 | Dữ liệu dev khớp quy tắc xóa: 129 dòng `customer_info`, 0 quá 90 ngày | VERIFIED (dev) | Truy vấn S1 trong báo cáo: 117 DELIVERED đã gửi chưa vào lịch sử, 10 READY, 2 CANCELLED |
| 6 | `.env` máy chạy thật có thể còn `SHOPONLINE_BACKUP_KEEP_DAYS=30` | UNVERIFIED, không còn quan trọng | `docs/deployment-guide.md:64`: biến không còn tác dụng |
| 7 | Câu hỏi còn mở của plan ("`SHOPONLINE_BACKUP_DIRS` có nơi nào ngoài máy?") | VERIFIED một phần | Dev có 1 dòng `ops.drive_connection` và 6 dòng `ops.backup_run`; bản lên Drive do plan 261123-0312 lo, chưa xác nhận ở production |

### Câu hỏi cho chủ dự án

1. Phát hiện 2: file kế toán sinh trước khi có đợt (7 dòng trên dev, ngày 13/11) có cần giữ làm bằng chứng không? Nếu có, trên production có thể đã bị lượt quét đêm 2026-11-16 xóa; cần chạy SQL S2 và liệt kê thư mục `exports`.
2. Phát hiện 3: file kế toán đã chốt chỉ vào bản sao lưu `full` hằng tuần. Chấp nhận rủi ro tới 6 ngày, hay đưa `exports/` vào bản hằng ngày?
3. Phát hiện 1: có đồng ý quét đêm từ chối chạy khi đường dẫn trong DB không nằm dưới thư mục dữ liệu hiện tại (chặn mất hết file sau một lần khôi phục lên thư mục khác)?
4. Phát hiện 4: có đồng ý cho `retention` thoát sớm khi đang khôi phục hoặc deploy?
5. Khi nào bật `--apply` cho dữ liệu khách? Trước đó nên xử lý phát hiện 5 (gỡ xác nhận sau khi tên đã xóa).
