---
title: Ra lệnh cho robot đọc báo cáo SAP khi cần
date: 2026-11-13
status: accepted
---

# Ra lệnh cho robot đọc báo cáo SAP khi cần

## Hiện trạng (đã kiểm tra trong mã)

- Robot là tiến trình thường trực, cứ 5 giây xem hàng đợi một lần (`saprobot/worker.py`, `run_forever`). Việc chỉ vào hàng đợi khi admin bấm nút trên trang lô.
- `zrsd001` chỉ được xếp một lần, lúc xác nhận lô lần đầu (`web/routes/batches.py`, `confirm_batch`). Nếu lúc đó chưa kiểm tra kết nối SAP, việc không được tạo và về sau không có nút nào để tạo.
- `zrsd004` xếp từ nút "Xuất file gửi kế toán" của từng lô. Dữ liệu việc chỉ gồm sàn, khách hàng SAP và ngày GI; khóa chống trùng là `read_zrsd004:<sàn>:<ngày>` (`sapjobs/report_requests.py`).
- "Chạy lại" chỉ áp dụng cho việc Lỗi, Chưa rõ hoặc Cần kiểm tra (`sapjobs/queue.py`, `retry`). Việc đã Xong không đọc lại được. Đây là chỗ hổng chính: đọc `zrsd001` khi sales admin chưa tạo đủ SO thì việc vẫn "Xong" nhưng thiếu dữ liệu.

## Quyết định của chủ dự án

1. Chọn phương án A: thêm cách ra lệnh cho robot đọc thêm hoặc đọc lại khi cần. Cách chạy tự động hiện có vẫn giữ nguyên.
2. Lệnh đọc `zrsd004` chọn theo sàn và ngày GI, không theo lô.

## Bản chốt

- **Kết quả:** admin chủ động bảo robot đọc báo cáo khi cần, kể cả đọc lại một lần đã xong:
  - Trên trang **Robot SAP** có form "Ra lệnh cho robot": đọc `zrsd001` cho một lô đã xác nhận, hoặc đọc `zrsd004` cho một sàn và một ngày GI.
  - Trang lô đã xác nhận có nút "Đọc lại zrsd001".
  - Các nút tự động hiện có giữ nguyên hành vi.
- **Ràng buộc:**
  - Robot vẫn chỉ đọc SAP. Không thêm T-code, phím hay thao tác nào; `guard.py` không đổi.
  - Lệnh mới dùng chung hàng đợi, chung hàm xếp việc và chung khóa chống trùng với nút tự động.
  - Vẫn chặn khi kết nối SAP chưa được kiểm tra. Khi robot tạm dừng, việc vẫn được xếp và nằm chờ.
  - Chỉ vai trò admin được ra lệnh. Mỗi lệnh ghi một sự kiện vào `event_log`, kèm người ra lệnh.
  - Không cần migration.
- **Không làm:** công tắc tự động/thủ công, đặt lịch chạy theo giờ, bật/tắt tiến trình robot từ web, ghi vào SAP, đọc `zrsd001` tự do theo sàn và ngày (vẫn theo lô, vì kết quả cần nối vào đơn của lô).
- **Tiêu chí hoàn thành:**
  - Admin tạo được việc `read_zrsd001` cho một lô đã xác nhận, kể cả khi việc trước của lô đó đã Xong.
  - Admin tạo được việc `read_zrsd004` cho một sàn và một ngày GI bất kỳ, kể cả ngày không có lô.
  - Bấm khi đang có việc cùng khóa thì bị từ chối, và trang báo số việc đang mở.
  - Lô chưa xác nhận không ra lệnh `zrsd001` được.
  - Kết nối chưa kiểm tra thì bị từ chối với cùng thông báo như nút tự động.
  - Tài khoản không phải admin nhận 403.
  - Robot chạy các việc này như việc thường, và kết quả nhập giống hệt khi tải file lên.
  - Có test cho hàm xếp việc, cho route mới và cho nút đọc lại; `uv run pytest` xanh.
  - `docs/robot-runbook.md` có mục mô tả cách ra lệnh.

## Thay đổi dự kiến

- `sapjobs/report_requests.py`: `request_zrsd004` nhận sàn và ngày GI thay cho lô. Nút "Xuất file gửi kế toán" gọi với `batch.platform` và `batch.gi_date`, nên hành vi không đổi.
- `web/routes/robot.py`: thêm route POST cho lệnh mới (admin), dùng `sap_config` và `UNVERIFIED_MESSAGE` như route của lô.
- `web/routes/batches.py`: thêm route "Đọc lại zrsd001" cho lô đã xác nhận, gọi `request_zrsd001`.
- `templates/robot.html` thêm form; `templates/batch_detail.html` thêm nút.
- Test thêm vào `tests/web/test_robot_web.py` và `tests/web/test_web_flow.py`.

## Đánh đổi

- **A, ra lệnh khi cần (đã chọn).** Giả định quan trọng nhất là người dùng muốn bảo robot làm thêm, không muốn chặn robot tự làm. Rủi ro là admin xếp nhiều lần đọc; khóa chống trùng chỉ cho mỗi báo cáo một việc mở tại một thời điểm.
- **B, công tắc Tự động/Thủ công.** Chỉ cần khi có lý do buộc robot không được tự chạy. Nó trùng vai trò với nút "Tạm dừng robot" và cần migration. Không chọn.
- **C, chỉ bật robot khi cần.** Dựa trên giả định rằng chạy thường trực gây tốn kém, nhưng giả định này sai: lúc rảnh robot không giữ phiên SAP nào. Web cũng không bật được robot, vì robot cần phiên Windows có màn hình. Không chọn.

Better approaches: none. Hướng đã chọn đúng với yêu cầu, và dùng lại hàng đợi, lớp chặn và cơ chế chống trùng việc có sẵn.

## Rủi ro còn lại

- Đọc lại `zrsd001` của một lô sẽ cập nhật SO đã nối. Hàm nhập đã báo số dòng mới, cập nhật và không đổi, nên cần một test xác nhận đọc lại không tạo trùng.
- Đọc `zrsd004` cho ngày không có lô vẫn tạo file kế toán. Đó là hành vi giống khi tải file lên bằng tay, không phải lỗi.
