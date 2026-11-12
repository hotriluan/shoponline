# Brainstorm: thu hẹp robot SAP về chỉ đọc báo cáo trên Production

Ngày: 2026-11-12. Áp dụng cho [plan shopee-excel-to-sap-order-flow](../261111-0755-shopee-excel-to-sap-order-flow/plan.md).

## Quyết định

Robot không tạo SO, DO hay post goods issue. Sales admin tiếp tục làm việc này như hiện nay, nên không cần ai phê duyệt thêm. Robot chỉ chạy `zrsd001` và `zrsd004` trên Production để hệ thống xuất file gửi kế toán. Giữ hướng robot SAP GUI Scripting; không dùng job nền SAP.

Thông tin từ chủ dự án:
- IT cấp được user robot truy cập `zrsd001` và `zrsd004`.
- License của user robot đã có sẵn, không tốn thêm phí.

## Lý do

- Phase 6–8 có ba rủi ro nặng nhất của kế hoạch: bản ghi `ZDI1` dùng chung, tạo trùng SO khi mất phiên, và post goods issue khó đảo ngược. Bỏ ba phase này thì ba rủi ro đó không còn.
- Giảm 12 trên 36 ngày công.
- Không còn việc nào cần QA, nên không còn vấn đề QA thiếu dữ liệu giống thật.
- Hàng đợi, kiểm tra hệ thống đích và xử lý popup vẫn giữ lại. Nếu sau này muốn robot ghi SO thì mở lại thành dự án riêng.

## Hợp đồng

- **Kết quả:** chế độ `manual` cho cả ba sàn là chế độ duy nhất. Robot đọc `zrsd001` sau khi admin xác nhận lô, và đọc `zrsd004` vào ngày goods issue, trên Production. Đường tải file tay vẫn giữ làm đường lùi.
- **Ràng buộc:**
  - Robot chỉ được vào `zrsd001` và `zrsd004`, và điều này được chặn bằng mã trong dự án (xem mục "Bổ sung" bên dưới). Giới hạn role của user robot phía SAP là khuyến nghị thêm, không phải điều kiện.
  - Báo cáo luôn được lọc theo ngày và theo khách hàng SAP của sàn.
  - Chủ dự án ghi recorder trên Production bằng chính user robot.
  - Claude Code không chạy robot trên SAP thật; chủ dự án là người chạy.
- **Ngoài phạm vi:** robot tạo SO, DO, post goods issue, `ZDI1`; chế độ `shadow` và `live`; QA; job nền SAP.
- **Tiêu chí hoàn thành:**
  - Kế hoạch bỏ phase 6, 7, 8, bỏ cổng G2 và G3, bỏ tiêu chí "chế độ `live`" và bỏ bảng chế độ `shadow`/`live`.
  - Phase 5 chạy trên Production ở chế độ chỉ đọc. Các thử nghiệm ngắt mạng và sai hệ thống đích chạy trên Production, vì việc đọc không gây hại.
  - Phase 9: các buổi diễn tập chạy trên Production và chỉ đọc. Diễn tập "rút mạng khi robot đang tạo SO" được thay bằng rút mạng khi robot đang đọc báo cáo.
  - Tài liệu robot (`docs/robot-machine-setup.md`, `docs/robot-runbook.md`) đổi ví dụ `QAS/300` thành hệ thống Production.
  - 5 ngày làm việc chạy song song: dữ liệu robot đọc giống hệt file admin tải lên.
  - `uv run pytest` thoát mã 0.

## Ảnh hưởng tới mã

Gần như không có. Hệ thống đích đã lấy từ `SHOPONLINE_SAP_SYSTEM` và `SHOPONLINE_SAP_CLIENT`. Cột chế độ `shadow`/`live` trong `platform_setting` được giữ nguyên và đánh dấu là không dùng. Không viết migration chỉ để xóa cột này.

## Rủi ro còn lại

- **File gửi kế toán sai do robot đọc sai.** Chặn bằng cách chạy song song 5 ngày và giữ đường tải tay.
- **Màn hình SAP thay đổi sau khi nâng cấp.** Robot dừng, chụp màn hình, và admin quay lại tải file tay.
- **User robot được cấp rộng hơn hai báo cáo.** Khi đó lớp chặn T-code trong mã là hàng rào duy nhất.

## Bổ sung: chặn T-code bằng mã trong dự án

Chủ dự án quyết định chặn ở phía mã: robot không được vào T-code nào ngoài `zrsd001` và `zrsd004`.

**Thiết kế:**
- Mọi thao tác của robot với SAP GUI đi qua một lớp bọc phiên duy nhất (`saprobot/guard.py`). Các thao tác trong `transactions/` không bao giờ nhận đối tượng phiên gốc.
- Danh sách T-code được phép nằm cứng trong mã, không nằm trong file YAML, để không ai nới được chỉ bằng cách sửa cấu hình. Danh sách gồm `ZRSD001`, `ZRSD004`, cùng màn hình đăng nhập và menu chính. Tên kỹ thuật chính xác của hai màn hình sau lấy từ bản ghi recorder.
- `start_transaction` chỉ nhận T-code có trong danh sách. Không có đường nào khác để ghi vào ô lệnh `okcd`.
- Trước và sau mỗi thao tác (gõ chữ, bấm nút, gửi phím, bấm popup), robot đọc `session.Info.Transaction`. Nếu T-code nằm ngoài danh sách thì robot dừng ngay: không bấm thêm gì, chụp màn hình, việc chuyển `FAILED`, và robot tự tạm dừng giống cách xử lý `WrongSystem`. Chỉ `admin` bật lại được.
- Chỉ cho phép gửi các phím đã liệt kê (Enter, F8). Phím lưu (Ctrl+S, `sendVKey 11`) bị cấm.
- Có test chứng minh không còn chỗ nào trong `saprobot/` ghi `okcd` hoặc gọi phiên gốc ngoài `guard.py`.

**Giới hạn:** lớp chặn này bảo vệ trước lỗi trong mã và trước những màn hình SAP tự chuyển sang T-code khác (ví dụ bấm đúp vào dòng báo cáo mở VA03 hoặc VA02). Nó không chặn được người đăng nhập SAP bằng user robot trên máy robot, và không chặn được lỗi nằm trong chính lớp chặn. Nếu IT giới hạn role của user robot thì sẽ thêm một lớp bảo đảm phía SAP; đây là khuyến nghị, không phải điều kiện.

## Bổ sung: user robot

Robot dùng user riêng `AL17016` trên `AEP`/300, không dùng `BASIS01`. Lý do không dùng `BASIS01`: mật khẩu user Basis sẽ nằm trên máy robot; robot sẽ nhận nhầm phiên do người mở nếu cùng user; đăng nhập trùng sẽ hiện hộp thoại; nhật ký SAP không tách được việc của robot và của người.

## Câu hỏi còn mở

- Tên `Info.Transaction` của màn hình đăng nhập và menu chính trên hệ thống của công ty (thường là `S000` và `SESSION_MANAGER`). Xác nhận khi ghi recorder.
