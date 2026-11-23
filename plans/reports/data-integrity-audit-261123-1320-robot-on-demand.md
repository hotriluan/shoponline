# Rà soát plan 261113-1142 (robot đọc khi cần): trùng và sót dữ liệu

Ngày: 2026-11-23. Phase 6 của `261123-0556-red-team-validate-data-integrity-audit`. Chỉ đọc mã và văn bản, không sửa mã. Số đếm lấy từ dev DB, 2026-11-23 (không phải production).

## 1. Đối chiếu phạm vi plan với mã (kết luận: gần như đã làm xong)

Plan ghi `pending`, nhưng mã đã commit `5a4ac9c` (2026-11-13) và tài liệu `0ed5301`.

| Mục của plan | Tình trạng | Bằng chứng |
|---|---|---|
| `request_zrsd004(session, target, platform, gi_date, actor)` | Đã có | `report_requests.py:38-60`; nơi gọi `accounting/runs.py:285` |
| `robot_refusal` và `UNVERIFIED_MESSAGE` ở `app.py` | Đã có | `app.py:115-125`; dùng ở `robot.py`, `batches.py:227`, `accounting.py:58` |
| Route `POST /batches/{id}/read-zrsd001` (admin) | Đã có | `batches.py:214-239` |
| Route `POST /robot/jobs/new` (admin; zrsd001, zrsd004, thêm cả zrsd003) | Đã có | `robot.py:110-157` |
| Form "Ra lệnh cho robot", ẩn với viewer hoặc khi chưa có hệ thống đích | Đã có | `robot.html:29-58` |
| Nút "Đọc lại zrsd001" trên trang lô | Đã có | `batch_detail.html:23-28` |
| Test web và worker (đọc lại, trùng, lô chưa xác nhận, ngày tương lai, chưa kiểm tra kết nối, viewer, không có form) | Đã có | `tests/web/test_robot_web.py:137-260`; `tests/saprobot/test_worker.py:128` |
| `pytest` hai file và `ruff check` | Xanh: 36 passed, ruff sạch | chạy 2026-11-23 |
| Mục "Ra lệnh cho robot" trong `robot-runbook.md`, câu ở bước 8 `daily-operations.md` | Đã có | `robot-runbook.md:32-39`; `daily-operations.md:17` |
| Chạy thử trên `AEP`/300 và journal | **Chưa có bằng chứng** | không có journal; dev DB có việc do người ra lệnh nhưng đó là máy dev, không phải production |

Kết luận: chỉ còn tiêu chí 9 (chạy thử production và journal). Phạm vi mã đã đủ, không còn gì để thu hẹp. Đề xuất: đóng plan thành `completed` sau khi chủ dự án xác nhận đã chạy thử, hoặc `completed` kèm ghi chú "chạy thử production chưa có biên bản".

## 2. Phát hiện (red team, lens bảo mật, giả định, trùng/sót)

| # | Phát hiện | Mức | Lens | Bằng chứng | Xử lý đề xuất |
|---|---|---|---|---|---|
| 1 | Trạng thái plan sai: `pending` trong khi mã và tài liệu đã xong | Medium | Giả định | plan.md dòng 5; commit `5a4ac9c`, `0ed5301` | Đổi `completed` (hoặc `in-progress` tới khi có biên bản chạy thử); cần chủ dự án duyệt |
| 2 | "Đọc lại zrsd001" vẫn lọc đúng một ngày (`date_from = date_to = processing_date`). SO của đơn trong lô mà sales admin tạo vào ngày sau sẽ không bao giờ được đọc, nút đọc lại không cứu được | Medium | Sót | `report_requests.py:18,28-29`; plan "Ngoài phạm vi" loại trừ đọc tự do theo ngày | Chấp nhận rủi ro đã loại trừ và ghi vào runbook, hoặc làm plan mới cho khoảng ngày (chủ dự án quyết định) |
| 3 | Lệnh tay `zrsd004` đang chờ cho hệ thống đích khác với đợt gửi kế toán bị đợt đóng bằng `close_waiting` ("Thay bằng việc của đợt gửi kế toán"); admin không được báo | Low | Trùng/sót | `accounting/runs.py:290-297` | Chấp nhận: việc bị thay đúng chủ ý, còn dấu vết trong nhật ký sự kiện |
| 4 | Ghi nhận DO chỉ cho đơn `SO_LINKED` và chỉ DO đầu của mỗi SO; đọc lại `zrsd004` không bắt DO thứ hai | Low | Sót | `so_link.py:303-313`; plan `261113-1230` đã xử lý bằng quyết định 8, 9 | Không làm gì ở plan này; phase 7 kiểm số đếm |
| 5 | Văn bản phase 2 sai: "ngày không có dữ liệu sẽ thành Lỗi và tính vào bộ đếm lỗi liên tiếp" chỉ đúng với `zrsd001`; `zrsd004` và `zrsd003` kết thúc `Xong` và trung tính | Low | Giả định | `worker.py:128,144,436-444`; `robot-runbook.md:36` đã viết đúng | Sửa chữ trong phase 2 nếu cần; tài liệu thật không sai |
| 6 | Văn bản plan dùng `date.today()` cho "hôm nay", mã dùng `today_vn()` (đúng hơn) | Low | Giả định | `robot.py:147,168` | Cập nhật chữ plan; không đổi mã |
| 7 | Phạm vi plan chỉ có zrsd001 và zrsd004, form thực tế có thêm zrsd003 | Low | Phạm vi | `robot.py:128,168-176`; `robot.html:53-58` | Ghi vào plan: zrsd003 thêm bởi plan `261119-0854` |

Đã kiểm và bác (không phải phát hiện):

- Trùng việc khi hai admin bấm cùng lúc: bác. Chỉ mục duy nhất từng phần `uq_sap_job_active_key` (`migrations/versions/0004_sap_job.py:47-53`) và `IntegrityError` được đổi thành `DuplicateJob` (`queue.py:98-101`).
- Đọc lại `zrsd001` tạo SO hoặc liên kết trùng: bác. Có test `test_reading_zrsd001_twice_creates_no_duplicate_links` (`test_worker.py:128`).
- Đọc lại `zrsd004` cho ngày đã gửi kế toán làm lùi trạng thái hoặc gửi trùng: bác. `mark_delivered` chỉ chuyển đơn đang `SO_LINKED` (`so_link.py:309-312`); sổ DO đã gửi là bảng riêng `accounting_sent_delivery` (`models.py:381`).
- Tiêm dữ liệu qua form: bác. `report` có danh sách cho phép (`robot.py:130`), `batch_id` kiểm `isdigit`, ngày qua `fromisoformat`, sàn qua `ValueError` của `request_zrsd004`; `OrderBatch.platform` là khóa ngoại tới `platform_setting` (`models.py:96`) nên `setting` không thể `None`.
- Viewer ra lệnh được: bác. Cả hai route dùng `require_admin` (`robot.py:120`, `batches.py:219`), có test viewer.

## 3. Số đếm nền (dev DB, 2026-11-23)

- `sap_job`: `read_zrsd001` 21 Xong và 1 Lỗi; `read_zrsd004` 23 Xong và 2 Lỗi; `read_zrsd003` 2 Xong; `check_connection` 4 Xong và 1 Lỗi.
- Việc đang mở trùng `dedupe_key`: 0.
- Việc `read_zrsd004` Xong với kết quả "chưa có DO": 1.
- Lô đã xác nhận: 16; `import_batch` loại `zrsd001`: 23.
- Đơn của lô đã xác nhận mà chưa có SO: 1, trạng thái `CANCELLED` (không phải sót).

## 4. Tổng kết

0 Critical, 0 High, 2 Medium, 5 Low. Không có đường làm trùng dữ liệu; rủi ro sót duy nhất là phát hiện 2 (cửa sổ một ngày của `zrsd001`).
