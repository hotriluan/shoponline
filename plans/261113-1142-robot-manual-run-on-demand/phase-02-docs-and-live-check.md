---
phase: 2
title: "Tài liệu và chạy thử trên Production"
status: pending
effort: 0.5d
---

# Phase 2: Tài liệu và chạy thử trên Production

## Bối cảnh

- [robot-runbook.md](../../docs/robot-runbook.md): bảng "Robot làm gì" chỉ có hai nút tự động. Mục "Robot tự dừng" nói về bộ đếm lỗi liên tiếp.
- [daily-operations.md](../../docs/daily-operations.md): quy trình hằng ngày của admin. Bước 8 hướng dẫn tự chạy `zrsd001` và tải file lên.
- Deploy: push lên `main`; workflow `deploy` chạy test rồi runner gọi `update-production.ps1` ([deployment-guide.md](../../docs/deployment-guide.md)).

## Yêu cầu

1. `robot-runbook.md`:
   - Thêm hai dòng vào bảng "Robot làm gì": form "Ra lệnh cho robot" và nút "Đọc lại zrsd001".
   - Thêm mục ngắn "Ra lệnh cho robot", nêu bốn điều:
     - khi nào dùng (SO tạo thêm sau lần đọc đầu; lô xác nhận lúc kết nối chưa được kiểm tra; cần file kế toán cho một ngày GI);
     - việc trùng bị từ chối khi việc cũ còn mở;
     - ngày không có dữ liệu sẽ thành Lỗi và tính vào bộ đếm lỗi liên tiếp;
     - lệnh được ghi vào nhật ký sự kiện với tên người ra lệnh.
2. `daily-operations.md`: bước 8 bảo admin tự chạy `zrsd001` trong SAP rồi tải lên. Thêm một câu: khi robot đang bật, robot đọc thay sau khi xác nhận lô; nếu SO được tạo thêm sau đó, bấm "Đọc lại zrsd001" trên trang lô. Tải file bằng tay vẫn là đường dự phòng.
3. Chạy thử trên `AEP`/300 sau khi deploy xanh:
   - Ra lệnh `zrsd004` cho một sàn và một ngày GI đã có DO. Việc phải Xong, và có link file kế toán.
   - Bấm "Đọc lại zrsd001" cho một lô đã đọc trước đó. Việc phải Xong, cột kết quả báo `new` bằng 0 nếu SAP không có SO mới.
4. Ghi kết quả chạy thử vào một journal trong `plans/journals/`.

## Files

- Sửa: `docs/robot-runbook.md`, `docs/daily-operations.md`.
- Tạo: `plans/journals/2026-11-13-ra-lenh-cho-robot.md` (hoặc ngày chạy thử thật).

## Các bước

1. Đọc hai tài liệu trên, sửa phần cần sửa.
2. Kiểm tra mọi liên kết và tên nút trong tài liệu khớp với template đã làm ở phase 1.
3. Commit theo conventional commit (`feat(robot): …` cho mã, `docs(robot): …` cho tài liệu), push lên `main`, theo dõi workflow `deploy` đến khi xanh.
4. Chạy thử trên Production như yêu cầu 3. Không chạy giờ cao điểm SAP.
5. Viết journal.

## Kiểm tra

- Workflow `deploy` xanh; trang `/robot` trên máy thật có khối "Ra lệnh cho robot".
- Hai việc chạy thử ở trạng thái Xong trên trang Robot SAP.

## Rủi ro và lùi lại

- **Lệnh chạy thử thất bại vì ngày không có dữ liệu.** Chọn ngày GI đã biết chắc có DO (xem trang Báo cáo SAP). Nếu robot tự dừng, xem lỗi, rồi bật lại.
- **Lùi lại:** revert commit trên `main`; workflow `deploy` đưa bản cũ lên. Không có migration nên không cần khôi phục database.
