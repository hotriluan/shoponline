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
