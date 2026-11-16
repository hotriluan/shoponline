# Phase 4: Dịch vụ đợt xuất, đối chiếu và chốt

## Bối cảnh

Hàng đợi: [queue.py](../../src/shoponline/sapjobs/queue.py) (`enqueue` ném `DuplicateJob` khi khóa đang mở và chỉ bọc lỗi của chính nó trong savepoint; `retry` giữ nguyên hệ thống đích của việc cũ và chỉ nhận việc lỗi; `supersede_checks` là mẫu đóng việc đang chờ). Khóa chống trùng `read_zrsd004:{platform}:{day}` ([report_requests.py:51](../../src/shoponline/sapjobs/report_requests.py)) không chứa hệ thống đích. Worker từ chối việc có đích khác cấu hình hiện tại ([worker.py:280-292](../../src/shoponline/saprobot/worker.py)). Nhật ký sự kiện: [states.py](../../src/shoponline/domain/states.py). Phase 1 cho bảng, `save_generated` mới và hàm gỡ chốt; phase 2 cho bộ dựng file; phase 3 cho kết quả "không có dữ liệu".

## Yêu cầu

Mô-đun `src/shoponline/accounting/runs.py`. Mọi hàm flush, không commit (quy ước của `queue.py`). Dùng `today_vn()` từ `src/shoponline/clock.py` (phase 1 tạo; trong mã hiện tại chưa có hàm nào theo `Asia/Saigon`, chỗ cũ đều dùng `date.today()`). Phase này đổi ba chỗ cũ sang hàm đó để cả ứng dụng dùng một khái niệm "hôm nay": [imports.py:22](../../src/shoponline/web/routes/imports.py), [robot.py:63 và 124](../../src/shoponline/web/routes/robot.py). <!-- Updated: Validation Session 1 - shared helper, replace 3 call sites -->

1. **`due_pairs(session, today)`**:
   - đơn chờ là đơn ở "Đã có SO", hoặc "Đã có DO" với DO chưa có trong sổ, thuộc lô có ngày goods issue dự kiến ≤ hôm nay;
   - với mỗi sàn có đơn chờ: các ngày từ ngày goods issue dự kiến cũ nhất của đơn chờ của sàn đó đến hôm nay, mỗi ngày một cặp, luôn gồm hôm nay; lùi tối đa 31 ngày, đơn chờ cũ hơn thì trả kèm danh sách cảnh báo;
   - cộng thêm các cặp của đợt `REVOKED` chưa nằm trong đợt `FINALIZED` nào sau đó.
2. **`start_run(session, target, actor)`**:
   - có đợt `OPEN` thì chạy `sync_pairs` cho đợt đó và trả về;
   - không có cặp nào thì ném `NothingDue`;
   - tạo đợt bên trong `begin_nested()`; gặp `IntegrityError` (đợt `OPEN` vừa được người khác tạo) thì chọn lại đợt `OPEN` và trả về, trước khi xếp việc nào;
   - với mỗi cặp: tạo dòng đọc và xếp việc bằng `request_zrsd004`. Gặp `DuplicateJob` thì nhận việc đang mở vào đợt **chỉ khi** việc ở `PENDING` hoặc `RUNNING` và đích trùng hệ thống hiện tại; ngược lại đóng việc cũ (theo mẫu `supersede_checks`, kèm lý do) và xếp việc mới;
   - không có hệ thống đích đã kiểm tra thì vẫn tạo đợt và các dòng đọc không có việc, để nhập tay.
3. **`sync_pairs(session, run)`**: gọi lại `due_pairs` và thêm dòng đọc cho cặp mới (lô được xác nhận hay ngày goods issue sửa sau khi đợt mở). Được gọi khi `start_run` mở lại đợt và khi xem trang đợt.
4. **`run_status(session, run)`** (rẻ, chỉ đọc các dòng việc): trạng thái từng cặp là `đang đọc` (việc chờ hoặc chạy), `xong có DO`, `SAP chưa có DO` (kết quả `no_data`), `lỗi` (FAILED, UNKNOWN, NEED_REVIEW kèm nội dung lỗi), `thiếu file nguồn` (đường dẫn file không còn), `chưa có việc`. Cặp có dữ liệu nếu việc `DONE` có file, hoặc có file gắn vào đợt chứa dòng của đúng sold-to và ngày goods issue.
5. **`retry_read(session, run, read, actor)`**: việc lỗi và đích trùng thì dùng `queue.retry`; việc đã `DONE` (kể cả `no_data`) hoặc đích khác thì xếp việc mới và đổi `sap_job_id` của dòng đọc sang việc mới.
6. **`attach_upload(session, run, import_batch)`**: ghi `accounting_run_source`. Chỉ gọi từ trang đợt (file mới tải hoặc chọn từ các file `zrsd004` đã tải lên chưa thuộc đợt nào kể từ đợt chốt trước). Không có tự gắn từ trang Báo cáo SAP.
7. **`reconcile(session, run)`** (chạy theo yêu cầu, không chạy mỗi lần làm mới trang): dựng file bằng hàm của phase 2 với tra khách theo lô (một truy vấn cho các SO và một cho `CustomerInfo`, thay vì theo từng dòng). Trả về:
   - các nguồn của đợt (file từ việc `DONE` có `import_batch_id` và file đã gắn), các số Delivery sẽ vào file, các số SO có trong file, số dòng bị bỏ theo lý do;
   - **`missing`**: đơn chờ (cùng định nghĩa ở `due_pairs`) mà SO không nằm trong file, kèm sàn, mã đơn, SO, ngày goods issue dự kiến;
   - **`unknown`**: DO trong file mà SO không thuộc đơn nào trên web;
   - **`warnings`**: thiếu mã đơn, tên, địa chỉ;
   - dòng tóm tắt ("Web đáng ra có 15 đơn, file có 14 DO, thiếu 1");
   - **dấu vân tay**: băm của danh sách id nguồn đã sắp, tập DO bị loại, danh sách cặp thiếu và danh sách `missing`.
8. **`draft_file(session, run)`**: dựng file có tiền tố `NHÁP`, trả về workbook trong bộ nhớ cùng dấu vân tay. Không gọi `save_generated`, không ghi sổ.
9. **`finalize(session, run, actor, fingerprint, allow_partial, ack_missing)`**, trong một giao dịch:
   - khóa dòng `accounting_run` (`FOR UPDATE`); không còn `OPEN` thì từ chối;
   - tính lại `reconcile`; dấu vân tay khác thì ném `StaleReview` ("Dữ liệu đã đổi, xem lại bản nháp");
   - còn cặp chưa có dữ liệu (không tính `SAP chưa có DO`) mà `allow_partial` sai thì ném `ReadsIncomplete` kèm danh sách cặp;
   - còn `missing` mà `ack_missing` sai thì ném `MissingNotAcknowledged`;
   - `FileRejected("Không có DO mới")` thì báo và không đổi gì;
   - `save_generated` lưu file, gán `generated_file_id`, ghi mọi Delivery trong file vào sổ, đặt `FINALIZED`, ghi `missing_note`;
   - ghi sự kiện `accounting_run_finalized` với số DO, cặp thiếu đã xác nhận, `missing` (sàn và mã đơn), `unknown`, số dòng bị bỏ.
   - Nếu giao dịch hỏng sau khi file đã ghi đĩa, route phase 5 xóa file đó (try/finally).
10. **`cancel_run`**: đặt `CANCELLED`, không đổi sổ; việc robot đang chờ của đợt không bị hủy (chúng vẫn nhập dữ liệu bình thường).
11. **`revoke_run`** dùng lại hàm của phase 1 (`accounting/ledger.py`); bảo đảm các cặp của đợt vào lại `due_pairs`.

## Tệp được sửa

- `src/shoponline/accounting/runs.py` (mới; package `accounting/` do phase 1 tạo)
- `src/shoponline/web/routes/imports.py`, `src/shoponline/web/routes/robot.py` (chỉ đổi `date.today()` thành `today_vn()`)
- `tests/accounting/test_runs.py` (mới)
- `tests/conftest.py` hoặc `tests/accounting/conftest.py`: fixture mở hai kết nối thật vào chính database `*_test`, ghi dữ liệu đã commit và xóa sạch ở cuối test (kể cả khi test lỗi), dùng cho các test đồng thời. Không tạo database riêng; không dùng fixture `db` (một kết nối, hoàn tác cuối test) cho các test này. <!-- Updated: Validation Session 1 - same _test database -->

## Các bước

1. Test trước cho `due_pairs` (cửa sổ từng ngày, lùi 31 ngày, đợt hủy chốt, ba sàn, hai sàn, không sàn nào) và `start_run` (đợt đã mở, việc cũ, việc khác đích, `PENDING` cùng đích được nhận).
2. `run_status`, `retry_read`, `sync_pairs`.
3. `reconcile`: các ca đủ, thiếu một đơn, DO lạ, DO nhiều dòng, dòng bị bỏ.
4. `draft_file`, `finalize` và các cổng.

## Kiểm tra

- Chốt xong, `start_run` rồi `finalize` lần nữa trên dữ liệu không đổi: `NothingDue` hoặc `Không có DO mới`, không DO nào ghi hai lần.
- Chốt thiếu sàn: DO của sàn thiếu không có trong sổ; đợt sau đọc xong và chốt thì file chứa đúng DO đó.
- Hai kết nối thật chốt cùng một đợt: một thành công, một bị từ chối. Hai kết nối thật gọi `start_run` cùng lúc: cả hai trả về cùng một đợt, không lỗi.
- Việc robot xong thêm hoặc file được gắn giữa lúc xem và lúc chốt: `StaleReview`.
- Việc `PENDING` cũ cho đích khác bị đóng; "Đọc lại" cho cặp `no_data` xếp việc mới.
- DO trong sổ nền, có ngày ≤ mốc, thuộc khách lạ, chưa goods issue hoặc trạng thái khác `C` đều bị loại, kể cả khi nằm trong file đã gắn.
- `revoke_run` làm các cặp quay lại `due_pairs`.
- Sự kiện nhật ký có đủ danh sách đơn chưa có DO khi chốt.

## Rủi ro và hoàn tác

- `reconcile` đọc nhiều file xlsx; cố ý chỉ chạy khi mở phần đối chiếu hoặc chốt, không chạy theo lần tự làm mới.
- Hoàn tác: các hàm mới chỉ được gọi từ phase 5 và CLI.
