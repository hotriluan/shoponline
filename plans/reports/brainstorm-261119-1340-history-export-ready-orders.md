# Brainstorm: cho tải file Shop Online khi còn đơn bị chặn

Ngày: 2026-11-19. Liên quan plan [261119-0605-zrsd003-tax-invoice-in-history](../261119-0605-zrsd003-tax-invoice-in-history/plan.md).

## Hiện trạng (đã kiểm trong code)

- `collect_rows` (`src/shoponline/exports/sales_history_workbook.py`) đã tách đơn theo từng đơn: đơn đủ dữ liệu vào `rows`/`order_ids`, đơn thiếu vào `blocked`. Một đơn bị chặn không làm hỏng dòng của đơn khác (test `test_blocked_order_does_not_hold_back_the_others`).
- Cổng chặn tất cả chỉ nằm ở hai chỗ: `download_history_file` trả về lỗi "Còn N đơn bị chặn" khi `result.blocked` khác rỗng (`src/shoponline/web/routes/sales_history.py:150`), và template `sales_history.html` ẩn nút **Tải file** khi còn đơn bị chặn.
- Trước khi có hóa đơn, đơn bị chặn là lỗi dữ liệu hiếm (thiếu tên, tỉnh, tên báo cáo). Từ khi có cột 19, đơn chờ hóa đơn là **trạng thái bình thường mỗi ngày**: đơn nào mới có DO hôm nay đều chưa có hóa đơn. Vì vậy cổng "tất cả hoặc không" gần như luôn đóng.
- Sổ đơn đã xuất đã chấp nhận dán không theo thứ tự ngày: đơn đặt từ tháng trước mà DO đến muộn vẫn vào file sau (`docs/daily-operations.md`, bước 2). Cột `Transaction` so sánh với dòng ngay trên, mà các dòng của một đơn luôn liền nhau, nên dán đơn muộn ở file sau không làm sai công thức.

## Hợp đồng

- **Kết quả:** trên trang File Shop Online, khi còn đơn bị chặn vẫn tải được file chứa các đơn đã đủ dữ liệu (có hóa đơn). Đơn bị chặn vẫn được liệt kê kèm lý do, không có trong file và sẽ vào một file sau khi đủ dữ liệu.
- **Ràng buộc:** giữ quy tắc "chặn chứ không đoán": không xuất dòng thiếu giá trị. Sổ `sales_history_file_order` / `sales_history_exported` giữ nguyên ý nghĩa: file chỉ ghi các đơn thật sự có trong nó. Không cần migration.
- **Ngoài phạm vi:** thay đổi cột, cách tính giá trị, robot zrsd003, luồng xác nhận/gỡ xác nhận.
- **Tiêu chí hoàn thành:**
  1. Có 1 đơn đủ dữ liệu và 1 đơn chờ hóa đơn: trang hiện nút tải kèm câu "1 đơn bị chặn chưa có trong file"; file tải về chỉ có dòng của đơn đủ dữ liệu, và `sales_history_file_order` chỉ ghi đơn đó.
  2. Sau khi đơn chờ có hóa đơn, lần tải sau chỉ chứa đơn đó (nếu file trước đã được xác nhận).
  3. Không có đơn nào đủ dữ liệu thì vẫn báo "Không có đơn nào chờ xuất" như hiện nay.
  4. Test web cũ đang khẳng định "còn đơn bị chặn thì không tải được" được sửa thành hành vi mới; `uv run pytest` và `uv run ruff check` thoát mã 0.
  5. `docs/daily-operations.md`, mục "Xuất dòng cho file Shop Online", bỏ câu "Còn đơn bị chặn thì không tải được file" và ghi hành vi mới.

## Các phương án

**A. Tải các đơn đã sẵn sàng (đề xuất).** Bỏ cổng ở route và template; file chứa `result.rows` như hiện tại, ghi đúng `result.order_ids`. Trang ghi rõ số đơn bị chặn bị để lại.
- Giả định chính: kế toán chấp nhận một đơn có thể vào file lịch sử muộn hơn các đơn đặt sau nó. Code và tài liệu hiện có đã chấp nhận điều này cho DO đến muộn.
- Hỏng đầu tiên khi: kế toán chốt tháng mà không nhìn danh sách bị chặn, tưởng file đã đủ tháng. Giảm rủi ro bằng câu cảnh báo cạnh nút tải và trong tên thông báo.
- Công sửa: khoảng 10 dòng route + template, 1–2 test, 1 đoạn tài liệu.

**B. Bản nháp để kiểm tra.** Thêm nút "Tải bản nháp": file gồm mọi đơn, ô thiếu để trống, thêm cột lý do chặn, tên file có chữ NHÁP; không lưu vào `generated_file` nên không xác nhận được.
- Giả định chính: người dùng chỉ cần xem, còn việc dán thật vẫn đợi mọi đơn đủ dữ liệu.
- Hỏng đầu tiên khi: ngày nào cũng có đơn chờ hóa đơn, nên file thật vẫn bị chặn gần như mỗi ngày; B chỉ cho xem, không gỡ được việc kẹt. Ngoài ra bản nháp có ô trống nên có nguy cơ bị dán nhầm vào file lịch sử.
- Công sửa: lớn hơn A (dòng có giá trị rỗng, cột 20, đường tải riêng, test riêng).

**C. Chỉ nới riêng lý do hóa đơn.** Đơn chờ hóa đơn được để lại; còn lỗi dữ liệu (thiếu tên, tỉnh, tên báo cáo) vẫn chặn cả file.
- Giả định chính: lỗi dữ liệu phải sửa ngay chứ không được để sang file sau.
- Hỏng đầu tiên khi: tên khách bị xóa sau 90 ngày theo retention, khiến một đơn cũ chặn mãi cả file. Hai loại quy tắc cũng khó giải thích hơn.

## Trade-offs

A đổi cổng "cả file đúng hết" lấy "mỗi đơn đúng hết". Độ chính xác từng dòng không đổi; thứ bị mất là cam kết "file đã tải là đầy đủ tới ngày chọn". Cam kết này thực tế không còn giữ được từ khi có cột hóa đơn. B giữ nguyên cam kết đó nhưng việc dán thật vẫn kẹt. C nằm giữa nhưng thêm một loại quy tắc mà không có bằng chứng cần đến.

## Better approaches

A tốt hơn ý "bản nháp" mà người dùng nêu: bằng chứng là `collect_rows` vốn đã cô lập từng đơn và sổ đơn đã xuất vốn đã chấp nhận đơn đến muộn. Vì vậy A vừa cho xem các đơn có hóa đơn, vừa gỡ việc kẹt hằng ngày, với chi phí nhỏ hơn B. Nếu sau này vẫn cần bản nháp, có thể làm B riêng trên nền A mà không phải sửa lại gì.

## Quyết định đã chốt (2026-11-19, chủ dự án)

1. Chọn A cho **mọi** lý do chặn, không chỉ đơn chờ hóa đơn.
2. Sheet1 không bắt buộc phải xếp theo ngày đặt, vì kế toán có thể tự sắp xếp trong Excel. Nếu có cách giúp sắp xếp dễ thì tốt hơn.

## Sắp xếp theo ngày trong file lịch sử

Đã kiểm `docs/Shop Online 2022-2026_10.xlsx`, sheet1:

- Có 3.010 dòng dữ liệu. Toàn bộ cột `createTime` là **text** dạng `YYYY-MM-DD HH:MM`, định dạng ô `@`. Dạng này khi sắp xếp như text cho ra đúng thứ tự thời gian.
- Sheet hiện cũng không xếp theo ngày: có 338 chỗ dòng sau có ngày nhỏ hơn dòng trước, có thể vì dán theo từng sàn. Như vậy dán đơn đến muộn không làm tình hình khác đi.
- Có 17 dòng cũ do người gõ tay sai dạng (`2025-12-24 16:2`, `2025-01-2014:07`, `27 Mar 2026 10:19`, …). Những dòng này sẽ đứng sai chỗ khi sắp xếp. Đây là dữ liệu cũ của kế toán, hệ thống không sửa.

File tải về đã ghi `createTime` dạng text `YYYY-MM-DD HH:MM` giống hệt, và các dòng đã xếp theo ngày đặt, mã đơn, số dòng. Vì vậy **không cần sửa code để hỗ trợ sắp xếp**. Chỉ cần thêm vào tài liệu cách sắp xếp an toàn:

- Sắp xếp toàn vùng dữ liệu của sheet1 (từ dòng 2) theo **createTime** (B), khóa phụ **Cust + time** (H). Khóa phụ giữ các dòng của cùng một đơn đứng liền nhau khi hai đơn trùng phút đặt.
- `Cust + time` và `Transaction` là công thức tương đối, nên sau khi sắp xếp, `Transaction` tự so với dòng mới ngay trên. Dòng đầu của mỗi đơn vẫn ra 1, các dòng sau ra 0.

Đã cân nhắc nhưng không chọn: ghi `createTime` thành giá trị ngày giờ thật của Excel. Cách này làm cột bị lẫn kiểu với 3.010 dòng text cũ, và khi sắp xếp Excel sẽ tách số với text thành hai nhóm riêng, tức là tệ hơn hiện tại.

## Hướng chọn và bàn giao

Làm A thành phase 6 của plan 261119-0605. Phạm vi:

1. Bỏ cổng chặn trong `download_history_file` và nút **Tải file** trong `sales_history.html`. Khi còn đơn bị chặn, hiện câu "N đơn bị chặn chưa có trong file này".
2. Sửa test web về cổng chặn; thêm test cho tiêu chí 1–3 ở trên.
3. `docs/daily-operations.md`: sửa bước 3–4 theo hành vi mới, và thêm cách sắp xếp sheet1 nêu trên.

Không cần migration, cũng không đụng tới robot hay luồng xác nhận.
