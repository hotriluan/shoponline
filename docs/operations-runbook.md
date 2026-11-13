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

Làm như bước 8 của [daily-operations.md](daily-operations.md) cho `zrsd001`: chạy `zrsd001` (Complete) trong SAP bằng user của mình, xuất Excel, tải lên trang **Báo cáo SAP**. Với `zrsd004`, tải file lên ngay trang đợt ở **Gửi kế toán**. Kết quả giống hệt khi robot đọc.

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

### Gửi kế toán: một sàn đọc lỗi

- **Dấu hiệu:** trang đợt (**Gửi kế toán**) có lượt báo **Lỗi**, **Thiếu file nguồn** hoặc **Chưa có việc**.
- **Việc cần làm:** bấm **Đọc lại** (việc lỗi vào hàng chờ lại; việc đã xong được thay bằng việc mới). Robot không chạy được thì xuất `zrsd004` tay từ SAP và dùng ô **Tải zrsd004 lên đợt**. Không có cách nào thì tích "Chốt thiếu" khi chốt: DO của lượt đó **không** vào file và **không** vào sổ, nên đợt sau đọc lại và gửi nốt.
- **Gọi lập trình viên khi:** lượt lỗi lặp lại sau khi đã đọc lại hai lần.

### Gửi kế toán: đơn nằm ở khung "Chưa thấy DO"

- **Dấu hiệu:** phần Đối chiếu liệt kê đơn đã có SO mà chưa thấy DO trong file.
- **Việc cần làm:** kiểm tra trong SAP xem sales admin đã tạo DO và goods issue chưa (DO phải có `Actual GI Date` và trạng thái `C`). Chưa xong thì chốt không có đơn đó: tích "Tôi đã xem danh sách đơn chưa có DO"; đơn sẽ vào đợt sau. Danh sách được ghi vào nhật ký sự kiện lúc chốt.

### Gửi kế toán: đợt mở bị bỏ quên

- **Dấu hiệu:** bấm "Xuất file gửi kế toán" thì mở lại một đợt cũ. Chỉ có một đợt mở tại một thời điểm.
- **Việc cần làm:** mở đợt đó rồi chốt, hoặc bấm **Hủy đợt** (sổ không đổi) và bắt đầu lại. Việc robot đã xếp cho đợt bị hủy vẫn chạy và nhập dữ liệu bình thường.

### Chốt nhầm một đợt gửi kế toán

- **Dấu hiệu:** đã chốt đợt nhưng file không đúng (thiếu sàn, chốt sớm).
- **Việc cần làm:** báo kế toán **không dùng** file đó. Trên máy chạy web, xem trước rồi gỡ:

  ```powershell
  uv run shoponline accounting-run revoke <số đợt>          # chỉ in số DO sẽ gỡ
  uv run shoponline accounting-run revoke <số đợt> --yes   # gỡ thật, ghi sự kiện accounting_run_revoked
  ```

  Chỉ đợt `FINALIZED` gỡ được. Các DO của đợt ra khỏi sổ và các lượt đọc của đợt quay lại danh sách cần đọc; file đã lưu giữ nguyên. Không sửa bằng SQL.

### Sổ DO đã gửi và mốc ngày

- Mốc ngày: DO có ngày goods issue thực không sau mốc coi như đã gửi. Mặc định là ngày chạy migration. Xem hoặc đổi: `uv run shoponline accounting-ledger cutoff [--set YYYY-MM-DD]`.
- Sổ nền (DO của các đơn đã "Đã có DO" lúc triển khai): `accounting-ledger list` để xem; `accounting-ledger add <DO>...` thêm DO đã gửi mà chưa có trong sổ; `accounting-ledger remove <DO>...` gỡ DO chưa thật sự gửi. DO thuộc một đợt đã chốt không gỡ riêng được, dùng `accounting-run revoke`.

### DO bị hủy sau khi đã chốt

- Hệ thống không phát hiện DO bị hủy sau khi đã chốt. Báo kế toán bằng tay.

### File đã chốt không còn trên máy chủ

- **Dấu hiệu:** tải file đã chốt báo "không còn trên máy chủ".
- **Việc cần làm:** retention không xóa file đã chốt, nên đây là file bị xóa hoặc mất ngoài hệ thống. Khôi phục từ bản sao lưu (thư mục `exports`). Không có bản sao thì hỏi kế toán dùng bản đã gửi; không chốt lại.

## Máy và dữ liệu

### Web không mở được hoặc máy chạy thật dừng

- **Việc cần làm:** admin quay lại làm Excel bằng tay như trước khi có hệ thống. Người quản trị kiểm tra máy còn bật và tác vụ `shoponline-web` đang chạy; nếu máy hỏng, xem [Kế hoạch khi máy hỏng](#kế-hoạch-khi-máy-hỏng).
- **Gọi lập trình viên khi:** máy chạy mà web không lên. Gửi kèm kết quả của Task Scheduler → `shoponline-web` → History.

### Cảnh báo sao lưu màu cam

- **Dấu hiệu:** dòng cam trên web: bản sao lưu gần nhất đã quá 36 giờ.
- **Việc cần làm:** Task Scheduler → `shoponline-backup` → **Run**. Kiểm tra ổ mạng công ty và thư mục Google Drive còn truy cập được.
- **Gọi lập trình viên khi:** chạy tay vẫn lỗi.

### Xem danh sách xóa theo thời hạn

Tác vụ `shoponline-retention` chạy hằng đêm và ghi vào `<SHOPONLINE_DATA_DIR>\logs\retention.log`. Trong tuần đầu nó chỉ liệt kê. Người quản trị đọc danh sách: chỉ được có đơn đã vào sổ gửi kế toán (hoặc đã hủy) và file quá 90 ngày. Sau một tuần không thấy sai, đăng ký lại tác vụ với `-RetentionApply` (xem [security-and-data-retention.md](security-and-data-retention.md#thời-hạn-lưu)).

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
