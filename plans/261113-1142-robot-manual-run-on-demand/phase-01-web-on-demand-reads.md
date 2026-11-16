---
phase: 1
title: "Lệnh đọc báo cáo trên web"
status: pending
effort: 0.5d
---

# Phase 1: Lệnh đọc báo cáo trên web

## Bối cảnh

- [report_requests.py](../../src/shoponline/sapjobs/report_requests.py):
  - `request_zrsd001(session, target, batch, actor)`: khóa chống trùng là `read_zrsd001:batch:<id>`.
  - `request_zrsd004(session, target, batch, actor)`: chỉ dùng `batch.platform` và `batch.gi_date`; khóa chống trùng là `read_zrsd004:<sàn>:<ngày>`.
- [queue.py](../../src/shoponline/sapjobs/queue.py): `enqueue` từ chối khóa trùng của việc đang mở bằng `DuplicateJob`, và ghi `sap_job_enqueued` kèm người ra lệnh.
- [batches.py](../../src/shoponline/web/routes/batches.py):
  - `UNVERIFIED_MESSAGE` khai báo ở dòng 30;
  - `confirm_batch` chỉ xếp `zrsd001` khi lô chưa xác nhận;
  - `request_accounting_file` kiểm tra `config.target` và `config.target_verified` rồi mới xếp việc.
- [robot.py](../../src/shoponline/web/routes/robot.py): trang `/robot`, các route tạm dừng, bật lại, chạy lại; dùng `require_admin` và `sap_config` từ [app.py](../../src/shoponline/web/app.py).
- Template: [robot.html](../../src/shoponline/web/templates/robot.html) (khối trạng thái ở đầu trang) và [batch_detail.html](../../src/shoponline/web/templates/batch_detail.html) (khối nút ở dòng 12-30).
- Test mẫu: [test_robot_web.py](../../tests/web/test_robot_web.py) (`_app`, `_login`, fixture `batch`, `_jobs`) và [test_worker.py](../../tests/saprobot/test_worker.py) (`test_zrsd001_read_goes_through_the_upload_functions`).

## Yêu cầu

1. **`request_zrsd004(session, target, platform, gi_date, actor)`.**
   - Nhận mã sàn và ngày thay cho lô. Khóa chống trùng và dữ liệu việc giữ nguyên.
   - Sàn không có trong `platform_setting` thì báo `ValueError("Không có sàn …")`.
   - Sửa nơi gọi trong `request_accounting_file` và trong `test_worker.py`.
2. **Một chỗ kiểm tra robot sẵn sàng.**
   - Chuyển `UNVERIFIED_MESSAGE` sang [app.py](../../src/shoponline/web/app.py), cạnh `sap_config`.
   - Thêm `robot_refusal(config) -> str | None`. Hàm trả thông báo khi chưa đặt hệ thống đích, hoặc khi kết nối chưa được kiểm tra; trả `None` khi robot sẵn sàng.
   - `request_accounting_file` và hai route mới dùng hàm này. `confirm_batch` giữ thông báo riêng của nó và chỉ đổi chỗ import `UNVERIFIED_MESSAGE`.
3. **Route `POST /batches/{batch_id}/read-zrsd001` (admin).**
   - Lô chưa xác nhận: báo lỗi, không xếp việc.
   - Robot chưa sẵn sàng: báo theo `robot_refusal`.
   - `DuplicateJob`: báo lỗi kèm số việc đang mở.
   - Thành công: báo "Robot sẽ đọc lại zrsd001 (việc #N)".
   - Mọi trường hợp đều chuyển về trang lô.
4. **Route `POST /robot/jobs/new` (admin).**
   - Trường `report`: `zrsd001` hoặc `zrsd004`.
   - Với `zrsd001`: trường `batch_id`. Lô phải tồn tại và đã xác nhận.
   - Với `zrsd004`: trường `platform` và `gi_date`. Sàn phải có trong `platform_setting`, và ngày không được sau hôm nay. "Hôm nay" lấy bằng `date.today()`, giống trang nhập file ([imports.py:22](../../src/shoponline/web/routes/imports.py)); máy chủ chạy giờ Việt Nam.
   - Giá trị `report` khác: 400. Thiếu trường: báo lỗi trên trang.
   - Ra lệnh thành công hay bị từ chối đều chuyển về `/robot` kèm thông báo.
5. **Giao diện.**
   - `robot.html`: thêm khối "Ra lệnh cho robot". Chỉ hiện khi người xem là admin và robot đã có hệ thống đích. Khối gồm hai form nhỏ:
     - đọc `zrsd001`: chọn lô từ 60 lô đã xác nhận gần nhất, hiện dạng "SHOPEE 11/11/2026";
     - đọc `zrsd004`: chọn sàn (tên hiển thị) và ngày GI (`<input type="date">`, `max` là hôm nay, mặc định hôm nay).

     Khi kết nối chưa được kiểm tra, khối hiện dòng lý do thay cho nút.
   - `robot_page` nạp thêm `batches` và `platforms` cho form.
   - `batch_detail.html`: với lô đã xác nhận, thêm nút "Đọc lại zrsd001" cạnh "Tải zrsd001", cùng điều kiện hiện với nút "Xuất file gửi kế toán" (`robot_enabled`, `robot_verified`, admin). Nút có hộp xác nhận "Robot sẽ đọc lại zrsd001 của lô này?".

## Files

- Sửa:
  - `src/shoponline/sapjobs/report_requests.py`
  - `src/shoponline/web/app.py`
  - `src/shoponline/web/routes/batches.py`
  - `src/shoponline/web/routes/robot.py`
  - `src/shoponline/web/templates/robot.html`
  - `src/shoponline/web/templates/batch_detail.html`
  - `tests/web/test_robot_web.py`
  - `tests/saprobot/test_worker.py`
- Không tạo file mã mới.

## Các bước

1. Viết test trước, trong `tests/web/test_robot_web.py`:
   - đọc lại `zrsd001` từ trang lô sau khi việc đầu đã Xong (đặt trạng thái bằng `queue.claim` + `queue.complete`) tạo việc thứ hai cùng khóa;
   - bấm khi việc đầu còn Chờ thì bị từ chối, trang báo số việc;
   - lô chưa xác nhận bị từ chối;
   - form `zrsd004` trên `/robot` tạo việc có dữ liệu `{"platform", "sold_to", "gi_date"}` đúng như nút của lô; ngày mai bị từ chối; sàn lạ bị từ chối;
   - kết nối chưa được kiểm tra thì cả hai route từ chối với `UNVERIFIED_MESSAGE` (dùng `tests/sap_setup.py` để đặt cấu hình chưa xác nhận, theo mẫu trong `test_sap_connection.py`);
   - viewer nhận 403 ở cả hai route, và trang `/robot` không có form;
   - robot chưa bật (target `None`) thì `/robot` không có form.
2. Trong `tests/saprobot/test_worker.py`, thêm test chạy `zrsd001` hai lần cho cùng lô bằng file mẫu đang dùng: lần hai báo `new == 0`, số liên kết SO của lô không đổi.
3. Sửa `request_zrsd004` và nơi gọi; chuyển `UNVERIFIED_MESSAGE`, thêm `robot_refusal`.
4. Thêm hai route và giao diện.
5. Chạy kiểm tra (mục dưới), sửa đến khi xanh.

## Kiểm tra

- `uv run pytest tests/web/test_robot_web.py tests/saprobot/test_worker.py`
- `uv run pytest`
- `uv run ruff check`
- Xem tay bằng `uv run shoponline web` trên máy phát triển: form hiện đúng với admin, không hiện với viewer.

## Rủi ro và lùi lại

- **Đọc lại `zrsd001` cập nhật SO đã nối.** Test ở bước 2 phải chứng minh không tạo trùng. Nếu test đỏ, dừng lại và báo chủ dự án trước khi sửa `report_ingest.py`, vì đó là đường nhập dùng chung với tải file lên.
- **Lùi lại:** revert commit. Không có migration và không đổi dữ liệu; việc đã xếp vẫn là việc đọc bình thường mà robot hiện tại chạy được.
