# Sổ tay vận hành: xử lý sự cố

Dành cho admin shop online và người quản trị hệ thống, không cần biết lập trình. Việc hằng ngày: [daily-operations.md](daily-operations.md). Chi tiết robot: [robot-runbook.md](robot-runbook.md).

Mỗi mục có ba phần: **dấu hiệu**, **việc cần làm**, và **gọi lập trình viên khi**. Nguyên tắc chung: khi chưa rõ thì dừng robot và làm bằng tay. Hệ thống không ghi gì vào SAP, nên làm tay luôn an toàn.

## Robot

### Robot dừng hoặc không nhận việc

- **Dấu hiệu:** trang **Robot SAP** có việc "Chờ" lâu mà không chạy; không có dòng cảnh báo robot tạm dừng.
- **Việc cần làm:**
  1. Trên máy robot, kiểm tra tài khoản `saprobot` đang đăng nhập và màn hình không bị khóa.
  2. Task Scheduler → `shoponline-robot` → **Run**. Nếu tác vụ báo đang chạy mà không nhận việc, **End** rồi **Run** lại.
  3. Trong lúc chờ, tải file báo cáo lên bằng tay (mục [Tải báo cáo tay](#tải-báo-cáo-sap-bằng-tay-khi-robot-dừng)).
- **Gọi lập trình viên khi:** robot khởi động rồi tắt ngay. Gửi kèm 50 dòng cuối của `<SHOPONLINE_DATA_DIR>\logs\robot.log`.

### Robot tự tạm dừng vì T-code ngoài danh sách

- **Dấu hiệu:** dòng cảnh báo trên mọi trang; lỗi của việc bắt đầu bằng "Lớp chặn T-code".
- **Việc cần làm:** làm đúng ba bước trong [robot-runbook.md, mục Lớp chặn T-code](robot-runbook.md#lớp-chặn-t-code). Nếu SAP trên máy robot còn đứng ở màn hình lạ (ví dụ `VA02`), thoát **không lưu**.
- **Gọi lập trình viên khi:** luôn gọi, trước khi bật lại robot. Đây là dấu hiệu màn hình SAP đã đổi hoặc mã robot có lỗi.

### Robot tự tạm dừng vì lỗi liên tiếp hoặc sai hệ thống

- **Dấu hiệu:** cảnh báo robot tạm dừng; nhiều việc "Lỗi" liền nhau, hoặc lỗi nêu hệ thống, client, user không khớp.
- **Việc cần làm:** xem lỗi và ảnh của từng việc. Lỗi do SAP bảo trì, mất mạng hoặc phiên SAP của người khác đang mở trên máy robot thì sửa nguyên nhân, bấm **Bật lại robot**, rồi **Chạy lại** từng việc.
- **Gọi lập trình viên khi:** lỗi lặp lại sau khi bật lại, hoặc không hiểu lỗi.

### Cửa sổ lạ, việc ở "Cần kiểm tra"

- **Dấu hiệu:** việc ở trạng thái "Cần kiểm tra"; robot không bấm gì trên cửa sổ đó.
- **Việc cần làm:** mở ảnh của việc. Đóng cửa sổ đó bằng tay trên máy robot (chọn Cancel hoặc No nếu có). Tải báo cáo lên bằng tay cho lần này.
- **Gọi lập trình viên khi:** cùng cửa sổ hiện lại. Lập trình viên quyết định có thêm nó vào `config/sap_popups.yaml` hay không; không tự sửa file này.

### Phiên SAP bị đăng xuất

- **Dấu hiệu:** lỗi nêu mất phiên hoặc không đăng nhập được.
- **Việc cần làm:** robot tự đăng nhập lại ở việc kế tiếp, nên chỉ cần bấm **Chạy lại**. Nếu đăng nhập lại cũng lỗi, kiểm tra mật khẩu `AL17016` còn đúng (xem [security-and-data-retention.md](security-and-data-retention.md#user-sap-của-robot)) và SAP không bảo trì.
- **Gọi lập trình viên khi:** đăng nhập tay bằng `AL17016` được mà robot vẫn lỗi.

### Tải báo cáo SAP bằng tay khi robot dừng

Làm như bước 8 và 10 của [daily-operations.md](daily-operations.md): chạy `zrsd001` (Complete) hoặc `zrsd004` trong SAP bằng user của mình, xuất Excel, tải lên trang **Báo cáo SAP**. Kết quả giống hệt khi robot đọc.

## Đơn và file

### Đơn thiếu ánh xạ

- **Dấu hiệu:** kết quả tải file sàn báo đơn **Thiếu ánh xạ**.
- **Việc cần làm:** trang **Ánh xạ SAP**, điền mã SAP và tên SAP (bước 2 của [daily-operations.md](daily-operations.md)). Đơn tự chuyển **Sẵn sàng**.
- **Gọi lập trình viên khi:** đã điền ánh xạ mà đơn vẫn không chuyển.

### Sales admin gõ sai mã đơn vào `PO No`

- **Dấu hiệu:** phần **Đối chiếu SO** trên trang lô có dòng "SO có PO No không khớp đơn nào".
- **Việc cần làm:** chọn đúng đơn ở cột **Nối với đơn**, bấm **Nối**. Không cần sửa SO trong SAP; file gửi kế toán dùng mã đơn đã nối.
- **Gọi lập trình viên khi:** không tìm được đơn nào để nối.

### Đơn hủy sau khi đã có SO hoặc DO

- **Dấu hiệu:** khách hủy sau khi sales admin đã tạo SO.
- **Việc cần làm:**
  1. Sales admin hủy SO hoặc DO trong SAP như hiện nay.
  2. Đơn ở "Đã có SO": mở đơn, bấm **Đánh dấu hủy**.
  3. DO đã hủy thì không còn trong `zrsd004`, nên đơn tự rơi khỏi file gửi kế toán.
  4. Đơn đã ở "Đã có DO" (đã có trong `zrsd004`) thì web không cho hủy. Báo kế toán bằng tay.
- **Gọi lập trình viên khi:** đơn đã hủy vẫn xuất hiện trong file gửi kế toán.

### Sàn đổi mẫu file

- **Dấu hiệu:** file sàn bị từ chối, thông báo nêu cột thiếu.
- **Việc cần làm:** không sửa tay file sàn. Làm file `ĐƠN HÀNG ONLINE` bằng tay cho ngày đó.
- **Gọi lập trình viên khi:** luôn gọi. Gửi kèm file bị từ chối (qua kênh nội bộ, không qua email ngoài vì file có tên khách).

### File gửi kế toán báo "đã quá thời hạn lưu"

- **Dấu hiệu:** tải lại file kế toán của một ngày cũ thì web báo file `zrsd004` đã bị xóa theo thời hạn lưu.
- **Việc cần làm:** chạy lại `zrsd004` cho ngày đó trong SAP và tải lên. Tên và địa chỉ khách của đơn cũ đã bị xóa, nên ba cột thêm sẽ trống. Hỏi kế toán dùng bản đã gửi trước đó.

## Máy và dữ liệu

### Web không mở được hoặc máy chạy thật dừng

- **Việc cần làm:** admin quay lại làm Excel bằng tay như trước khi có hệ thống. Người quản trị kiểm tra máy còn bật và tác vụ `shoponline-web` đang chạy; nếu máy hỏng, xem [Kế hoạch khi máy hỏng](#kế-hoạch-khi-máy-hỏng).
- **Gọi lập trình viên khi:** máy chạy mà web không lên. Gửi kèm kết quả của Task Scheduler → `shoponline-web` → History.

### Cảnh báo sao lưu màu cam

- **Dấu hiệu:** dòng cam trên web: bản sao lưu gần nhất đã quá 36 giờ.
- **Việc cần làm:** Task Scheduler → `shoponline-backup` → **Run**. Kiểm tra ổ mạng công ty và thư mục Google Drive còn truy cập được.
- **Gọi lập trình viên khi:** chạy tay vẫn lỗi.

### Xem danh sách xóa theo thời hạn

Tác vụ `shoponline-retention` chạy hằng đêm và ghi vào `<SHOPONLINE_DATA_DIR>\logs\retention.log`. Trong tuần đầu nó chỉ liệt kê. Người quản trị đọc danh sách: chỉ được có đơn đã gửi kế toán (hoặc đã hủy) và file quá 90 ngày. Sau một tuần không thấy sai, đăng ký lại tác vụ với `-RetentionApply` (xem [security-and-data-retention.md](security-and-data-retention.md#thời-hạn-lưu)).

## Kế hoạch khi máy hỏng

Chủ dự án chốt các ô còn trống trước khi bàn giao.

| Câu hỏi | Trả lời |
|---|---|
| Máy thay thế lấy ở đâu | _(chờ chủ dự án)_ |
| Ai dựng lại máy | _(chờ chủ dự án)_ |
| Thời gian dựng lại chấp nhận được | _(chờ diễn tập)_ |
| Trong lúc chờ | Admin làm Excel tay; sales admin làm SO, DO như cũ |

Các bước dựng lại: [deployment-guide.md](deployment-guide.md), mục "Khi máy hỏng".

## Biên bản diễn tập

| Ngày | Tình huống | Người làm | Kết quả | Chỗ sổ tay phải sửa |
|---|---|---|---|---|
| | Dựng lại máy từ ổ mạng công ty | | | |
| | Dựng lại máy từ Google Drive | | | |
| | Tắt robot giữa lượt | | | |
| | Rút mạng khi robot đang đọc báo cáo | | | |
| | Tải lên file sàn thiếu cột | | | |
