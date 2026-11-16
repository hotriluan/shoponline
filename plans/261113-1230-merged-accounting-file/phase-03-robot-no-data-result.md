# Phase 3: Robot: không có dữ liệu là kết quả hợp lệ

## Bối cảnh

`execute` ném `NoReportData` khi SAP trả "No data to display" ([report_screen.py:40-41](../../src/shoponline/saprobot/transactions/report_screen.py)). `NoReportData` là một `RobotError`, nên worker kết thúc việc ở `FAILED` ([worker.py:338-340](../../src/shoponline/saprobot/worker.py)) và `record_outcome` tăng bộ đếm lỗi liên tiếp; đủ `max_failures` thì robot tự dừng ([worker.py:426](../../src/shoponline/saprobot/worker.py)).

Một đợt xuất đọc nhiều cặp (sàn, ngày), trong đó có ngày chưa có DO. Đó là tình huống bình thường, và nếu để là lỗi thì vài cặp như vậy đủ làm robot dừng. Ngược lại, nếu "No data" tính là thành công và đặt lại bộ đếm về 0, một cấu hình sai (ví dụ sai mã khách hàng của sàn) sẽ không bao giờ làm robot dừng.

## Yêu cầu

- Việc `read_zrsd004` gặp `NoReportData` kết thúc `DONE` với kết quả `{"rows": 0, "delivered": 0, "warnings": [], "no_data": true}`, không có file và không có `import_batch_id`.
- Kết quả `no_data` **trung tính** với bộ đếm lỗi liên tiếp: không tăng, không xóa về 0.
- `read_zrsd001` giữ nguyên: không có dữ liệu vẫn là lỗi.
- Trang Robot SAP hiển thị "SAP chưa có DO" cho kết quả này, không hiển thị như lỗi.

## Tệp được sửa

- `src/shoponline/saprobot/worker.py`
- `tests/saprobot/test_worker.py`
- `src/shoponline/web/templates/robot.html`

## Các bước

1. Test trước:
   - giả lập thao tác `read_zrsd004` ném `NoReportData`: việc `DONE`, `result.no_data` true, `consecutive_failures` giữ nguyên giá trị trước;
   - sau một việc lỗi (đếm = 1) rồi một việc `no_data`, đếm vẫn bằng 1;
   - ba việc `no_data` liên tiếp: robot không dừng;
   - cùng tình huống với `read_zrsd001`: `FAILED` và đếm tăng.
2. Trong worker, bắt `NoReportData` khi loại việc là `read_zrsd004` và tạo kết quả `DONE` không file; `_after_zrsd004` nhận `out` rỗng và trả kết quả trên; `_finish` bỏ qua `record_outcome` khi kết quả là `no_data`.
3. Hiển thị "SAP chưa có DO" trên bảng việc ở `robot.html`.

## Kiểm tra

- `uv run pytest tests/saprobot`.

## Rủi ro và hoàn tác

- Ngày nhập sai hay mã khách hàng sai giờ cũng cho "chưa có DO" thay vì lỗi. Phase 4 giữ cặp "No data" còn đơn chờ ở cổng xác nhận khi chốt, nên không mất đơn âm thầm. Lệnh tay trong form "Ra lệnh cho robot" vẫn nhập được ngày bất kỳ ≤ hôm nay.
- Hoàn tác: bỏ nhánh bắt `NoReportData` và nhánh bỏ qua `record_outcome`.
- Sau khi xong phase này, sửa ghi chú rủi ro tương ứng trong [kế hoạch lệnh robot theo yêu cầu](../261113-1142-robot-manual-run-on-demand/plan.md).
