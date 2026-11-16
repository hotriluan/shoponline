---
phase: 5
title: "Tài liệu và chạy thử production"
status: in-progress
priority: P2
effort: "2h"
dependencies: [4]
---

# Phase 5: Tài liệu và chạy thử production

## Goal
Hướng dẫn admin cách xuất, dán và xác nhận, rồi xác nhận trên dữ liệu production rằng file và sổ đã xuất khớp tiêu chí của plan.

## Bối cảnh
- Quy trình hằng ngày: [daily-operations.md](../../docs/daily-operations.md). Kiến trúc: [system-architecture.md](../../docs/system-architecture.md). Dữ liệu cá nhân và retention: [security-and-data-retention.md](../../docs/security-and-data-retention.md).
- Deploy qua GitHub runner trên máy `AlkanaDuongPC` (192.168.18.123); script deploy sao lưu database rồi `migrate` ([deployment-guide.md](../../docs/deployment-guide.md)).
- Có thể đọc dữ liệu production qua SSH `prod-win10` (chỉ đọc).

## Files to Create / Modify
- Modify: `docs/daily-operations.md`: mục "Xuất dòng cho file Shop Online".
- Modify: `docs/system-architecture.md`: ba bảng mới và các route mới.
- Modify: `docs/security-and-data-retention.md`: file `sales_history` chứa tên khách và chịu retention của thư mục exports; tên khách của đơn chưa xác nhận vào file lịch sử được giữ quá 90 ngày. <!-- Updated: Validation Session 1 - retention change -->

## Tasks & Steps
1. Viết tài liệu: xử lý đơn bị chặn, tải file, copy từ dòng 2 và dán vào dòng trống đầu tiên của sheet1, bấm "Xác nhận đã dán"; gỡ xác nhận khi dán nhầm; chỉ đơn "Đã có DO" được xuất.
2. Sau deploy: kiểm migration `0007_sales_history` đã chạy và bản sao lưu trước deploy có trong thư mục sao lưu.
3. Chạy thử chỉ đọc trên production: `province_of` cho mọi `customer_info.address`; liệt kê địa chỉ ra `None`. Có địa chỉ đúng mà không khớp thì sửa `PROVINCES`/tiền tố, thêm test, deploy lại.
4. Admin mở "Tên báo cáo", duyệt gợi ý của khoảng 75 mã, so với cách ghi trong file lịch sử (ví dụ `Propan - ULTRAN VERNIS - V-09 - Sơn Dầu Bóng Màu` / `0.8 lít` / `Màu sắc:2004 Cánh gián`), lưu.
5. Admin bổ sung tên khách còn thiếu cho các đơn "Đã có DO".
6. Xuất lần đầu: số đơn trong file bằng số đơn `DELIVERED` lúc kiểm (ghi con số), header trùng dòng 1 của sheet1; dán thử vào một bản sao file lịch sử và kiểm hai cột công thức; bấm xác nhận; mở lại trang và thấy không còn đơn chờ (trừ đơn mới có DO).
7. Kiểm retention chế độ chỉ liệt kê (`uv run --no-dev shoponline retention`) không liệt kê tên của đơn chưa xác nhận.

## Verification
- `uv run pytest` và `uv run ruff check` trên máy dev.
- Biên bản ngắn trong `plans/reports/` ghi: số đơn, số dòng, số địa chỉ không tách được, kết quả dán thử, kết quả xác nhận.

## Risk & Rollback
- Nếu file không dùng được: gỡ mục menu bằng một deploy; các bảng mới để nguyên không ảnh hưởng gì. Lùi migration chỉ khi cần, sau khi sao lưu, và hoàn lại thay đổi retention cùng lúc.
