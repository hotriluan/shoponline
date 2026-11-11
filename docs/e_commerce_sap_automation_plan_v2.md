# KẾ HOẠCH DỰ ÁN (BẢN CHỈNH SỬA V2): TỰ ĐỘNG HÓA ĐƠN HÀNG SÀN TMĐT ↔ SAP ECC6

**Sàn:** Shopee, Lazada, TikTok Shop
**ERP:** SAP ECC6 (module SD, FI), thao tác qua **SAP GUI Scripting** (không dùng RFC/BAPI)
**Hóa đơn điện tử:** BKAV (hiện upload file Excel; API cần xác nhận)
**Kiến trúc:** Python, PostgreSQL, Docker (phần không phải SAP) + một máy Windows riêng cho robot SAP

> Ghi chú đọc kế hoạch: mục đánh dấu **[Xác nhận]** là điểm chưa chắc, cần kế toán, sales admin hoặc nhà cung cấp (BKAV, sàn) xác nhận trước khi cố định trong mã. Các thông số kỹ thuật của sàn (thời hạn token, tên API, quyền truy cập) cần đối chiếu với tài liệu hiện hành tại thời điểm triển khai.

---

## 0. THAY ĐỔI SO VỚI BẢN V1

| # | Thay đổi | Lý do |
|---|---|---|
| 1 | Bỏ bước bật scripting bằng RZ11/RZ10 | Scripting đã chạy được (đã ghi thành công script `VA03`). Đổi tham số profile là việc của Basis, ảnh hưởng toàn hệ thống |
| 2 | Tách Docker và máy Windows | SAP GUI Scripting cần Windows có phiên tương tác, không chạy được trong container Linux |
| 3 | Đổi thứ tự Workflow C | Quy trình thật: đóng gói và dán vận đơn trước khi shipper lấy hàng; PGI sau khi kho xác nhận |
| 4 | Hóa đơn lấy số liệu từ chứng từ SAP | Tránh lệch giữa hóa đơn và sổ kế toán; hóa đơn đã phát hành khó sửa |
| 5 | Thêm mục giải quyết địa chỉ người mua | API sàn che số nhà/tên đường, trong khi hóa đơn cần địa chỉ |
| 6 | Thêm mục giá, VAT, voucher, trợ giá | V1 chưa nói đến thuế và cách phân bổ voucher |
| 7 | Thêm hàng đợi một phiên SAP, chống trùng, kiểm tra chéo | Một phiên GUI dùng chung cho mọi việc |
| 8 | Đổi thứ tự triển khai và thêm chạy song song (shadow mode) | Đưa phần có lợi nhanh lên trước, giảm rủi ro khi ghi chứng từ thật |
| 9 | Không dùng AI/LLM trong đường đi chính của nghiệp vụ SAP | Nghiệp vụ phải xác định, cùng đầu vào cho cùng đầu ra |
| 10 | Đối soát thanh toán: bắt đầu bằng báo cáo, chưa ghi tự động | Phần nhạy cảm nhất của kế toán |

---

## 1. NGUYÊN TẮC THIẾT KẾ

1. **Xác định, không đoán.** Mọi thao tác tạo chứng từ SAP, phát hành hóa đơn là mã xác định. Mô hình ngôn ngữ (nếu dùng) chỉ hỗ trợ phụ như tóm tắt thông báo lỗi cho người xử lý, không quyết định bước nghiệp vụ.
2. **Không tạo trùng.** Trước khi tạo chứng từ, luôn kiểm tra đã tồn tại chưa (theo mã đơn sàn). Không tự thử lại thao tác tạo nếu chưa biết lần trước đã thành công hay chưa.
3. **SAP là nguồn chuẩn cho số liệu kế toán.** Hóa đơn và bút toán dựa trên chứng từ SAP.
4. **Người duyệt ở các điểm khó đảo ngược** (hóa đơn, bút toán), ít nhất trong giai đoạn đầu.
5. **Dừng khi bất thường.** Lỗi liên tiếp hoặc số liệu lệch thì dừng robot và báo người, không chạy tiếp.
6. **Từng bước, có chạy song song.** Chỉ ghi chứng từ thật khi kết quả khớp ổn định với người làm tay.

---

## 2. KIẾN TRÚC

```
 Shopee ─┐
 Lazada ─┼─► [Docker] Connector + Order Sync ─► PostgreSQL ◄─► Web UI (kho, sales admin)
 TikTok ─┘                                         │
                                                   ▼
                                       Hàng đợi công việc SAP
                                                   │
                                                   ▼
                          [Windows VM / mini PC] Robot SAP GUI Scripting (1 phiên)
                                                   │
                                                   └─► Số chứng từ trả về PostgreSQL

 Hóa đơn: SAP billing doc ─► (Excel mẫu hiện tại hoặc API BKAV, [Xác nhận]) ─► BKAV
 In vận đơn: API sàn ─► file AWB ─► máy in kho
```

### 2.1 Phần chạy trong Docker
- PostgreSQL.
- Connector từng sàn (xác thực, làm mới token, gọi API, chuyển về định dạng đơn chung).
- Order Sync (polling 5 phút, kết hợp webhook nếu sàn hỗ trợ; webhook chỉ là tín hiệu, dữ liệu luôn lấy lại qua API).
- Label Service (lấy và gom in vận đơn).
- Web UI nhẹ: duyệt đơn lỗi, quét mã kho, xem trạng thái, nút thử lại.
- Cảnh báo (Zalo/Email/Telegram).

### 2.2 Phần chạy trên máy Windows riêng
- SAP GUI cài sẵn, đăng nhập bằng user riêng cho robot.
- Python với `pywin32` (`win32com.client`) điều khiển SAP GUI Scripting.
- Chỉ **một robot xử lý một việc tại một thời điểm** trên một phiên.
- Máy cố định độ phân giải, tắt khóa màn hình và tự đăng xuất, bỏ tích hai ô thông báo "Notify when a script attaches/opens a connection" (chỉ làm trên máy chuyên dụng này).
- Nếu dùng RDP, cấu hình để phiên không bị khóa khi ngắt kết nối; hoặc dùng mini PC có màn hình ảo.

### 2.3 Hàng đợi công việc SAP (ưu tiên)
Mọi việc chạm vào SAP (tạo SO, tạo DO, PGI, đọc tồn kho, lập billing, nhập hàng hoàn) vào cùng một hàng đợi trong PostgreSQL. Thứ tự ưu tiên gợi ý:
1. Đơn sắp quá hạn giao cho shipper.
2. Tạo SO, DO, PGI cho đơn bình thường.
3. Billing/hóa đơn.
4. Đọc tồn kho, nhập hàng hoàn, báo cáo (chạy lúc ít việc).

---

## 3. GIAI ĐOẠN 0: CHUẨN BỊ

### 3.1 Cấu hình SAP GUI (đã làm một phần)
- ✅ Client đã bật "Enable scripting".
- ✅ Server đã cho phép (ghi được script `VA03`).
- Trên máy robot: bỏ tích hai ô thông báo script; tạo user SAP riêng cho robot **[Xác nhận chính sách công ty]**.
- Hỏi về chính sách đổi mật khẩu định kỳ (mật khẩu hết hạn sẽ làm robot dừng). Có cảnh báo trước hạn.
- Ghi lại thao tác thật bằng recorder cho từng T-code cần dùng: `VA01`, `VA05`/báo cáo tìm SO, `VL01N`, `VL02N`, `VF01`, `MMBE` (hoặc báo cáo tồn kho đang dùng).

### 3.2 Đăng ký API sàn
- **Shopee Open Platform:** tạo app cho hệ thống nội bộ của người bán; lấy Partner ID/Key; quyền kết nối shop có hạn, cần cấp quyền lại định kỳ.
- **Lazada Open Platform:** tạo app loại Seller In-house phù hợp loại hình (cá nhân/doanh nghiệp); OAuth.
- **TikTok Shop Partner Center:** tạo app Custom cho shop của chính mình, xin đủ nhóm quyền (đơn hàng, logistics, tài chính). **[Xác nhận]** cổng khu vực dành cho shop Việt Nam; khu vực của tài khoản không đổi được sau khi tạo.
- **Quản lý token:** mô-đun làm mới token trước khi hết hạn. Một số sàn cấp **refresh token mới sau mỗi lần làm mới**, nên phải lưu token mới ngay vào database (trong cùng giao dịch) và có cảnh báo khi làm mới thất bại. Thời hạn token cần đối chiếu tài liệu hiện hành, không cố định cứng trong mã.

### 3.3 Cơ sở dữ liệu (PostgreSQL)
Bảng chính:
- `shop`: sàn, mã shop, mã khách hàng SAP riêng cho sàn, nhà máy/kho, token (mã hóa), hạn quyền kết nối.
- `sync_cursor`: mốc thời gian lấy đơn gần nhất của từng shop.
- `order`, `order_item`: đơn thống nhất; **khóa duy nhất** (shop_id, platform_order_id).
- `sku_mapping`: SKU sàn → mã vật tư SAP, hệ số quy đổi (hỗ trợ combo: một SKU sàn thành nhiều mã SAP).
- `sap_document`: SO, DO, billing, số chứng từ, trạng thái, thời điểm.
- `shipment`: vận đơn, hãng vận chuyển, tracking, thời điểm in, thời điểm giao shipper.
- `sap_job`: hàng đợi công việc SAP (loại việc, tham số, ưu tiên, số lần thử, kết quả, ảnh chụp màn hình khi lỗi).
- `event_log`: mọi chuyển trạng thái và thao tác SAP/API.
- `settlement_line`, `invoice_export`: dùng cho đối soát và hóa đơn (giai đoạn sau).

### 3.4 Các quyết định cần chốt với kế toán và sales admin (trước khi viết robot tạo SO)
1. Trường tham chiếu nào trên SO dùng lưu mã đơn sàn (để chống trùng).
2. Giá và VAT: giá niêm yết trên sàn có gồm VAT không, giá ZPR1 trong SAP có gồm VAT không, cách quy đổi.
3. Voucher của shop: ghi dưới dạng điều kiện nhập tay nào (ví dụ `ZDI1`/`ZDI2`), ghi âm hay dương, theo dòng hàng hay theo đơn.
4. Voucher cấp theo đơn: phân bổ vào các dòng hàng thế nào và quy tắc làm tròn.
5. Trợ giá/voucher của sàn: xử lý ra sao trên SO và hóa đơn (V1 giả định "bỏ qua rồi thu khi đối soát"; cần kế toán xác nhận có đúng với cách xuất hóa đơn và ghi nhận doanh thu không).
6. Phí vận chuyển: có đưa vào SO không.
7. Địa chỉ trên hóa đơn (mục 6).
8. Đơn thiếu hàng: chờ, hủy trên sàn hay tách đơn.
9. Đơn bị hủy khi đã có SO/DO: ai quyết định, đảo chứng từ thế nào.

---

## 4. GIAI ĐOẠN 1: GOM ĐƠN VÀ IN VẬN ĐƠN (KHÔNG CẦN SAP)

Đây là phần có lợi nhanh nhất, không phụ thuộc rủi ro SAP.

- Lấy đơn từ 3 sàn, chuẩn hóa vào PostgreSQL, lọc theo trạng thái hợp lệ.
- Ánh xạ SKU sàn → mã vật tư SAP; đơn có SKU chưa ánh xạ vào danh sách lỗi `MAPPING_ERROR`.
- Xuất file Excel chuẩn hóa (đã ánh xạ SKU, đúng mã khách hàng theo sàn) cho sales admin nhập SAP như hiện nay.
- Lấy vận đơn qua API Logistics, in hàng loạt, sắp thứ tự; gắn mã đơn để kho quét xác nhận đóng gói. **[Xác nhận]** từng sàn có yêu cầu bước "sắp xếp giao hàng" trước khi có mã vận đơn hay không.
- Giao diện web: xem đơn, đơn lỗi, trạng thái in.

**Tiêu chí hoàn thành:** sales admin không còn xuất Excel tay từ 3 sàn; kho in vận đơn hàng loạt.

---

## 5. GIAI ĐOẠN 2: ROBOT SAP (SO → DO → PGI)

### Workflow A: Tạo Sales Order
- **Kích hoạt:** đơn hợp lệ, SKU đã ánh xạ, kiểm tồn đạt.
- **Kiểm tra trước khi tạo:**
  1. Tìm SO theo mã đơn sàn (báo cáo/`VA05` hoặc tương đương). Nếu đã có thì chỉ ghi lại số SO, không tạo mới.
  2. Kiểm tồn khả dụng cho từng dòng (đọc `MMBE` hoặc báo cáo tồn kho đang dùng, có đệm kết quả để đỡ chậm).
- **Thao tác `VA01`:** loại đơn, tổ chức bán hàng, mã khách hàng của sàn, mã đơn sàn vào trường tham chiếu, các dòng SKU, số lượng, giá; điều kiện giảm giá nhập tay theo mục 3.4 (đã chốt với kế toán); lưu.
- **Đọc kết quả:** từ thanh trạng thái (loại thông báo và nội dung); lấy số SO.
- **Kiểm tra chéo sau khi lưu:** tổng giá trị SO so với giá trị mong đợi tính từ dữ liệu sàn. Lệch quá ngưỡng cho phép thì chuyển `NEED_REVIEW`, không đi tiếp.

### Workflow C (đã đổi thứ tự): DO, vận đơn, đóng gói, PGI
1. **Tạo DO** (`VL01N` tham chiếu theo số SO). Có thể cần kho xác nhận trước khi tạo, tùy chính sách.
2. **Sắp xếp giao hàng và lấy vận đơn** qua API sàn **[Xác nhận]** thứ tự theo từng sàn.
3. **In vận đơn;** kho dùng DO để lấy hàng, đóng gói, dán vận đơn, **quét mã đơn xác nhận** đóng gói.
4. **PGI** (`VL02N`) khi kho đã quét xác nhận (hoặc khi shipper nhận hàng, tùy chính sách kho). Nếu đơn bị hủy trước PGI thì xử lý theo quy trình hủy DO, không tự động đảo.
5. Cập nhật trạng thái `HANDED_OVER` khi sàn báo shipper đã lấy hàng hoặc kho xác nhận bàn giao.

### Quy tắc xử lý lỗi cho robot GUI
- **Đọc thanh trạng thái** sau mỗi bước.
- **Popup không dự kiến:** đọc nội dung, ghi log, **không bấm bừa**; chuyển `NEED_REVIEW` nếu không nằm trong danh sách popup đã biết và được phép bỏ qua.
- **Phiên bị ngắt, hết thời gian, bị đăng xuất:** phát hiện, đăng nhập lại, đưa việc đang dở về trạng thái chờ kiểm tra (kiểm tra SAP đã tạo chứng từ chưa trước khi làm lại).
- **Chứng từ bị khóa** (người khác đang sửa): chờ vài giây, thử lại có giới hạn.
- **Ảnh chụp màn hình** khi lỗi, lưu cùng `sap_job`.
- **Công tắc dừng khẩn cấp:** tự dừng khi lỗi liên tiếp quá ngưỡng.
- **Chống tạo trùng:** như nguyên tắc 2.

### Trạng thái đơn (rút gọn)
`NEW → VALIDATING → READY_FOR_SO → SO_CREATED → DO_CREATED → LABEL_READY → PACKED → PGI_DONE → HANDED_OVER`
Nhánh: `MAPPING_ERROR`, `STOCK_SHORT`, `SAP_ERROR`, `NEED_REVIEW`, `CANCELLED`, `RETURNED`.
Đơn bị hủy hoặc hoàn sau khi đã có chứng từ SAP **không tự đảo**, chuyển `NEED_REVIEW` cho người có quyền.

### Chạy song song (shadow mode)
Trong 1–2 tuần đầu: robot chỉ chạy trên hệ thống test (nếu có) hoặc tạo bản đề xuất; sales admin vẫn làm tay; so sánh từng đơn. Chỉ ghi chứng từ thật khi khớp ổn định. Mở từng sàn một.

---

## 6. GIAI ĐOẠN 3: HÓA ĐƠN ĐIỆN TỬ (BKAV)

### Nguyên tắc
- **Số liệu lấy từ billing document của SAP**, không lấy từ database trung gian.
- **Phát hành sau khi shipper đã lấy hàng** (đúng quy trình hiện tại).
- **Mỗi billing document chỉ phát hành hóa đơn một lần** (kiểm tra trùng).
- Giai đoạn đầu có bước **kế toán duyệt** trước khi phát hành.

### Thao tác
1. Robot tạo billing document (`VF01`) từ DO, hoặc chạy T-code xuất Excel hiện tại.
2. **Phương án A (bắt đầu):** xuất đúng file Excel mẫu hiện tại, kế toán kiểm tra và upload lên BKAV như hiện nay.
3. **Phương án B (sau khi BKAV xác nhận):** gọi API BKAV phát hành tự động. **[Xác nhận]** gói đang dùng có mở API không, có tính phí không.
4. Ghi số hóa đơn và trạng thái về PostgreSQL.

### Địa chỉ người mua
API sàn chỉ trả địa chỉ từ phường/xã trở đi, trong khi vận đơn có địa chỉ đầy đủ. Thứ tự thử:
1. Hỏi kế toán/tư vấn thuế: hóa đơn của công ty có bắt buộc địa chỉ đầy đủ số nhà, tên đường không. Nếu chấp nhận địa chỉ từ phường/xã thì xong.
2. Dùng tính năng yêu cầu hóa đơn của sàn (nếu có) để người mua tự cung cấp.
3. Kiểm tra API Logistics có trả dữ liệu in vận đơn dạng có cấu trúc hay chỉ file PDF.
4. Phương án cuối: đọc địa chỉ từ PDF vận đơn (dễ hỏng khi sàn đổi mẫu).

Dữ liệu cá nhân của người mua chỉ lưu và dùng cho mục đích xuất hóa đơn, có thời hạn lưu rõ ràng, nhật ký không ghi thông tin không cần thiết.

---

## 7. GIAI ĐOẠN 4: ĐỐI SOÁT THANH TOÁN

### Bước đầu: báo cáo, chưa ghi tự động
Robot/API lập **bảng kê đối chiếu** hằng tháng (đúng việc shop admin đang làm tay) cho kế toán:
- Lấy dữ liệu thanh toán/đối soát từ API (Shopee có thông tin chi tiết theo đơn như hoa hồng, phí dịch vụ, phí giao dịch, voucher, phí vận chuyển điều chỉnh, số tiền thực nhận; Lazada và TikTok cần kiểm tra thực tế).
- Đối chiếu với đơn, hóa đơn, tiền về tài khoản; liệt kê chênh lệch.
- Phí sàn có hóa đơn VAT riêng hằng tháng: bút toán cần tính **thuế GTGT đầu vào**, không chỉ ghi chi phí.
- Tài khoản và quy tắc hạch toán (ví dụ 112, 641, 131, thuế GTGT đầu vào) do **kế toán trưởng xác nhận**.
- Đơn COD: tiền do shipper thu rồi chuyển sau, tách riêng khi đối soát.

### Cách kiểm tra mức đủ dữ liệu (làm trước khi viết code)
1. Tải bảng đối soát của một kỳ gần nhất từ trang quản lý từng sàn.
2. Chọn khoảng 20 đơn (đơn thường, có voucher, hoàn/hủy).
3. Lấy dữ liệu cùng các đơn qua API (dùng công cụ thử API trên trang developer).
4. So từng đơn: số thực nhận và từng khoản phí/voucher.
5. Đối chiếu tổng với tiền về ngân hàng; ghi lại khoản không khớp (ví dụ phí quảng cáo, điều chỉnh sau kỳ).
6. Phần không có trên API sẽ nhập từ báo cáo của sàn.

### Sau khi bảng kê khớp ổn định nhiều tháng
Có thể tự động hóa bước ghi nhận thanh toán và bù trừ công nợ, **vẫn có bước kế toán duyệt**.

---

## 8. GIAI ĐOẠN 5: HÀNG HOÀN, THẤT LẠC, TỒN KHO LÊN SÀN

### Workflow F: Hàng hoàn và thất lạc
- API phát hiện trạng thái hoàn/thất lạc → đưa vào bảng điều khiển đối soát (chờ trừ tiền).
- Giao diện kho quét mã hàng hoàn:
  - Nguyên vẹn: nhập lại kho trong SAP (thao tác GUI, chạy qua hàng đợi).
  - Hư hỏng/đổi hàng: gắn cờ và bắt đầu đếm thời hạn cho CSKH khiếu nại.
  - Thất lạc: theo dõi quá hạn (ví dụ trên 15 ngày) và nhắc nộp yêu cầu bồi thường.
- Đơn bị hủy trước khi giao và đơn COD có quy trình riêng (mục 3.4 và 5).

### Workflow B: Đồng bộ tồn kho lên sàn (làm muộn, có rào chắn)
Đây là tính năng mới, không nằm trong nỗi đau hiện tại, và gửi sai có thể gây hết hàng oan hoặc bán vượt. Nếu làm:
- Chạy thử không đẩy thật trước.
- Giới hạn mức thay đổi tối đa mỗi lần; không bao giờ đẩy số 0 khi không đọc được dữ liệu SAP.
- Có tồn đệm (ví dụ giữ ẩn vài đơn vị) theo cấu hình từng SKU.
- Đồng bộ toàn bộ định kỳ chứ không chỉ khi có SO (kho còn thay đổi từ kênh khác).
- Đọc tồn qua GUI từng SKU chậm, nên đệm kết quả và chạy lúc ít việc.

---

## 9. THỨ TỰ TRIỂN KHAI

| Giai đoạn | Nội dung | Phụ thuộc SAP |
|---|---|---|
| 0 | Chuẩn bị, chốt quy tắc với kế toán, ghi script các T-code | Có (đọc/ghi thử) |
| 1 | Gom đơn, ánh xạ SKU, xuất Excel, in vận đơn hàng loạt | Không |
| 2 | Robot tạo SO (shadow mode → thật), kiểm tra chéo | Có |
| 2b | DO, vận đơn, quét đóng gói, PGI | Có |
| 3 | Dữ liệu hóa đơn (Excel → API nếu BKAV hỗ trợ) | Có |
| 4 | Bảng kê đối soát hằng tháng | Ít |
| 5 | Hàng hoàn, thất lạc; đồng bộ tồn kho lên sàn; ghi nhận thanh toán tự động | Có |

---

## 10. VẬN HÀNH, BẢO MẬT, KIỂM TOÁN

- **Bí mật:** mật khẩu SAP, khóa ứng dụng sàn, token lưu trong kho bí mật hoặc biến môi trường được bảo vệ, không để trong mã nguồn. Mã hóa token trong database.
- **Quyền truy cập:** database chứa thông tin người mua nên hạn chế người truy cập; sao lưu hằng ngày; có kịch bản khôi phục.
- **Nhật ký và vết kiểm toán:** mọi thao tác SAP/API, người duyệt, ảnh chụp màn hình khi lỗi.
- **Cảnh báo có phân cấp:** lỗi tạm thời tự thử lại không báo; lỗi cần người báo; gom tin tổng hợp theo giờ để tránh tràn tin.
- **Đối chiếu hằng ngày:** số đơn trên sàn, trong database, trong SAP; báo chênh lệch.
- **Theo dõi giới hạn tần suất gọi API** của từng sàn khi đơn tăng.
- **Giấy phép và chính sách nội bộ:** việc robot tạo chứng từ SAP thay người nên được cấp trên hoặc IT biết; hỏi đại diện SAP/IT về điều khoản giấy phép truy cập gián tiếp nếu áp dụng.
- **Năng lực mở rộng:** một phiên GUI xử lý tốt 30 đơn/ngày. Khi lên hàng trăm đơn/ngày, cần tính nhiều phiên SAP (giới hạn theo cấu hình công ty) hoặc chuyển sang BAPI/RFC.

---

## 11. LƯU Ý KỸ THUẬT CHO LẬP TRÌNH VIÊN

1. Dùng `pywin32` (`win32com.client`) kết nối `SAPGUI` → `GetScriptingEngine` → connection → session. Kiểm tra phiên đã đăng nhập chưa, xử lý trường hợp có nhiều connection/session thay vì luôn dùng `Children(0)`.
2. Dùng recorder và SAP GUI Scripting Tracker để xác định ID phần tử (`wnd[0]/usr/...`). Các ID có thể khác nhau giữa các màn hình tùy chỉnh của công ty.
3. Mỗi thao tác là một hàm nhỏ trả về kết quả rõ ràng: thành công kèm số chứng từ, hoặc lỗi kèm loại và nội dung thông báo.
4. Danh sách popup đã biết và cách xử lý (được bỏ qua, phải dừng và báo) lưu thành cấu hình, không viết cứng trong mã.
5. Cố định ngôn ngữ đăng nhập SAP và độ phân giải máy robot để giảm thay đổi giao diện.
6. Viết kiểm thử cho phần xử lý dữ liệu đơn (ánh xạ SKU, tính giá, phân bổ voucher); phần GUI kiểm thử bằng bộ đơn mẫu trên hệ thống test hoặc ở chế độ shadow.

---

## 12. DANH SÁCH VIỆC CẦN XÁC NHẬN

- [ ] Hệ thống SAP có môi trường test/QA để thử không? Nếu không, dùng đơn mẫu nào để thử?
- [ ] Chính sách đổi mật khẩu của user robot.
- [ ] Trường tham chiếu SO để lưu mã đơn sàn.
- [ ] Quy tắc giá, VAT, voucher shop, voucher sàn, trợ giá, phí vận chuyển (mục 3.4).
- [ ] Địa chỉ trên hóa đơn: cần đầy đủ hay đến cấp phường/xã.
- [ ] BKAV: gói hiện tại có API không, chi phí.
- [ ] Từng sàn: có bước "sắp xếp giao hàng" trước khi lấy vận đơn không; API Logistics trả dữ liệu cấu trúc hay PDF.
- [ ] TikTok Shop: cổng khu vực dành cho shop Việt Nam.
- [ ] Mức chi tiết dữ liệu đối soát của từng sàn (thực hiện theo mục 7).
- [ ] Tài khoản và quy tắc hạch toán đối soát (kế toán trưởng).
- [ ] Quy trình đơn bị hủy sau khi đã có SO/DO.
- [ ] Đơn thiếu hàng: chờ, hủy hay tách đơn.
- [ ] Giấy phép và sự đồng ý nội bộ khi robot thao tác SAP.
