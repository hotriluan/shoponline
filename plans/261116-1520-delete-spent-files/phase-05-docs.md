---
phase: 5
title: "Cập nhật tài liệu thời hạn lưu"
status: completed
---

# Phase 05: Cập nhật tài liệu thời hạn lưu

## Files

- Sửa: [docs/security-and-data-retention.md](../../docs/security-and-data-retention.md) (bảng nơi lưu và mục "Thời hạn lưu")
- Đọc lại, chỉ sửa nếu nói sai: [docs/robot-runbook.md](../../docs/robot-runbook.md) dòng về `robot-work`, [docs/system-architecture.md](../../docs/system-architecture.md) bảng thư mục

## Steps

1. Ghi rằng `robot-work/job-N` bị xóa ngay khi việc nhập xong; thư mục chỉ còn lại với việc lỗi, cần xem lại, tối đa `evidence_keep_days`; file xóa không được thì lượt quét đêm dọn.
2. Ghi rằng `uploads/` chỉ giữ zrsd004 của đợt đang mở và zrsd004 upload tay chờ gắn; file khác bị xóa ngay khi nhập xong, khi đợt chốt hoặc hủy, hoặc khi file bị từ chối.
3. Ghi rằng file `ĐƠN HÀNG ONLINE` không được giữ trên máy chủ sau khi tải; muốn có lại thì bấm tải lần nữa.
4. Ghi quy tắc giữ file (bảng ở phase 03), việc `shoponline retention` luôn xóa file còn `--apply` chỉ dùng cho dữ liệu khách, và file Shop Online bị xóa khi xác nhận hết.
5. Ghi cách giữ sao lưu: mỗi ngày một bản, 14 ngày, hôm nay giữ hết; sửa mọi chỗ còn ghi 30 ngày (`deployment-guide.md`, `operations-runbook.md`, `security-and-data-retention.md`).
6. Kiểm tra lại link và tên hàm khớp code.

## Validation

Đọc lại đoạn đã sửa so với code và script của phase 01 đến 04.
