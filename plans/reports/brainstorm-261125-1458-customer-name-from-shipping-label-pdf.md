# Brainstorm: đọc tên và địa chỉ khách Shopee/TikTok từ PDF phiếu vận đơn

Ngày: 2026-11-25. Trạng thái: **đã chốt toàn bộ** với chủ dự án (15:23); bước tiếp theo là lập plan.

## Bối cảnh

File đơn Excel của Shopee và TikTok che tên người mua, nên `customer_info.customer_name` của hai sàn này
trống sau khi nhập file; admin đang gõ tay từng tên trên trang `/customers`. Địa chỉ từ Excel chỉ có dạng
`<quận/xã>, <tỉnh>, Việt Nam` (`domain.order.default_address`). Lazada không bị ảnh hưởng vì file Lazada có
`billingName` thật. Phiếu vận đơn PDF (file in nhãn dán hàng) có tên người nhận và địa chỉ đầy đủ.

## Quyết định của chủ dự án

| Câu hỏi | Quyết định |
|---|---|
| Tên TikTok dạng `user8822216008733` | Ghi nguyên vào hệ thống |
| Có đọc địa chỉ trên nhãn không | Có, đọc luôn địa chỉ đầy đủ |
| Đơn vị vận chuyển khác SPX/J&T | Hiện chưa có; khi có sẽ làm thêm bộ đọc |
| Giới hạn file | 40 MB và 500 trang mỗi file |
| Lưu file PDF | Không lưu: đọc xong xóa ngay, không để lại trên máy chủ |
| Phân biệt địa chỉ do Excel điền và do admin sửa | Thêm cột `customer_info.address_source` (cách 1 bên dưới) |

## Kết quả khảo sát 2 file mẫu (`docs/tenkhach/`)

| | Shopee (`Shopee - Kênh Người bán.pdf`) | TikTok (`tiktok.pdf`) |
|---|---|---|
| Mẫu | Phiếu SPX Express khổ A4, 1 trang/kiện | Nhãn J&T Express khổ nhỏ (298×420 pt), 1 trang/kiện |
| Lớp chữ | Có, không cần OCR | Có |
| Mã đơn | `Mã đơn hàng: 26112332NWGHHH` (trùng cột "Mã đơn hàng" của Excel) | `Order ID: 587345694978246318` (trùng cột "Order ID") |
| Tên | Dòng đầu dưới nhãn `Đến:`, cột phải; bố cục 2 cột nên phải cắt theo tọa độ | Chữ đậm cùng dòng nhãn `Người nhận`, trái đường kẻ dọc x≈190; bỏ mã phân loại `840` cùng dòng |
| Địa chỉ | Các dòng chữ thường dưới tên, dừng ở dòng chữ đậm đầu tiên (mã tuyến SPX như `MBD-28-12-TN02-N`); xuống dòng ở khoảng trắng, nối bằng dấu cách | Dòng đường (cỡ 11,3) + dòng xã (9,4) + dòng tỉnh (8,6); bỏ chữ thường `ĐƯỢC ĐỒNG KIÊM` |
| SĐT | Không in | Bị che, không đọc |

Nguyên mẫu `pdfplumber` (đã có trong `pyproject.toml`) đọc đúng mã đơn, tên và địa chỉ ở **16/16** trang
Shopee và **7/7** trang TikTok. Cả 23 địa chỉ đều được `province_of` hiện có nhận ra tỉnh (tên tỉnh mới), ví dụ:

- `26112336JEV6RR → Đỗ Văn Chiến → Số nhà 51- tổ 2- khu tân lập 2 ( toà nhà vàng đi vào ), Phường Quang Hanh, Tỉnh Quảng Ninh, Việt Nam → Quảng Ninh`
- `587362013583737958 → hoa → thôn Phú Đông xã Đại hiệp huyện đại lộc tỉnh Quảng Nam, Xã Đại Lộc, Đà Nẵng, Việt Nam → Đà Nẵng`

Thời gian đọc khoảng 70 ms/trang, nên 500 trang mất khoảng 35 giây.

Phát hiện cần xử lý trong code:

- TikTok ngắt dòng đường **theo ký tự**, có khi giữa từ (`Vĩnh Lon|g`, `hu|yện`), có khi đúng chỗ khoảng trắng
  (`lược|huyện`), và PDF không giữ dấu cách để phân biệt. Quy tắc đã kiểm: ghép mảnh cuối dòng với mảnh đầu
  dòng sau; nếu kết quả chỉ có một cụm nguyên âm (một âm tiết tiếng Việt) thì nối liền, ngược lại chèn dấu
  cách. Đúng cả 3 chỗ ngắt trong mẫu.
- Chữ TikTok cần chuẩn hóa Unicode NFC trước khi so khớp nhãn.
- Dấu `,` thừa cuối dòng (`An Phú ,`) bị bỏ; chữ sai do người mua gõ (`Hà Huy Tậ p_`) giữ nguyên như trên nhãn.
- Phần đường do người mua gõ có thể còn tên tỉnh cũ (`tỉnh Quảng Nam`), còn dòng cuối là tỉnh mới; định dạng
  `..., <tỉnh mới>, Việt Nam` giúp `province_of` và `place_key` lấy đúng tỉnh mới.
- Một đơn có thể có nhiều kiện (nhiều trang cùng mã đơn); phải gộp.

## Hiện trạng code liên quan

- `customer_info` (`src/shoponline/db/models.py:181`): khóa `(platform, platform_order_id)`, cột tên, địa chỉ,
  `province`, `place_key`; độc lập với `sales_order`.
- `_ensure_customer` (`src/shoponline/importers/order_import.py:282`): nhập Excel chỉ điền ô trống.
- `save_customer` (`src/shoponline/web/routes/customers.py`): admin sửa tay tên, địa chỉ; tính lại tỉnh.
- Mẫu đọc PDF: `importers/invoice_pdf.py` và route `POST /orders/{id}/return/invoice-pdf`
  (`web/routes/returns.py:236`): chỉ admin, kiểm dung lượng, đọc trong worker thread có timeout, không lưu file,
  có bước xác nhận ghi đè.
- `docs/security-and-data-retention.md`: tên, địa chỉ là dữ liệu cá nhân; cấm ghi vào `event_log`.

## Brainstorm contract

**Outcome:** Admin tải một hoặc nhiều PDF phiếu vận đơn (Shopee, TikTok, trộn lẫn được) trên trang
`/customers`; hệ thống tự nhận sàn theo từng trang, đọc mã đơn, tên và địa chỉ, ghi vào `customer_info`
(kèm tỉnh, `place_key`), rồi bỏ file. Admin không phải gõ tay tên và địa chỉ khách Shopee/TikTok nữa.

**Constraints:**

- Đọc lớp chữ bằng `pdfplumber` có sẵn; không OCR, không gửi PDF ra dịch vụ ngoài.
- Chỉ admin; kiểm `%PDF`, tối đa 40 MB và 500 trang mỗi file; đọc trong worker thread có giới hạn thời gian.
- **Không lưu PDF:** đọc vào bộ nhớ, không ghi vào `SHOPONLINE_DATA_DIR`, không ghi vào kho file, đóng
  `UploadFile` trong `finally` để file tạm mà máy chủ web tự tạo cho upload trên 1 MB bị xóa ngay sau khi đọc.
  Trên Windows file tạm này mở với cờ tự xóa, nên kể cả khi tiến trình chết giữa chừng, hệ điều hành vẫn xóa
  nó khi handle đóng. Bước xác nhận gửi lại dữ liệu đã đọc bằng trường ẩn, không giữ file chờ.
- Không ghi tên, địa chỉ vào log hay `event_log`; thông báo chỉ nêu số lượng và số trang.
- Không ghi đè dữ liệu admin đã sửa tay mà không hỏi.

**Non-goals:**

- Không đọc SĐT (bị che), không hỗ trợ Lazada.
- Không hỗ trợ đơn vị vận chuyển ngoài SPX (Shopee) và J&T (TikTok); trang không nhận ra được báo lại.
- Không sửa chính tả địa chỉ người mua gõ.

**Acceptance criteria:**

1. Tải `Shopee - Kênh Người bán.pdf` ghi đúng 16 cặp tên, địa chỉ với `platform = SHOPEE`; tải `tiktok.pdf` ghi
   đúng 7 cặp với `platform = TIKTOK` (kể cả `user8822216008733`); chọn cả hai file trong một lần cũng vậy.
   `province` của cả 23 dòng khác rỗng.
2. Tên: trống thì điền; giống thì giữ; khác thì chờ admin xác nhận.
3. Địa chỉ theo bảng quy tắc ở phần "Phân biệt địa chỉ…": trống, hoặc nguồn `file`/`label`, thì ghi; giống thì
   giữ; nguồn `admin` hoặc chưa rõ mà khác thì chờ admin xác nhận. Test cả trường hợp admin chỉ sửa tên thì
   nguồn địa chỉ không đổi.
4. Màn hình xác nhận liệt kê mã đơn, giá trị hiện có, giá trị trên nhãn, có ô chọn từng dòng; xác nhận không
   cần tải lại file.
5. Thông báo kết quả nêu số đơn đã ghi, giữ nguyên, chờ xác nhận, chưa có đơn trong hệ thống, và các số trang
   không đọc được; không nêu tên hay địa chỉ.
6. File không phải PDF, quá 40 MB, quá 500 trang, hoặc không trang nào nhận ra: từ chối, không ghi gì.
7. Sau mỗi lần tải (thành công, lỗi hay quá thời gian), không còn file PDF nào do yêu cầu đó tạo ra trên máy chủ:
   test kiểm `UploadFile` đã đóng và thư mục dữ liệu không có file mới.
8. Nhập file Excel sau khi đọc PDF không ghi đè tên, địa chỉ đã điền từ nhãn.
9. Test bộ đọc dùng PDF tổng hợp không chứa tên thật; không commit `docs/tenkhach/` lên git.
10. Cập nhật `docs/daily-operations.md` (bước tải PDF) và `docs/security-and-data-retention.md` (PDF phiếu vận
    đơn: chỉ admin, giới hạn, không lưu).

## Các phương án đọc PDF

| Phương án | Giả định chủ chốt | Hỏng đầu tiên khi | Đánh giá |
|---|---|---|---|
| **A. Đọc lớp chữ theo tọa độ bằng `pdfplumber`, một bộ đọc cho mỗi mẫu nhãn** | Sàn tiếp tục xuất PDF có lớp chữ và giữ bố cục nhãn | Sàn đổi mẫu hoặc shop dùng đơn vị vận chuyển khác: trang báo "không nhận ra", admin nhập tay; sửa bằng một bộ đọc mới | **Chọn.** 23/23 trang đúng, không thêm thư viện, chạy cục bộ |
| B. OCR hoặc AI đọc ảnh | Chấp nhận gửi dữ liệu cá nhân ra ngoài, trả phí mỗi trang | Ngay từ đầu: trái chính sách dữ liệu cá nhân, phụ thuộc mạng | Loại |
| C. Open API của sàn | Sàn cấp quyền xem thông tin người nhận | API cũng che thông tin người mua; cần đăng ký và duyệt app | Loại |

Khi có đơn vị vận chuyển thứ hai, chỉ phần nhận diện mẫu và bộ đọc mới thay đổi; phần ghi `customer_info`,
quy tắc ghi đè, route và màn hình xác nhận giữ nguyên.

Better approaches: none — hướng khuyến nghị chính là hướng người dùng yêu cầu (đọc PDF), đã kiểm chứng bằng
nguyên mẫu trên hai file thật.

## Phân biệt địa chỉ do Excel điền và địa chỉ admin sửa tay

Hầu như mọi đơn đều đã có địa chỉ dạng `quận, tỉnh, Việt Nam` từ file Excel trước khi tải PDF. Nếu coi mọi
địa chỉ khác nhau là "cần xác nhận" thì gần như đơn nào cũng phải xác nhận, mất ý nghĩa tự động. Bảng hiện tại
không cho biết địa chỉ do ai ghi.

| Cách | Giả định chủ chốt | Hỏng đầu tiên khi | Đánh giá |
|---|---|---|---|
| **1. Thêm cột `customer_info.address_source`** (`file` khi nhập Excel, `label` khi đọc nhãn, `admin` khi sửa tay); nhãn được thay địa chỉ `file` hoặc trống, hỏi khi là `admin` | Chấp nhận một migration nhỏ, cột cho phép NULL | Dòng cũ có NULL: không biết nguồn nên phải hỏi. Chỉ ảnh hưởng đơn cũ, còn đơn mới đều có nguồn | **Khuyến nghị.** Quy tắc rõ ràng, test được, sai thì cũng an toàn (hỏi thay vì ghi đè) |
| 2. Không đổi schema: coi địa chỉ là do Excel điền khi nó có tối đa 2 phần trước `Việt Nam` và tỉnh trùng với tỉnh trên nhãn | Admin không bao giờ sửa tay thành địa chỉ ngắn như vậy | Admin sửa tay thành `Xã X, Tỉnh Y`: bị ghi đè không hỏi | Chỉ dựa vào hình dạng chuỗi, đoán sai thì mất dữ liệu admin sửa |
| 3. Không đổi schema: luôn hỏi khi địa chỉ khác nhau | Admin chịu xác nhận gần như mọi đơn | Ngay ngày đầu: màn hình xác nhận dài bằng cả lô | Không đạt mục tiêu tự động |

**Đã chọn cách 1.** Chi tiết thực hiện:

- Migration `0017`: thêm cột `address_source VARCHAR(10) NULL` vào `customer_info`, giá trị `file` | `label` |
  `admin`. Không điền ngược cho dòng cũ (NULL nghĩa là không rõ nguồn, nhãn sẽ hỏi trước khi ghi đè). Sao lưu
  database trước khi chạy migration.
- `_ensure_customer` (`order_import.py:293-304`): khi điền địa chỉ mặc định từ Excel thì đặt `file`.
- `save_customer` (`customers.py:118-121`): chỉ đặt `admin` khi địa chỉ **thực sự thay đổi**. Ô sửa trên trang
  tự lưu cả hàng, nên nếu admin chỉ sửa tên thì địa chỉ cũ được gửi lại nguyên vẹn và nguồn phải giữ nguyên.
- Luồng đọc nhãn: ghi địa chỉ thì đặt `label`. Địa chỉ đang là `label` và khác nhãn mới (ví dụ tải lại phiếu
  của cùng đơn) thì thay luôn, vì nguồn mới cùng loại và mới hơn.
- Bảng quy tắc ghi địa chỉ từ nhãn:

| Địa chỉ hiện có | Nguồn | Hành động |
|---|---|---|
| Trống | bất kỳ | Ghi |
| Giống địa chỉ trên nhãn | bất kỳ | Giữ nguyên |
| Khác | `file` hoặc `label` | Ghi đè, không hỏi |
| Khác | `admin` hoặc NULL | Chờ admin xác nhận |

## Thiết kế đề xuất

**Bộ đọc** `src/shoponline/importers/shipping_label_pdf.py`: kiểm file; với mỗi trang, chuẩn hóa NFC, nhận mẫu
(`Mã vận đơn:` + `Mã đơn hàng:` + `Đến:` là SPX Shopee; `Order ID:` + `Người nhận` là J&T TikTok), đọc
`(platform, order_id, name, address, page_no)` theo các quy tắc ở phần khảo sát; trả thêm danh sách số trang
không đọc được; gộp trang cùng mã đơn, còn mâu thuẫn trong cùng file thì đưa đơn đó vào nhóm cần xem lại.
Thông báo lỗi chỉ nêu số trang và tên trường.

**Ghi dữ liệu:** một hàm dịch vụ áp quy tắc ở tiêu chí 2 và 3, tính lại `province`, `place_key` khi đổi địa chỉ,
đánh dấu đơn chưa có `sales_order`.

**Giao diện** (`/customers`, chỉ admin): khung "Đọc tên, địa chỉ từ phiếu vận đơn PDF", chọn nhiều file. Có chỗ
khác nhau thì hiện trang đối chiếu với ô chọn từng dòng; giá trị đã đọc gửi lại bằng trường ẩn.

## Rủi ro còn lại

- Sàn đổi mẫu nhãn: trang báo "không nhận ra", admin vẫn nhập tay; cần file mẫu mới để thêm bộ đọc.
- Quy tắc nối theo âm tiết có thể sai với từ không phải tiếng Việt bị ngắt giữa chừng (ví dụ tên tòa nhà tiếng
  Anh). Chỉ ảnh hưởng một khoảng trắng trong phần đường; tỉnh vẫn đúng vì lấy từ dòng riêng.
- Tên rất dài ở mẫu SPX có thể xuống dòng; khi đó dòng thứ hai sẽ bị tính vào địa chỉ. Mẫu hiện tại không có
  trường hợp này; admin vẫn sửa được trên `/customers`.

## Câu hỏi chưa giải quyết

Không còn.
