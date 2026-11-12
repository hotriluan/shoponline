---
title: "Khung robot SAP chỉ đọc: hàng đợi, phiên, popup, worker, màn hình"
date: 2026-11-12
summary: Phase 5 xong phần không cần SAP; thao tác đọc zrsd001/zrsd004 chờ bản ghi recorder
---

# Khung robot SAP chỉ đọc

## Đã xảy ra
- Phase 4 không còn việc viết mã; phần còn lại (triển khai máy thật, 10 ngày song song) là việc của chủ dự án.
- Phase 5, phần làm được không cần SAP: bảng `sap_job` và `robot_control` (migration `0004_sap_job`), hàng đợi `SKIP LOCKED` với khóa chống trùng là unique index một phần trên việc chưa xong, khung `saprobot` (phiên, thanh trạng thái, popup, ảnh lỗi, worker), lệnh `robot`, `robot-pause`, `robot-resume`, trang **Robot SAP**, đăng ký Task Scheduler bằng `-RobotUser`.
- Nhập file báo cáo tách ra `reconcile/report_ingest.py`; trang tải lên và robot dùng chung, nên kết quả robot đọc giống hệt file tải lên.
- 92 test qua, ruff sạch.

## Quyết định
- Robot chỉ vào luồng khi đặt `SHOPONLINE_SAP_SYSTEM` và `SHOPONLINE_SAP_CLIENT`; để trống thì mọi thứ như phase 4.
- Thao tác đọc báo cáo phải trả về một file xlsx, dù lấy bằng cách đọc lưới hay xuất Excel, để đi qua đúng bộ đọc của phase 4.
- Sai hệ thống, client hoặc user: robot từ chối việc và tự dừng; khi đã có phiên của hệ thống khác thì không đăng nhập thêm.
- Một robot duy nhất nhờ khóa advisory PostgreSQL, ngoài cấu hình `IgnoreNew` của Task Scheduler.
- Việc đọc bị ngắt thì về "Chờ"; việc ghi (từ phase 6) bị ngắt thì thành "Chưa rõ", không bao giờ tự chạy lại.

## Chưa làm, chờ người khác
- `read_zrsd001`, `read_zrsd004` và ID màn hình: chờ bản ghi recorder trên QA với user robot.
- Chạy thử trên QA, 5 ngày so với file tải lên, đo thời gian đọc.
- Database dev đã sao lưu (`pg_dump`, ở thư mục `backups` trong thư mục dữ liệu) rồi nâng lên `0004_sap_job`; dữ liệu cũ còn nguyên.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
