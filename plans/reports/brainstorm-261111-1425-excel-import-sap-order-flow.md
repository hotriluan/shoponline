# Brainstorm: nhập file Excel từ sàn, xử lý đơn tới post DO, xuất file gửi kế toán

Ngày: 11/11/2026. Trạng thái: hướng đã được chủ dự án chốt qua bốn vòng trao đổi; còn một điểm mở ở cuối, chỉ liên quan chặng 3.

Bản này thay đổi phạm vi của [kế hoạch 12 phase](../261111-0431-ecommerce-sap-automation/plan.md). Kế hoạch đó chưa được sửa; bước kế tiếp là lập lại kế hoạch từ hợp đồng dưới đây.

## Vì sao đổi hướng

Đăng ký API trên các sàn quá khó, riêng Shopee có khả năng không được duyệt. Chủ dự án quyết định bỏ kết nối API: admin tải file Excel từ trang quản lý sàn rồi nhập vào hệ thống.

## Hợp đồng

**Kết quả.** Trong ngày D, admin shop online tải file "chờ giao hàng" của sàn lên hệ thống. Hệ thống ánh xạ sản phẩm sàn sang mã SAP, SO được tạo với `PO No` là mã đơn sàn, hệ thống lưu cặp mã đơn ↔ số SO, rồi DO được tạo và post với ngày goods issue theo quy tắc bên dưới. Sang ngày goods issue, hệ thống lấy báo cáo `zrsd004`, chèn ba cột mã đơn hàng, tên khách hàng, địa chỉ, và xuất file gửi kế toán.

**Ràng buộc.**

- SAP chỉ qua GUI Scripting, một phiên; thử trên QA, rồi shadow, rồi mới ghi thật.
- Không mã đơn sàn nào có hai SO. Trước khi tạo SO, tra theo `PO No`.
- Mã đơn luôn được xử lý dạng chuỗi, không bao giờ dạng số.
- Không tạo DO cho đơn chưa lưu được số SO.
- Các quyết định hạ tầng trước đó giữ nguyên: một máy Windows, Python, PostgreSQL, web render phía máy chủ.

**Ngoài phạm vi.**

- Mọi việc của kế toán: billing document, sales invoice, hóa đơn VAT, BKAV, đối soát, hạch toán.
- API sàn, in vận đơn, đẩy tồn kho lên sàn.
- Tự hủy DO và SO. Đơn hủy hoặc shipper không lấy do người xử lý tay trong SAP.
- Đánh dấu đơn hủy trong file gửi kế toán. Chủ dự án không cần, vì đã lùi ngày goods issue một ngày.

**Nghiệm thu.**

- File gửi kế toán khớp từng ô với file admin tự làm trong 10 ngày làm việc liên tiếp.
- Mọi dòng trong file gửi kế toán có mã đơn hàng và địa chỉ; dòng thiếu tên khách được báo rõ trước khi xuất.
- Không mã đơn nào có hai SO.
- Giá trị SO trong `zrsd001` khớp giá trị tính từ file sàn cho mọi đơn.
- Nhập lại cùng một file sàn không đổi dữ liệu; file thiếu cột bắt buộc bị từ chối toàn bộ.

## Quy tắc nghiệp vụ đã chốt

| Quy tắc | Nội dung | Nguồn |
|---|---|---|
| Khóa nối đơn sàn với SAP | `PO No` của SO chứa mã đơn sàn | `zrsd001.XLSX` |
| Thời điểm lấy `zrsd001` | Ngay sau khi tạo SO và trước khi tạo DO, với lựa chọn "Open Sales Order" | Chủ dự án; `docs/zrsd001filter.png` |
| Ngày goods issue | Ngày làm việc kế tiếp (đơn thứ Sáu thì thứ Hai). Nếu ngày đó rơi sang tháng khác thì dùng chính ngày D | Chủ dự án |
| DO | Tạo và post ngay trong ngày D, chỉ ngày goods issue là lùi | Chủ dự án; `zrsd004.XLSX` có Delivery Date 10/11 và Actual GI Date 11/11 |
| Trợ giá | Tổng "Người bán trợ giá" và "Được Shopee trợ giá" đi vào SO bằng điều kiện `ZDI1`, số tiền đã gồm VAT, không sửa đơn giá. Chưa có SO mẫu | Chủ dự án |
| Cách nhập `ZDI1` hiện nay | `ZDI1` là bản ghi điều kiện theo cặp khách hàng SAP và mã vật tư. Mọi đơn Shopee dùng chung khách hàng `1200001145`, nên bản ghi có hiệu lực cho mọi SO Shopee của mã vật tư đó. Vì vậy: tạo hết SO không giảm giá trước; sau đó với từng đơn có giảm giá, nhập đúng số tiền cho đúng mã vật tư rồi mới tạo SO của đơn đó; cùng mã vật tư mà số tiền khác thì lặp lại cho từng đơn | Chủ dự án |
| Bảng ánh xạ | Sheet `price` chỉ là bản tham khảo; chủ dự án sẽ cung cấp bảng đầy đủ sau. Hệ thống quản lý bảng này trên web, nhập được từ Excel; dòng chưa có ánh xạ chuyển cho người | Chủ dự án |
| Phạm vi sàn | Làm Shopee trước. Lazada và TikTok làm sau, khi có file tải từ trang quản lý hai sàn | Chủ dự án |
| Combo, quà tặng | Không dùng. Mỗi dòng đơn sàn ứng với đúng một mã SAP | Chủ dự án |
| Bộ sản phẩm | Một dòng đơn sàn vẫn ứng với một mã SAP là mã bộ (ví dụ `100004033`, EDP-551 DARK GREY VN-1KS). Giá nằm ở mã bộ; SAP tự bung các thành phần thành dòng phụ giá 0 trong SO và DO khi gõ mã bộ, chỉ để kho biết khi xuất hàng, nên robot chỉ gõ một dòng. Phép so giá trị SO tính theo tổng cả SO; file gửi kế toán giữ nguyên mọi dòng của `zrsd004` | Chủ dự án; SO `210038698` có dòng 10, 11, 12 |
| `ZDI1` sau khi tạo SO | Đưa số tiền về 0. Số tiền nhập là cho một đơn vị sản phẩm | Chủ dự án |
| Billing | Billing document lấy giá từ SO, gồm cả phần giảm giá, nên việc đưa `ZDI1` về 0 sau đó không làm lệch hóa đơn | Chủ dự án |
| Ngày nghỉ lễ | Không có bảng ngày nghỉ. Hệ thống đề xuất ngày goods issue (bỏ thứ Bảy, Chủ nhật, áp quy tắc cuối tháng); admin shop online sửa được ngày này trước khi làm DO | Chủ dự án |
| Tra lại số SO sau khi đã có DO | `zrsd001` với lựa chọn "Complete" trả về SO đã giao kèm `PO No` | `docs/zrsd001complete.XLSX`: 13 SO ngày 11/11, `Deliv Qty` đủ, `PlnGI` 12/11 |
| Giá | Lấy "Giá gốc" từ file sàn. Sheet `price` đang ghi 96.000đ trong khi đơn thật là 120.000đ | File sàn và `zrsd001.XLSX` |
| Tên khách hàng | Admin chép tay từ phiếu giao hàng; file sàn che tên | Chủ dự án; file sàn |
| Địa chỉ | Tự điền từ các cột phường/xã và tỉnh/thành của file sàn | `NOTE TT KH T11.XLSX` |
| Điểm dừng của robot | Sau khi post DO. Billing và sales invoice do kế toán làm | Chủ dự án |
| File gửi kế toán | `zrsd004` nối `zrsd001` qua số SO để lấy mã đơn, rồi nối bảng khách hàng qua mã đơn | Dựng lại và khớp 15/15 dòng với `SHOP ONLINE 111126.XLSX` |

## Bằng chứng từ file thật

- Mã đơn TikTok đã bị Excel làm tròn trong quy trình tay: một `PO No` trong SAP kết thúc bằng ba số 0 trong khi đơn bên cạnh giữ đủ 18 chữ số.
- `SKU phân loại hàng` trên Shopee là `10` cho mọi màu, nên hiện phải ánh xạ bằng chuỗi ghép tên sản phẩm với tên phân loại. Một dòng trong sheet `price` thừa một dấu cách so với các dòng khác.
- Có một SO ba dòng, một mã có giá và hai mã giá 0. Đây là bộ sản phẩm; xem bảng quy tắc.
- Số SO tạo ngày 11/11 (13) nhiều hơn số đơn trong file sàn ngày 11/11 (8); năm đơn còn lại mang mã ngày 10/11. Admin nhập nhiều file trong một ngày, nên nhập file phải cộng dồn được.
- `zrsd004` có hai dòng tổng ở cuối, không có số DO.
- `zrsd001` có lựa chọn "Open Sales Order" và "Complete", và có ô lọc "Purchase Order No.".
- Mã khách hàng SAP: Shopee `1200001145`, Lazada `1200001118`, TikTok `1200001146`. Sales Organization `1000`, Sales Office `1401`.
- File đơn hàng tay của Lazada và TikTok dùng cùng bố cục với Shopee.

## Phương án: ba chặng

1. **Thay Excel tay, chưa đụng SAP.** Nhập file sàn; ánh xạ mã SAP và báo đơn chưa có ánh xạ; sinh file `ĐƠN HÀNG ONLINE` đúng mẫu hiện tại; màn hình nhập tên khách; admin tải `zrsd001` và `zrsd004` lên để hệ thống lưu số SO và xuất file gửi kế toán.
2. **Robot chỉ đọc SAP.** Robot tự chạy `zrsd001` và `zrsd004`, đối chiếu giá trị SO với file sàn, xuất file gửi kế toán.
3. **Robot ghi SAP.** Tạo SO kèm điều kiện giảm giá, ghi số SO ngay lúc lưu, tạo DO, đặt ngày goods issue theo quy tắc, post.

Ở chặng 1, hệ thống so `zrsd001` với danh sách đơn đã nhập và báo "đủ số SO, được làm DO" hoặc liệt kê đơn thiếu. Đơn lỡ làm DO trước được cứu bằng cách chạy `zrsd001` với lựa chọn "Complete" hoặc nhập tay số SO.

## Bổ sung 11/11 15:54: chế độ thủ công là tùy chọn lâu dài

Chủ dự án yêu cầu một tùy chọn "không tự động làm SO và DO". Kế hoạch `261111-0755-shopee-excel-to-sap-order-flow` chưa phản ánh phần này; cần sửa `plan.md` và viết phase 2–9 theo nó.

**Hành vi ở chế độ thủ công.**

1. Admin tải file "chờ giao hàng" của Shopee, TikTok hoặc Lazada lên. Hệ thống ánh xạ mã SAP và sinh file đơn hàng đúng mẫu `ĐƠN HÀNG ONLINE`.
2. Sales admin tạo SO và DO trong SAP như hiện nay.
3. Admin shop online bấm xác nhận "đã tạo SO và DO" cho lô đó.
4. Hệ thống lấy `zrsd001` với lựa chọn "Complete" để lưu cặp mã đơn ↔ số SO và đối chiếu, rồi lấy `zrsd004`, chèn ba cột và xuất file gửi kế toán.

**Thiết kế.**

- Đây là một luồng duy nhất có một điểm rẽ ở bước "ai tạo SO và DO": người hoặc robot. Phần trước (nhập file, ánh xạ, file đơn hàng) và phần sau (lưu số SO, đối chiếu, file gửi kế toán) dùng chung. Chế độ đặt theo từng sàn: `thủ công` hoặc `robot`.
- Ở chế độ thủ công, ràng buộc "lấy `zrsd001` trước khi làm DO" không còn cần, vì lựa chọn "Complete" trả về SO đã có DO kèm `PO No` (`docs/zrsd001complete.XLSX`).
- Sau khi xác nhận, hệ thống báo bốn loại lệch: đơn chưa có SO; SO có `PO No` không khớp đơn nào (sales admin gõ sai mã đơn); một mã đơn có hai SO; giá trị hoặc mã vật tư của SO khác với file sàn.
- Trước khi có user SAP cho robot, bước 4 làm bằng cách admin tải hai file báo cáo lên. Khi robot đọc được SAP thì hệ thống tự lấy.
- Phạm vi sàn thay đổi: chế độ thủ công nhận cả TikTok và Lazada. File TikTok đã có; vẫn cần file tải từ trang quản lý Lazada để viết bộ đọc.

**File TikTok** (`docs/Chờ vận chuyển đơn hàngtiktok-2026-11-11-15_44.xlsx`, một đơn mẫu):

- Sheet `OrderSKUList`; dòng 1 là tiêu đề, dòng 2 là dòng mô tả cột, dữ liệu từ dòng 3.
- `Order ID` là chuỗi 18 chữ số. `Seller SKU` là `5`, không dùng làm khóa ánh xạ được.
- Tên phân loại khác Shopee một dấu cách (`Cánh gián - 2004, 0.8 lít`), nên bảng ánh xạ theo từng sàn.
- `SKU Unit Original Price` theo một đơn vị; `SKU Seller Discount` và `SKU Platform Discount` theo cả dòng, khác Shopee (theo một đơn vị). Cả hai bằng 0 trong đơn mẫu.
- `Created Time` dạng `11/11/2026 11:36:57`. Tên người nhận và địa chỉ chi tiết bị che; `District` và `Province` dùng được.

Kế hoạch đã viết lại đầy đủ tại `plans/261111-0755-shopee-excel-to-sap-order-flow/`.

## Đánh đổi

| Hướng | Giả định quan trọng nhất | Hỏng trước tiên khi |
|---|---|---|
| Ba chặng, robot ghi SAP sau cùng (đã chọn) | Màn hình tạo SO, DO ổn định cho đơn sàn | Popup lạ hoặc thiếu tồn kho; chặng 1 và 2 vẫn chạy |
| Chỉ làm chặng 1 và 2 | Sales admin kham nổi việc gõ SO và DO | Ngày cao điểm 100 đơn |
| Làm robot ghi SAP trước | Quy tắc combo và điều kiện giảm giá đã rõ | Robot tạo SO sai giá |

**Hướng tốt hơn cho ánh xạ:** đặt mã SAP làm `SKU phân loại hàng` trên từng sàn. Khi đó ánh xạ là tra trực tiếp theo mã, không phụ thuộc tên hiển thị. Chi phí là sửa một lần trên trang sàn. Chủ dự án chưa quyết định.

## Rủi ro của `ZDI1` và cách robot xử lý (chặng 3)

Bản ghi `ZDI1` là dữ liệu dùng chung, không gắn với một đơn. Bản ghi còn sót lại sẽ làm mọi SO Shopee tạo sau đó của cùng mã vật tư bị giảm giá sai, kể cả SO người gõ tay.

**Hướng tốt hơn cần thử trên QA:** nhập `ZDI1` thẳng vào tab điều kiện của dòng SO thay vì sửa bản ghi điều kiện. Nếu cấu hình `ZDI1` cho phép nhập tay thì số tiền gắn với đúng một dòng của đúng một SO, không còn ràng buộc thứ tự và không còn nguy cơ sót bản ghi. Chi phí kiểm chứng là một lần thử tạo SO trên QA. Chưa kiểm chứng.

Mặc định, robot làm theo cách hiện nay (nhập bản ghi bằng `VK11`) với các chốt chặn:

1. Tạo hết SO không giảm giá trước. Trước lượt này, kiểm tra mọi bản ghi `ZDI1` của khách hàng `1200001145` đang bằng 0; khác 0 thì dừng.
2. Với từng đơn có giảm giá: nhập bản ghi cho mọi mã vật tư được giảm của đơn đó, tạo SO, đọc lại giá trị SO và so với giá trị tính từ file sàn, rồi đưa bản ghi về 0 và kiểm tra đã về 0.
3. Bất kỳ bước nào ở mục 2 lỗi thì robot dừng hẳn và cảnh báo, không làm đơn kế tiếp.
4. Trong lúc robot làm lượt giảm giá, không ai gõ tay SO Shopee.

Ở chặng 1, file `ĐƠN HÀNG ONLINE` xếp đơn không giảm giá lên trước, đơn có giảm giá xuống cuối kèm số tiền từng dòng, đúng thứ tự sales admin phải làm.

## Câu hỏi còn mở

Chỉ còn một câu, liên quan chặng 3 và không chặn việc lập kế hoạch.

1. `ZDI1` có nhập tay được trên tab điều kiện của dòng SO không? Chủ dự án chưa biết; hiện đang nhập bằng `VK11`. Kế hoạch lấy cách `VK11` kèm bốn chốt chặn làm mặc định, và thử cách nhập tay một lần trên QA khi ghi recorder tạo SO. Nếu nhập tay được thì chuyển sang cách đó.
