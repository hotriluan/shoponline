# Phase 5: Giao diện web

## Bối cảnh

Hiện có ba chỗ tạo file kế toán một sàn:

- nút "Xuất file gửi kế toán" ở [batch_detail.html:28](../../src/shoponline/web/templates/batch_detail.html) gọi [batches.py:177](../../src/shoponline/web/routes/batches.py) (chỉ hiện khi robot bật và đã kiểm tra kết nối);
- route `GET /sap-reports/zrsd004/{record_id}/accounting-file` ở [sap_reports.py:99](../../src/shoponline/web/routes/sap_reports.py), liên kết từ [accounting_preview.html:14](../../src/shoponline/web/templates/accounting_preview.html), [robot.html:78](../../src/shoponline/web/templates/robot.html) và [sap_reports.html:28](../../src/shoponline/web/templates/sap_reports.html).

Route admin bị viewer gọi không trả 403 mà chuyển hướng 303 kèm thông báo (trừ yêu cầu autosave) ([app.py:198-203](../../src/shoponline/web/app.py)).

## Yêu cầu

- Trang **Gửi kế toán** (`/accounting`), có mục trong thanh điều hướng của [base.html](../../src/shoponline/web/templates/base.html): danh sách các đợt gần đây (trạng thái, người chốt, thời điểm, số DO, tải file đã chốt) và, nếu có đợt `OPEN`, chi tiết đợt; nếu không có thì nút bắt đầu (admin) và số đơn đang chờ.
- Chi tiết đợt (`/accounting/runs/{id}`):
  - gọi `sync_pairs`; bảng cặp (sàn, ngày) với trạng thái từ `run_status`; trang tự làm mới khoảng 10 giây **chỉ khi còn cặp đang đọc**, và khi đó chỉ dựng bảng trạng thái;
  - cặp lỗi hoặc `SAP chưa có DO`: nút **Đọc lại**; một ô **Tải zrsd004 lên đợt** duy nhất cho cả đợt, cùng danh sách file `zrsd004` đã tải lên chưa thuộc đợt nào với nút **Thêm vào đợt**;
  - khi không còn cặp đang đọc: phần **Đối chiếu** (gọi `reconcile`): dòng tóm tắt, khung **Chưa thấy DO** (sàn, mã đơn, SO, ngày goods issue dự kiến), khung **DO không thuộc đơn nào trên web**, số dòng bị bỏ theo lý do, cảnh báo thiếu mã đơn, tên, địa chỉ, và cảnh báo đơn chờ cũ hơn 31 ngày;
  - nút **Tải bản nháp**, gửi trực tiếp từ bộ nhớ;
  - nút **Chốt và ghi sổ** mang theo dấu vân tay ẩn. Ô tích **chốt thiếu sàn** (nêu tên cặp) hiện khi còn cặp chưa có dữ liệu; ô tích **đã xem danh sách đơn chưa có DO** hiện khi còn `missing`. Nút khóa cho tới khi mọi ô cần thiết được tích;
  - nút **Hủy đợt**.
- Đợt đã chốt: chỉ đọc, tải đúng file đã lưu (`generated_file`) kèm đối chiếu đã ghi lúc chốt; file không còn trên đĩa thì trả 404 với thông báo rõ.
- Nút ở trang lô đổi thành **Xuất file gửi kế toán** gọi `start_run` rồi chuyển tới đợt. Giữ nguyên URL `POST /batches/{id}/accounting-file` ([batches.py:177](../../src/shoponline/web/routes/batches.py)), chỉ đổi nội dung xử lý; nút này không phụ thuộc lô, đợt luôn tính từ toàn bộ đơn chờ. <!-- Updated: Validation Session 1 - keep batch URL --> Nút hiện cho admin kể cả khi robot tắt hay chưa kiểm tra kết nối (khi đó đợt chỉ có các dòng đọc chưa có việc, và hiện thông báo từ `robot_refusal` ([app.py](../../src/shoponline/web/app.py)) cùng hướng dẫn tải tay). Thông báo flash cũ ở [batches.py:197-201](../../src/shoponline/web/routes/batches.py) bị thay.
- Bỏ route `download_accounting_file`; thay liên kết "Tải file kế toán" ở `robot.html`, `sap_reports.html` và nút ở `accounting_preview.html` bằng liên kết tới `/accounting`; đổi tiêu đề mục ở [sap_reports.html:16](../../src/shoponline/web/templates/sap_reports.html) nếu còn nhắc "file gửi kế toán"; xóa các import thừa trong `sap_reports.py` (`FileResponse`, `build_accounting_workbook`, `save_generated`) nếu không còn dùng. Màn hình xem trước sau khi tải tay vẫn hiện cảnh báo, kèm gợi ý "Vào Gửi kế toán để gửi file".
- Quyền: `require_admin` cho bắt đầu, đọc lại, tải lên, thêm vào đợt, chốt, hủy; `current_user` cho xem và tải file đã chốt. Bản nháp dành cho admin.

## Tệp được sửa

- `src/shoponline/web/routes/accounting.py` (mới), đăng ký trong `src/shoponline/web/app.py`
- `src/shoponline/web/templates/accounting.html`, `accounting_run.html` (mới)
- `src/shoponline/web/routes/batches.py`, `src/shoponline/web/routes/sap_reports.py`
- `src/shoponline/web/templates/base.html`, `batch_detail.html`, `robot.html`, `sap_reports.html`, `accounting_preview.html`
- `tests/web/test_accounting_routes.py` (mới)
- Các test hiện có sẽ vỡ, phải sửa theo hành vi mới (không nới lỏng kiểm tra):
  - [test_web_flow.py:144-163](../../tests/web/test_web_flow.py): lấy id từ liên kết cũ, tải từ route cũ, kiểm retention 404 của route cũ. Viết lại thành luồng: tải zrsd004 → `/accounting` → bản nháp → chốt → tải; kiểm file đã chốt bị xóa khỏi đĩa thì 404 rõ.
  - [test_robot_web.py:64-75, 142-152](../../tests/web/test_robot_web.py): "bấm lần hai bị từ chối" đổi thành "bấm lần hai mở lại đúng đợt, không tạo việc mới".
  - [test_sap_connection.py:201-210](../../tests/web/test_sap_connection.py): đổi theo nút luôn hiện và khóa/tắt ở chỗ khác.

## Các bước

1. Viết test route trước: quyền, bắt đầu, làm mới, đọc lại, tải lên, thêm vào đợt, chốt, các cổng chốt, dấu vân tay cũ, tải bản nháp, tải file đã chốt, 404.
2. Viết route và template; dùng lại `flash`, `redirect`, `render` và kiểu trang hiện có. Route chốt bọc việc lưu file trong try/finally để xóa file nếu giao dịch hỏng.
3. Đổi các liên kết cũ, xóa route cũ, sửa các test nêu trên.
4. Chạy thử trên máy phát triển với dữ liệu mẫu của ba sàn: bắt đầu đợt, xem, chốt, tải file, bắt đầu đợt mới.

## Kiểm tra

- Viewer thao tác bắt đầu, đọc lại, tải lên, thêm vào đợt, chốt, hủy: bị chuyển hướng kèm thông báo từ chối, không dòng nào của `accounting_run`, nguồn hay sổ thay đổi; xem trang và tải file đã chốt thì được. Viewer tải bản nháp bị từ chối.
- Chốt khi còn cặp chưa có dữ liệu mà không tích: bị từ chối, sổ không đổi; tích thì chốt được và `missing_note` ghi đúng.
- Chốt khi còn đơn chưa có DO mà không tích: bị từ chối.
- Tải file đã chốt hai lần cho cùng byte; sha256 khớp.
- `grep` không còn route `download_accounting_file` (`/sap-reports/zrsd004/{id}/accounting-file`) và không còn chuỗi "Tải file kế toán"; chuỗi `accounting-file` chỉ còn ở route lô `POST /batches/{id}/accounting-file` và test của nó. <!-- Updated: Validation Session 1 - batch URL kept -->
- `uv run pytest` và `uv run ruff check`.

## Rủi ro và hoàn tác

- Người quen tải file kế toán ngay trên trang Robot SAP sẽ phải qua trang Gửi kế toán; ghi trong phase 6.
- Hoàn tác: khôi phục route và liên kết cũ; sổ và bảng đợt không ảnh hưởng.
