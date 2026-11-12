---
title: "Lớp chặn T-code cho robot SAP"
date: 2026-11-12
summary: Mọi thao tác của robot với SAP GUI đi qua saprobot/guard.py; T-code lạ thì việc FAILED, có ảnh, robot tự dừng
---

# Lớp chặn T-code cho robot SAP

## Đã xảy ra
- Viết `saprobot/guard.py`: lớp bọc phiên `GuardedSession` là chỗ duy nhất gọi `findById`, `sendVKey`, `HardCopy` và ghi ô lệnh `okcd`. `screen.py`, `statusbar.py`, `popups.py`, `evidence.py` và màn hình đăng nhập trong `session.py` chỉ nhận phiên đã bọc; `send_vkey` và `start_transaction` chuyển từ `screen.py` vào lớp chặn.
- `worker.py` bọc phiên ngay sau `ensure_session`, kiểm tra T-code một lần trước khi chạy thao tác, và xử lý `GuardViolation` như `WrongSystem`: việc `FAILED`, có ảnh, robot tạm dừng, sự kiện `robot_guard_violation`.
- `docs/robot-machine-setup.md`, `docs/robot-runbook.md` đổi sang `AEP`/300, user `AL17016`, thêm mục lớp chặn T-code. Không còn nhắc QA.
- 116 test qua (thêm `tests/saprobot/test_guard.py` và hai test worker), ruff sạch.

## Quyết định
- Danh sách nằm cứng trong mã: phiên chỉ được đứng ở `S000`, `SESSION_MANAGER`, `ZRSD001`, `ZRSD004`; robot chỉ tự mở `ZRSD001`, `ZRSD004`; phím chỉ Enter và F8; phím lưu 11 bị cấm kể cả khi ai đó thêm vào danh sách.
- Kiểm tra trước và sau mỗi thao tác. Sau lần vấp đầu tiên, lớp chặn từ chối mọi thao tác tiếp theo; chỉ chụp màn hình vẫn được.
- Đọc phần tử chỉ trả giá trị thường (chuỗi, số, bool); hàm đọc lưới giới hạn ở `GetCellValue`, `GetColumnTitles`, `GetDisplayedColumnTitle`. Không trả về đối tượng con để không lộ phiên gốc.
- Test quét mã nguồn chặn mọi chỗ ngoài `guard.py` trong `saprobot/` gọi thẳng SAP GUI.

## Chưa làm, chờ người khác
- Cổng bước 9: chủ dự án xác nhận danh sách T-code khớp bản ghi recorder trên `AEP`/300.
- Nếu đọc lưới cần cuộn (`firstVisibleRow`) hoặc cần xuất Excel, thêm vào `guard.py` kèm test khi có bản ghi recorder.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
