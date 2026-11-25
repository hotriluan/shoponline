# Brainstorm: module báo cáo cho quản lý

Ngày 2026-11-25. Đầu vào cho plan. Người xem chính: **quản lý**.

## Quyết định của chủ dự án

1. Kiến trúc: báo cáo trong web hiện có, đọc từ schema `reporting` của PostgreSQL; chỉ lưu cố định những gì view không tính lại được.
2. Bỏ việc xóa dữ liệu khách sau 90 ngày. Giữ `customer_info` vĩnh viễn.
3. Nhập tiền về Lazada bằng tay (không có file nguồn nào dùng được).
4. Ba con số doanh thu hiện thành ba đường riêng trên cùng báo cáo.
5. Nạp toàn bộ lịch sử từ `docs/history/Shop Online 2022-2026-10-luan.xlsx`.
6. Không dùng Power BI, không mở database ra ngoài `localhost`.

## Hợp đồng

**Kết quả:** quản lý mở trang `/reports`, xem xu hướng doanh số từ 2022 tới nay theo tháng, sàn, shop, sản phẩm và tỉnh. Từ 11/2026 trở đi, trang có thêm ba đường giá trị trên sàn, doanh thu hóa đơn và tiền thực nhận, cùng phí sàn và trả hàng. Mọi bảng tải được ra Excel.

**Ràng buộc:**
- Không ghi gì vào SAP.
- Dùng tài khoản admin/viewer hiện có: viewer xem được báo cáo, chỉ admin nhập tiền Lazada và nạp lịch sử.
- Không phụ thuộc thư viện tải từ mạng; thư viện biểu đồ chép vào `static/`.
- Sao lưu database trước khi chạy migration và trước khi nạp lịch sử.

**Không làm:**
- Dự báo.
- Gọi API sàn.
- Báo cáo kho.
- Sửa ngược dữ liệu lịch sử trong file gốc.
- Bảng kê chi phí sàn theo mẫu kế toán. Có thể là bước sau, vì người xem chính là quản lý.

**Kiểm chứng:**
- Nạp lịch sử xong thì tổng `Customer paid` theo năm và theo Division khớp tổng trên file gốc. Báo cáo nạp liệt kê từng dòng bị loại và lý do.
- Nạp lại cùng file không sinh dòng trùng.
- Không có tháng nào bị tính hai lần ở chỗ giáp ranh giữa lịch sử và dữ liệu hệ thống.
- Ba đường doanh thu của một tháng mẫu khớp truy vấn tay trên `sales_order_item`, `sap_tax_invoice` và `platform_settlement`.
- Nhập tiền Lazada cho một đơn thì đơn đó hết nằm trong "chờ tiền vô" và có số ở đường tiền thực nhận.
- Lệnh `shoponline retention` (kể cả với `--apply`) không xóa dòng `customer_info` nào nữa; các quy tắc xóa file vẫn chạy như cũ.

## Phát hiện khi khảo sát

### File lịch sử (3.006 dòng, 19 cột, cùng 17 cột với file `sales_history` hệ thống đang xuất)

- **Không có mã đơn sàn, mã vật tư hay số hóa đơn.** Vì vậy lịch sử chỉ có đường "giá trị trên sàn" (`Customer paid`, cùng nghĩa với cách hệ thống tính: (giá − trợ giá) × số lượng). Hai đường còn lại bắt đầu từ khi có dữ liệu hệ thống.
- **Ngày lộn xộn:** 2.891 dòng dạng `yyyy-mm-dd`, 102 dòng `dd-mm-yyyy`, 185 dòng `yyyy-dd-mm` (ví dụ `2026-19-08`), 13 ô kiểu khác. Có ngày lớn nhất là 2026-12-08, tức là ngày ở tương lai, do đọc nhầm ngày với tháng.
- **Cột `month`/`year` lệch với `createTime` ở 987 trong số các dòng đọc được ngày.** Riêng 758 dòng lệch đúng 12 tháng. Kỳ báo cáo phải lấy theo một quy tắc đã chốt (xem câu hỏi 2).
- **Division** có 8 giá trị nhưng viết hoa không thống nhất (`tiktok`/`Tiktok`/`shopee Bình Dương`). Đây là **shop**, không phải sàn. Shopee có ba shop: PGT, Bình Dương, Đà Nẵng. Lazada có `Lazada` và `Lazada Mall`. Hệ thống hiện gán mỗi sàn một Division cố định (`DIVISION` trong `exports/sales_history_workbook.py`).
- **`billingCity`** có 327 giá trị: tên tỉnh cũ trước sáp nhập 2025, xen lẫn tên huyện hoặc thành phố (`Huyện Cẩm Mỹ`, `Thành Phố Phan Thiết`). Hàm `province_of` chỉ nhận 34 tỉnh mới, nên cần thêm bảng quy đổi tên cũ sang tỉnh mới.
- Tên và số điện thoại trong file đã bị che một phần (`t******n`). Giá trị `unitPrice` có ô kiểu chuỗi.
- 559 dòng (năm 2022) có `Cust + time` và `Transaction` (1 hoặc 0) dùng để đếm đơn. Các năm sau không có, nên với lịch sử, một đơn được nhận biết bằng `billingName` + `createTime` + Division.

### Xóa dữ liệu khách

- Phần xóa nằm ở `maintenance/retention.py`: hàm `find_expired` và `apply`, lệnh `retention --apply`, và tùy chọn `-RetentionApply` trong `scripts/windows/register-tasks.ps1`.
- `retention_days` còn quyết định thời gian giữ file `zrsd004` tải tay (`kept_files`). Vì vậy chỉ gỡ phần xóa dữ liệu khách; biến cấu hình vẫn giữ cho phần file.
- Nếu tác vụ trên máy chạy thật đã đăng ký với `retention --apply`, `register-tasks.ps1` sẽ giữ lại tham số đó. Vì thế `--apply` phải vẫn được chấp nhận (không làm gì và ghi log) để tác vụ không lỗi, và `register-tasks.ps1` không đăng ký nó nữa.
- Cần sửa tài liệu: `docs/security-and-data-retention.md`, README (bảng biến và lệnh), `docs/operations-runbook.md`, `docs/deployment-guide.md`.

### Tiền về Lazada

File Balance Transactions của Lazada không có mã đơn, nên bộ đọc đang từ chối (`importers/settlement_files.py`). Nhập tay sẽ ghi vào chính `platform_settlement` (`platform='LAZADA'`, `line_key` dạng `manual:<id>`, `import_batch_id` trỏ tới một lô kiểu `manual_settlement`), để trang lịch sử, cột "Tiền Vô" và báo cáo dùng chung một nguồn.

## Ba đường doanh thu

Có. Mỗi báo cáo theo kỳ có ba đường, cộng hai chênh lệch suy ra:

| Đường | Định nghĩa | Nguồn | Có từ |
|---|---|---|---|
| Giá trị trên sàn | (giá − trợ giá) × số lượng | `sales_order_item`; lịch sử: `Customer paid` | 2022 |
| Doanh thu hóa đơn | `net_value_vnd + tax_vnd` | `sap_tax_invoice` qua `do_number` | 11/2026 |
| Tiền thực nhận | Tổng `amount` theo mã đơn | `platform_settlement` (Lazada nhập tay) | 11/2026 |
| Trợ giá / chênh giá | Giá trị trên sàn − doanh thu hóa đơn | suy ra | |
| Phí sàn | Doanh thu hóa đơn − tiền thực nhận | suy ra | |

**Mốc thời gian:** cả ba con số được tính vào kỳ của **ngày đặt đơn**. Ví dụ: "các đơn đặt trong tháng 11, đã xuất hóa đơn bao nhiêu, đã nhận bao nhiêu tiền". Như vậy ba đường so sánh được với nhau, và phần chưa có hóa đơn hoặc chưa nhận tiền hiện ra thành khoảng hở. Nếu mỗi con số đi theo ngày riêng của nó (ngày hóa đơn, ngày nhận tiền) thì các đường lệch kỳ nhau và quản lý khó đọc. Cách tính theo ngày riêng, nếu cần, để cho bảng kê của kế toán sau này.

## Thiết kế đã chọn

- **Bảng mới:**
  - `history_sale_line`: một dòng lịch sử đã làm sạch gồm kỳ, ngày (có thể trống), shop, sàn, tỉnh, tên hàng, quy cách, màu, số lượng, `customer_paid`, khóa chống trùng, và dòng gốc để đối chiếu.
  - `shop`: danh mục shop (mã, sàn, tên Division chuẩn, còn bán hay không), dùng chung cho đơn hệ thống và lịch sử; các cách viết khác của Division trong file lịch sử quy về tên chuẩn.
  - `province_alias`: tên cũ hoặc tên huyện quy về 1 trong 34 tỉnh, sửa trên web giống trang `/report-names`.
- **View `reporting.sale_line`:** gộp `history_sale_line` (trước mốc ranh giới) với dòng bán từ hệ thống (từ mốc trở đi), chung một bộ cột. Mọi báo cáo bán hàng đọc từ view này.
- **View `reporting.order_revenue`:** ba con số theo từng đơn của hệ thống.
- **Trang `/reports`:**
  - Tổng quan: ba đường theo tháng, giá trị đơn trung bình, số đơn.
  - Theo sàn và shop.
  - Theo sản phẩm, quy cách và màu.
  - Theo tỉnh.
  - Trả hàng.
  - Bộ lọc kỳ, sàn, shop; nút xuất Excel.
- **Trang nhập tiền Lazada:** danh sách đơn Lazada đã giao mà chưa có tiền. Admin nhập số tiền và ngày nhận, theo từng đơn hoặc dán nhiều dòng; sửa và xóa được; mọi thay đổi ghi `event_log`.
- **Nạp lịch sử:** lệnh CLI cộng trang tải lên. Chạy thử trước (in báo cáo dòng hợp lệ, dòng bị loại, các tên tỉnh và shop chưa quy đổi được), xác nhận rồi mới ghi. Nạp lại thì thay toàn bộ lịch sử trong một giao dịch.

## Thứ tự làm

1. Gỡ việc xóa dữ liệu khách, sửa tài liệu.
2. Nhập tiền về Lazada.
3. Danh mục shop: đơn mang shop, trang tải file chọn shop, file lịch sử Shop Online xuất theo Division của shop.
4. Nạp lịch sử cùng bảng quy đổi tỉnh; Division trong file lịch sử quy về danh mục shop.
5. Các view `reporting` và trang `/reports`.

Bước 1 và 2 độc lập với nhau; bước 4 cần bước 3; bước 5 cần bước 4.

## Rủi ro

- **Pháp lý:** giữ tên và địa chỉ khách vô thời hạn là thay đổi chính sách dữ liệu cá nhân (Nghị định 13/2023). Đây là quyết định của chủ dự án; tài liệu sẽ ghi lại lý do và ngày chốt.
- **Quy tắc ngày của lịch sử** quyết định số theo tháng. Chọn sai thì xu hướng bị lệch kỳ.
- Một phần dòng lịch sử có thể không quy đổi được về tỉnh. Báo cáo theo tỉnh hiện chúng là "Chưa xác định", không đoán.

## Quyết định bổ sung (2026-11-25, 13:14)

1. **Chưa từng xóa dữ liệu khách.** Máy chạy thật là máy này (`C:\shoponline`, database `shoponline`). Tác vụ `shoponline-retention` đăng ký không có `--apply` (chỉ liệt kê) và đã tắt từ 16/11. `event_log` không có dòng `retention_*` nào. Cả 62 đơn đều còn `customer_info`. Không có gì phải khôi phục.
2. **Kỳ của dòng lịch sử lấy theo cột `month`/`year`.** Kiểm tra cho thấy các dòng có `createTime` là `2026-11-08` hay `2026-12-08` đều mang kỳ 8/2026, tức là đảo ngày với tháng (ngày 11/8 và 12/8). Theo `month`/`year`, kỳ cuối của file là 10/2026 (240 dòng).
3. **Ranh giới tính theo tháng: lịch sử nhận các kỳ đến hết 10/2026; hệ thống nhận đơn có `ordered_at` từ 01/11/2026.** Bộ nạp từ chối dòng lịch sử có kỳ từ 11/2026 trở đi. Mốc là một hằng số cấu hình duy nhất, view `reporting.sale_line` dùng chung mốc đó.
   - Ranh giới theo tháng khớp với quyết định lấy kỳ theo `month`/`year`. Ranh giới theo ngày cần `createTime`, mà cột này đọc không tin được.
   - **Có lỗ hổng 01–10/11/2026.** Đơn sớm nhất trong hệ thống (cả `shoponline` và `shoponline_dev`) đặt lúc 11/11/2026 10:32; file lịch sử dừng ở kỳ 10/2026. Đơn đặt từ 1 đến 10/11 không nằm ở nguồn nào. Báo cáo đánh dấu tháng 11/2026 là "thiếu dữ liệu 01–10/11" cho đến khi lỗ hổng được lấp.
4. **Ghi riêng từng shop.** Thêm danh mục `shop` (mã, sàn, tên Division chuẩn, còn bán hay không). Lô đơn và đơn mang `shop`; trang tải file sàn bắt chọn shop; `DIVISION` cố định trong `exports/sales_history_workbook.py` được thay bằng tên Division của shop. Các shop đã có trong lịch sử được tạo sẵn: Shopee PGT, Shopee Bình Dương, Shopee Da Nang, tiktok Bình Dương, Lazada, Lazada Mall. Đơn hiện có được gán vào shop đang mặc định cho sàn đó.

## Quyết định bổ sung (2026-11-25, lượt 3)

1. **Lấp lỗ hổng 01–10/11/2026:** bộ nạp lịch sử nhận thêm từ file của kế toán đúng các dòng có kỳ 11/2026 và `createTime` trước 11/11/2026. Dòng kỳ 11/2026 mà ngày không đọc được hoặc ngày từ 11/11 trở đi thì bị loại và liệt kê trong báo cáo nạp. Từ 11/11, nguồn duy nhất là dữ liệu hệ thống.
2. **Các shop cùng một sàn dùng chung một khách hàng SAP.** Vì vậy robot, `platform_setting.sap_customer`, bộ đối chiếu `zrsd001`/`zrsd004`/`zrsd003` và đợt gửi kế toán giữ nguyên. Shop chỉ là một thuộc tính của đơn, phục vụ file lịch sử Shop Online và báo cáo.
3. **Không tự nhận ra shop được; admin chọn shop khi tải file.** Kết quả kiểm tra các file mẫu trong `docs/`:
   - Shopee (`Order.toship…xlsx`, 61 cột): không có cột nào mang tên shop; tên file cũng không có.
   - TikTok (`Chờ vận chuyển…xlsx`, 56 cột): `Warehouse Name` là tên công ty (`CÔNG TY TNHH ALKANA VIỆT NAM`), giống nhau cho mọi shop.
   - Lazada (`lazadaexport.xlsx`, 77 cột): `wareHouse` = `PROPAN PAINT STORE`. Có thể là tên kho của shop, nhưng chỉ có một file mẫu nên không chứng minh được hai shop Lazada khác nhau ở cột này.

   Thiết kế: trang `/imports` thêm ô chọn shop, lọc theo sàn đã chọn. Sàn chỉ còn một shop đang bán thì tự chọn sẵn. Shop tải gần nhất của sàn đó được chọn mặc định. `order_batch` vẫn giữ khóa `(platform, processing_date)`, vì file `ĐƠN HÀNG ONLINE <SÀN>` và SO trong SAP đi theo sàn; shop gắn vào `sales_order`. Bảng ánh xạ SKU vẫn theo sàn.

## Tự nhận shop khi tải file (lượt 4; ĐÃ BỎ ngày 2026-11-25 khi lập kế hoạch, giữ thiết kế "admin chọn shop")

Bằng chứng từ các file mẫu:
- **TikTok:** `SKU ID` là mã sàn sinh cho từng sản phẩm đăng bán (ví dụ `1733884027240089393`). Mã này thuộc về shop đã đăng sản phẩm đó.
- **Lazada:** `lazadaSku` có dạng `<mã sản phẩm>_VNAMZ-<mã biến thể>`, cũng do sàn sinh theo shop. Có thêm cột `wareHouse` (`PROPAN PAINT STORE`).
- **Shopee:** file `Order.toship` không có mã sản phẩm nào do sàn sinh. `SKU sản phẩm` để trống, `SKU phân loại hàng` là mã người bán tự nhập (`10`). Shopee lại là sàn có ba shop.
- Ánh xạ SKU đi theo tên sản phẩm và tên phân loại (`domain/sku_mapping.py`), không theo SKU người bán. Đổi SKU người bán không ảnh hưởng ánh xạ.

Cách nhận shop, xét theo thứ tự:
1. **Sàn chỉ có một shop đang bán:** chọn luôn shop đó. Hiện mỗi sàn chỉ một shop đang bán, nên mọi lần tải hiện nay đều tự động.
2. **Mã sản phẩm đã học (TikTok, Lazada):** bảng `shop_listing (platform, listing_key, shop)`. Mỗi lần tải được xác nhận thì ghi mã của các dòng vào bảng. Lần sau, nếu mọi mã đã biết trong file đều thuộc một shop thì nhận shop đó.
3. **Quy ước SKU người bán (Shopee, và cả hai sàn kia):** mỗi shop đặt một tiền tố riêng cho `SKU phân loại hàng`/`Seller SKU`/`sellerSku` trên trang người bán, ví dụ `BD-`, `PGT-`, `DN-`. Tiền tố khai trong danh mục shop. Đây là thay đổi thao tác của shop, không phải thay đổi code của sàn.
4. **Không xác định được:** file chưa có mã nào đã học và không khớp tiền tố nào, hoặc mã đã học trỏ tới hai shop khác nhau. Khi đó trang dừng và bắt admin chọn shop. Lựa chọn đó cũng được ghi vào `shop_listing`. Nếu hai shop cùng khớp thì báo rõ dòng nào trỏ về shop nào.

Trang kết quả tải luôn ghi shop đã nhận và căn cứ (một shop đang bán / mã đã học / tiền tố SKU / admin chọn). Hệ thống không đoán theo tên sản phẩm, vì các shop bán cùng sản phẩm.

**Trade-offs:**
- *Chỉ cho admin chọn:* đơn giản nhất. Dựa vào giả định là admin luôn chọn đúng; sai lần đầu khi admin quên đổi shop, và lỗi chỉ lộ ra trong báo cáo.
- *Học mã sản phẩm:* dựa vào giả định mã sàn sinh không trùng giữa các shop (đúng với cách TikTok và Lazada cấp mã, nhưng mới thấy trên file của một shop). Hỏng ở lần tải đầu của mỗi sản phẩm mới, và với Shopee thì không dùng được.
- *Quy ước tiền tố SKU:* dựa vào giả định nhân viên đặt SKU đúng quy ước trên mọi sản phẩm. Hỏng khi một sản phẩm mới được đăng mà quên tiền tố; lúc đó rơi về bước 4, không nhận sai.

**Better approaches:** quy ước tiền tố SKU là cách duy nhất làm được cho Shopee. Nó cũng đủ cho TikTok và Lazada, nên nếu shop chấp nhận quy ước này thì có thể bỏ bước 2 (học mã) để giảm một bảng. Bước 2 vẫn hữu ích khi không đổi được SKU của sản phẩm đang bán.

## Câu hỏi còn mở

1. Shop có đồng ý đặt tiền tố SKU người bán riêng cho mỗi shop (nhất là Shopee) không? Nếu không, Shopee nhiều shop đang bán cùng lúc thì vẫn phải chọn tay.
2. Giữ cả bước học mã sản phẩm (TikTok, Lazada) hay chỉ dùng tiền tố SKU?
