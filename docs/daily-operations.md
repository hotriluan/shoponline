# Vận hành hằng ngày (chế độ thủ công)

Dành cho admin shop online. Ở chế độ thủ công hệ thống không ghi gì vào SAP; sales admin vẫn tạo SO và DO như hiện nay.

## Trong ngày D

1. **Tải file sàn.** Trang **Tải file sàn**: chọn sàn (Shopee, TikTok hoặc Lazada), ngày xử lý D, chọn file "chờ giao hàng" tải từ trang quản lý sàn. Tải nhiều file trong một ngày được; đơn đã có không bị nhân đôi. Đơn có nhiều sản phẩm được gom thành một đơn: cùng một số ở cột `Đơn Hàng` trong file `ĐƠN HÀNG ONLINE`, nên sales admin tạo một SO và kế toán xuất một hóa đơn cho cả đơn. Lazada gom theo cột `orderNumber` (không phải `orderItemId`, là mã của từng sản phẩm).
2. **Xử lý đơn lỗi.** Nếu kết quả báo đơn **Thiếu ánh xạ**, vào **Ánh xạ SAP**, điền mã SAP và tên SAP cho các sản phẩm còn thiếu. Dòng nào đủ hai ô thì tự lưu khi chuyển sang ô khác; nút **Lưu tất cả** lưu lại mọi dòng đã điền (dòng để trống được bỏ qua). Nhiều dòng thì bấm **tải danh sách này ra Excel**, điền cột Mã SAP và Tên SAP, rồi nhập lại ở mục **Nhập từ Excel**. Đơn tự chuyển sang **Sẵn sàng**. Đơn **Cần kiểm tra** (ví dụ trợ giá TikTok không chia đều cho số lượng): mở đơn, kiểm tra tay, bấm **Đã kiểm tra, cho đi tiếp**.
3. **Kiểm tra ngày goods issue.** Màn hình lô đề xuất ngày làm việc kế tiếp (cuối tháng thì giữ ngày D). Gặp ngày lễ thì đổi ngày; ngày tự lưu và trang tải lại.
4. **Tải file `ĐƠN HÀNG ONLINE`** trên màn hình lô và gửi sales admin. File chỉ gồm đơn **Sẵn sàng**; đơn không giảm giá đứng trước, đơn có giảm giá đứng sau, cột `Sale` ghi trợ giá cho một sản phẩm. Sales admin phải tạo SO không giảm giá trước.
5. **Nhập tên khách.** Bấm **Nhập tên khách** trên màn hình lô, chép tên từ phiếu giao hàng. Địa chỉ đã điền sẵn từ file sàn; sửa nếu cần. Mỗi dòng tự lưu khi chuyển sang ô khác, kết quả hiện ở cột cuối; dòng lưu lỗi hiện chữ đỏ và trình duyệt hỏi lại trước khi rời trang. Đơn Lazada đã có sẵn tên (cột `billingName`) và địa chỉ đầy đủ (cột `billingAddr`) từ file; chỉ kiểm tra lại. Tên, địa chỉ đã sửa tay không bị nhập lại file ghi đè.
6. **Hủy đơn.** Đơn khách hủy trước khi làm SO: mở đơn, bấm **Đánh dấu hủy**. Việc hủy SO hoặc DO trong SAP vẫn do người làm.

## Sau khi sales admin tạo SO và DO

7. Trên màn hình lô bấm **Sales admin đã tạo SO và DO**.
8. Chạy `zrsd001` trong SAP với lựa chọn **Complete**, lọc đúng ngày D, xuất Excel. Trang **Báo cáo SAP**, mục zrsd001: chọn lô vừa xác nhận rồi tải file lên. Nếu file không có SO nào của sàn trong ngày D, hệ thống báo để kiểm tra lại bộ lọc. Khi robot đang bật, robot đọc `zrsd001` thay bạn ngay sau khi xác nhận lô; nếu sales admin tạo thêm SO sau đó, bấm **Đọc lại zrsd001** trên trang lô. Tải file bằng tay vẫn là đường dự phòng.
9. Đọc phần **Đối chiếu SO** trên màn hình lô:
   - **Đơn sẵn sàng chưa có SO**: sales admin còn sót đơn.
   - **SO có PO No không khớp đơn nào**: thường do gõ sai mã đơn vào `PO No`. Chọn đúng đơn ở cột **Nối với đơn** rồi bấm **Nối**.
   - **Một mã đơn có nhiều SO**: báo sales admin hủy SO thừa trong SAP.
   - **SO khác file sàn**: giá trị hoặc mã vật tư, số lượng khác file sàn; kiểm tra SO trong SAP.

## Ngày goods issue

10. Vào trang **Gửi kế toán**, bấm **Xuất file gửi kế toán** (nút này cũng có trên trang lô). Hệ thống mở một đợt và xếp việc cho robot đọc `zrsd004` cho từng sàn và từng ngày goods issue còn đơn chờ, từ ngày cũ nhất của đơn chờ đến hôm nay. Robot không chạy thì xuất `zrsd004` tay từ SAP và tải lên ngay trên trang đợt.
11. Theo dõi bảng tiến độ (tự làm mới 10 giây một lần khi còn lượt đang đọc). Lượt báo **Lỗi** hoặc **SAP chưa có DO** có nút **Đọc lại**. "SAP chưa có DO" là kết quả hợp lệ (ngày đó chưa có giao hàng), không phải lỗi.
12. Khi không còn lượt nào đang đọc, phần **Đối chiếu** hiện:
    - dòng tóm tắt, ví dụ "Web đáng ra có 15 đơn, file có 14 DO, thiếu 1";
    - khung **Chưa thấy DO**: đơn đã có SO mà chưa thấy DO trong file;
    - khung **DO không thuộc đơn nào trên web** (ví dụ SO sales admin tạo tay);
    - số dòng không vào file theo từng lý do, và các dòng còn thiếu mã đơn, tên khách hoặc địa chỉ (bổ sung ở trang **Khách hàng** rồi tải lại trang).

    Nút **Tải bản nháp** cho file có tiền tố `NHÁP`, không ghi sổ.
13. Bấm **Chốt và ghi sổ**. Nếu còn lượt chưa có dữ liệu thì phải tích "Chốt thiếu"; nếu còn đơn chưa thấy DO thì phải tích "Tôi đã xem danh sách đơn chưa có DO". Nếu dữ liệu đổi sau khi xem bản nháp (robot đọc xong thêm, có file mới gắn vào) thì web từ chối và bảo xem lại. Chốt xong, trang đợt có link tải đúng file đã chốt.
14. Gửi `SHOP ONLINE ddmmyy.xlsx` cho kế toán. File gộp DO của mọi sàn và mọi ngày goods issue chưa gửi, giữ nguyên mọi cột của `zrsd004`, tính lại hai dòng tổng theo quy tắc của SAP và chèn ba cột `mã đơn hàng`, `tên khách hàng`, `địa chỉ` ngay sau `SO Reference`. DO đã chốt không bao giờ vào file sau. Đơn đã hủy DO không còn trong `zrsd004` nên không có trong file.

Đợt không muốn chốt nữa thì bấm **Hủy đợt** (sổ không đổi). Chốt nhầm thì xem [operations-runbook.md](operations-runbook.md#chốt-nhầm-một-đợt-gửi-kế-toán).

## Xuất dòng cho file Shop Online

File lịch sử của kế toán `Shop Online 2022-2026` (sheet1, 17 cột; file tải về thêm cột 18 `Mã đơn` sau `variation` để đối chiếu đơn, cột 19 `Tax Invoice Doc.` là số hóa đơn của DO, lấy từ `zrsd003`, và cột 20 `Tiền Vô` là số tiền sàn đã trả cho đơn, lấy từ file quyết toán Shopee/TikTok) nhận một dòng cho mỗi sản phẩm của mỗi đơn **Đã có DO**. Web dựng sẵn các dòng đó; không cần gõ tay.

1. **Lần đầu, và khi có mã vật tư mới:** vào **Tên báo cáo**. Mã chưa lưu đứng đầu và có giá trị gợi ý (itemName, kích cỡ, variation) lấy từ tên sản phẩm trên sàn; sửa theo cách file lịch sử vẫn ghi (ví dụ `Propan - ULTRAN VERNIS - V-09 - Sơn Dầu Bóng Màu` / `0.8 lít` / `Màu sắc:2004 Cánh gián`) rồi bấm **Lưu tất cả**. Dòng điền thiếu ô làm cả lần lưu bị từ chối; giá trị đã gõ vẫn còn.
2. Vào **File Shop Online**. Ô **Tháng đặt hàng** mặc định là tháng trước, vì file của một tháng làm vào đầu tháng sau (ví dụ tháng 10/2026 làm khoảng 10/11/2026); muốn xem hay xuất nháp đơn tháng này thì chọn tháng này. Trang lấy mọi đơn Đã có DO chưa được xác nhận, đặt tới hết ngày cuối tháng chọn, kể cả đơn đặt từ các tháng trước mà giờ mới đủ dữ liệu; đơn của tháng sau không vào.
3. **Đơn bị chặn** (thiếu tên khách, địa chỉ không ra tỉnh/thành, mã vật tư chưa có tên báo cáo, DO chưa có Tax Invoice Doc.; Shopee/TikTok chưa có tiền vô thì nằm ở mục riêng, xem dưới): bấm vào lý do để sang trang sửa (**Khách hàng** của lô, hoặc **Tên báo cáo**), rồi mở lại trang. Đơn bị chặn không làm chặn cả file: file chỉ chứa các đơn đã đủ dữ liệu, còn đơn bị chặn ở lại chờ và vào lần tải sau khi đủ dữ liệu. Khi chốt tháng, xem bảng **Đơn bị chặn** để biết đơn nào chưa có trong file.
   - **Chờ hóa đơn:** hóa đơn xuất sau DO, nên đơn mới có DO mà chưa có hóa đơn là bình thường. Khi SAP đã xuất hóa đơn, bấm **Robot đọc zrsd003** trong ô hóa đơn trên trang: robot đọc `zrsd003` (Sales Organization `1000`, Sales Office `1401`) với ngày hóa đơn từ ngày 1 của tháng chọn (hoặc ngày đặt của đơn chờ cũ hơn, nếu còn) đến hôm nay, rồi mở lại trang khi việc **Xong**. Khoảng đọc kết thúc ở hôm nay chứ không ở cuối tháng, vì hóa đơn của đơn đặt cuối tháng ra trong tháng sau. Khi không còn đơn nào tới hết tháng chọn chờ hóa đơn, ô này ghi "không cần đọc zrsd003" thay cho nút. Cần khoảng ngày khác thì dùng form "Ra lệnh cho robot" trên trang **Robot SAP**, nơi vẫn chọn tự do từ ngày đến ngày. Robot không chạy thì xuất `zrsd003` tay từ SAP với cùng bộ lọc và tải lên ở trang **Báo cáo SAP**, mục zrsd003. Cả hai đường chỉ giữ hóa đơn của khách SAP các sàn và xóa file gốc ngay sau khi nhập.
   - **Chờ tiền vô (Shopee, TikTok):** sàn quyết toán vài ngày sau khi giao, nên đơn mới giao chưa có tiền vô là bình thường. Các đơn này không vào file mà nằm ở hộp **Đơn chờ tiền vô**, kèm khoảng ngày đặt cần export từ sàn (đơn đang bị chặn vì lý do khác cũng được tính). Export file quyết toán của sàn phủ khoảng đó rồi tải lên ngay trong hộp (chỉ admin): Shopee: Số dư TK Shopee → Báo cáo giao dịch (sheet `Transaction Report`); TikTok: Tài chính → quyết toán (sheet `Chi tiết đơn hàng`). Đơn tự vào lần tải sau. Tải lại file trùng kỳ hay chồng kỳ không cộng trùng. File Lazada Balance Transactions không có mã đơn nên không dùng được; đơn Lazada không chờ và cột `Tiền Vô` để trống. File quyết toán bị xóa ngay sau khi nhập; chỉ giữ mã đơn, số tiền và ngày.
   - **Đọc cột `Tiền Vô`:** chỉ dòng đầu của mỗi đơn có số, là tổng các giao dịch của đơn. Số `0` là đơn hoàn tiền toàn bộ (TikTok); số âm là đơn giao không thành công hoặc hoàn tiền kèm phí. Shopee dòng "Điều chỉnh" không theo đơn bị bỏ qua. TikTok dòng loại khác "Đơn hàng" bị bỏ qua và thông báo liệt kê ID giao dịch và đơn liên quan để xử lý tay. Tiền vô đổi sau khi đơn đã xuất (sàn ghi "Tiền ra" muộn) không được cập nhật vào file đã xuất. Đơn không bao giờ được quyết toán ở lại hộp chờ cùng thông tin khách cho tới khi xử lý tay.
4. Bấm **Tải file** (`SHOP ONLINE LỊCH SỬ ddmmyy.xlsx`). Tài khoản xem cũng tải được.
   - **Tải file nháp** (`NHÁP SHOP ONLINE LỊCH SỬ ddmmyy.xlsx`) để kiểm tra trước khi chốt tháng. Nháp gồm đơn đủ dữ liệu và đơn chỉ còn chờ hóa đơn hoặc tiền vô; ô `Tax Invoice Doc.` hoặc `Tiền Vô` còn thiếu để trống, và cột 21 `Trạng thái` ghi đơn đang chờ gì (`Chờ hóa đơn`, `Chờ tiền vô`, hoặc cả hai). Đơn bị chặn vì lý do khác không có trong nháp. Nháp không được lưu, không có trong bảng **File đã tải**, không xác nhận được, và không được dán vào file lịch sử.
5. Mở file lịch sử, copy từ **dòng 2** của file vừa tải và dán vào dòng trống đầu tiên của sheet1. Nếu sheet1 chưa có tiêu đề cột T, thêm tay `Tiền Vô` một lần. Hai cột `Cust + time` và `Transaction` là công thức tương đối nên tự tính theo dòng mới.
   - **Sắp xếp theo ngày đặt (tùy chọn):** đơn đến muộn (DO hoặc hóa đơn muộn) được dán sau các đơn đặt sau nó. Muốn xếp lại thì chọn toàn bộ dữ liệu sheet1 từ dòng 2, cột A đến **T** (không chỉ A:S, kẻo cột `Tiền Vô` lệch hàng), **Sort** theo cột `createTime` (B), khóa phụ `Cust + time` (H). `createTime` là text dạng `YYYY-MM-DD HH:MM` nên sắp xếp theo text ra đúng thứ tự thời gian; khóa phụ giữ các dòng của một đơn liền nhau, và `Transaction` tự tính lại theo dòng mới ngay trên. Dòng cũ gõ tay sai dạng (ví dụ `27 Mar 2026 10:19`) sẽ đứng sai chỗ, cần sửa tay về đúng dạng.
6. Trở lại trang, ở bảng **File đã tải** bấm **Xác nhận đã dán** cho đúng file vừa dán. Lần xuất sau không còn các đơn đó. Nếu một đơn đã được xác nhận qua file khác, thông báo ghi số đơn bỏ qua.
7. Dán nhầm hoặc dán thiếu: xóa các dòng đã dán trong file lịch sử, bấm **Gỡ xác nhận** cho file đó, rồi xuất lại.

Quên xác nhận thì lần xuất sau có lại các đơn đó (lặp chứ không sót); bảng **File đã tải** ghi "Chưa xác nhận" để nhắc. File sẽ không bao giờ được dán (tải thử, tải trùng) thì bấm **Xóa** ở dòng đó để làm sạch bảng; file và danh sách đơn của nó bị xóa, các đơn chưa xác nhận vẫn có trong lần xuất sau. File đã xác nhận không xóa được: gỡ xác nhận trước. Chỉ admin xác nhận, gỡ xác nhận và xóa.

## Duyệt bảng dài

Mọi bảng có dòng tiêu đề đều bấm được vào tên cột để sắp xếp (lần 1 tăng dần, lần 2 giảm dần, lần 3 về thứ tự gốc). Bảng từ 8 dòng trở lên có thêm ô **Tìm trong bảng** (không phân biệt hoa thường và dấu), ô chọn lọc ngay dưới tiêu đề cho cột chỉ có vài giá trị (sàn, trạng thái…), nút **Xóa bộ lọc**, và phân trang 10/25/50/100 dòng (lựa chọn được nhớ trên trình duyệt). Các dòng của cùng một đơn (đơn nhiều sản phẩm) luôn đi cùng nhau. Các danh sách lịch sử (Lô đơn, khách hàng theo sàn, hàng đợi robot, đợt gửi kế toán, lần tải báo cáo SAP, file Shop Online đã tải) được tìm và phân trang ngay trên máy chủ: ô **Tìm** quét toàn bộ dữ liệu cũ (không chỉ trang đang xem), có chọn 10/25/50/100 dòng/trang và liên kết số trang; tìm không phân biệt hoa thường nhưng phân biệt dấu. Ở các bảng này bấm tên cột chỉ sắp xếp các dòng của trang đang xem.

## Khi có sự cố

- **Web không mở được hoặc máy chạy thật hỏng:** làm file Excel bằng tay như trước, báo người quản trị hệ thống.
- **Thanh cảnh báo sao lưu màu cam:** trang **Sao lưu** (mục trên cùng của menu) nói rõ nơi nào hỏng hoặc bản nào quá hạn. Người xem chỉ đọc; admin bấm **Sao lưu ngay** hoặc báo người quản trị.
- **File bị từ chối:** thông báo nêu cột thiếu hoặc dòng lỗi. Sàn có thể đã đổi mẫu file; không sửa tay file sàn, báo người quản trị.

## Biên bản chạy song song (cổng G1)

Trong 10 ngày làm việc liên tiếp, admin vẫn làm file gửi kế toán bằng tay và so từng ô với file hệ thống. Mỗi khác biệt được ghi lại, sửa trong hệ thống và thêm thành ca test.

| Ngày | Sàn | Số dòng | Ô khác nhau | Ghi chú | Người so |
|---|---|---|---|---|---|
| 11/11/2026 (dữ liệu mẫu, trên máy phát triển) | Shopee, TikTok, Lazada | 15 dòng DO | 0 | So `SHOP ONLINE 111126.XLSX` dựng lại từ `zrsd001`, `zrsd004`, `NOTE TT KH T11` | Kiểm thử tự động |
