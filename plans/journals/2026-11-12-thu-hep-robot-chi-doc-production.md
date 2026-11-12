---
title: "Thu hẹp robot SAP: bỏ ghi SO và DO, chỉ đọc báo cáo trên Production"
date: 2026-11-12
summary: Bỏ phase 6–8 và cổng G2, G3; phase 5 và 9 chuyển sang Production chỉ đọc; thêm lớp chặn T-code làm điều kiện trước lần chạy đầu
---

# Thu hẹp robot SAP về chỉ đọc trên Production

## Đã xảy ra
- Chủ dự án lo QA không có dữ liệu giống Production để chạy thử SO và DO. Khi rà kế hoạch thì thấy thêm hai chỗ hở: DO không có bậc shadow, và kế hoạch không có bước kiểm tra QA có đủ dữ liệu.
- Chủ dự án đề xuất bỏ robot ghi SAP. Sales admin vẫn đang tạo SO và DO nên không cần ai phê duyệt. IT đã cấp được user robot vào `zrsd001` và `zrsd004`, license có sẵn. Chủ dự án chọn giữ robot GUI, không dùng job nền SAP.
- Kế hoạch đã sửa: phase 6–8 chuyển `cancelled` và giữ nội dung để tham khảo; bỏ G2 và G3; effort giảm từ 36 xuống 24 ngày; phase 5 và 9 làm trên Production, chỉ đọc, không dùng QA.

## Quyết định
- Robot chỉ vào được `ZRSD001` và `ZRSD004`. Điều này được chặn bằng mã (`saprobot/guard.py`), không phụ thuộc role phía SAP. Danh sách T-code nằm cứng trong mã. Robot kiểm tra `Info.Transaction` trước và sau mỗi thao tác, vì báo cáo ALV có thể tự mở VA02 khi bấm đúp. Gặp T-code lạ thì việc `FAILED` và robot tự tạm dừng.
- Lớp chặn là điều kiện trước lần chạy đầu trên Production.
- Cột chế độ của `platform_setting` giữ nguyên, không viết migration để xóa.

## Rủi ro còn lại
- Lớp chặn không ngăn người đăng nhập SAP bằng tay với user robot. Khuyến nghị IT giới hạn role, nhưng không phải điều kiện.
- Rủi ro chuyển từ dữ liệu SAP sang file gửi kế toán; được chặn bằng 5 ngày chạy song song và đường tải tay.

## Tiếp theo
- `/ak-cook`: `guard.py` và test, nối vào `worker.py`; sửa `docs/robot-machine-setup.md` và `docs/robot-runbook.md`, vì hai file này còn ví dụ QA và nhắc tới phase 6.
