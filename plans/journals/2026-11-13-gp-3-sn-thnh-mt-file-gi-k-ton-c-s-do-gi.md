---
title: "Gộp 3 sàn thành một file gửi kế toán, có sổ DO đã gửi"
date: 2026-11-13
summary: "Phase 1-5 và tài liệu xong, 322 test qua; chạy thử Production chờ chủ dự án"
---

# Gộp 3 sàn thành một file gửi kế toán, có sổ DO đã gửi

## What happened
Làm xong sổ DO đã gửi (migration 0006), bộ dựng file gộp nhiều nguồn với dòng tổng tính lại theo đơn vị, kết quả "SAP chưa có DO" trung tính cho robot, dịch vụ đợt xuất (cặp sàn × ngày, đối chiếu, bản nháp, chốt, hủy, gỡ chốt) và trang Gửi kế toán. Cập nhật docs.

## Decisions
- Thêm cột coverage vào accounting_run_source để trạng thái cặp không phải mở file xlsx.
- Chốt gắn với dấu vân tay của bản đã xem; hai kết nối thật được kiểm bằng test.
- Mốc ngày mặc định là ngày chạy migration, nên test phải đặt mốc về quá khứ.

## Next steps
- Chạy thử Production (phase 6): sao lưu DB, migrate, duyệt sổ nền và mốc, so bản nháp với file kế toán làm tay, xác nhận thứ tự đơn vị ở dòng tổng và ý nghĩa P_WADAT. Chưa làm.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
