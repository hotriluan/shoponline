# Rà soát toàn vẹn dữ liệu: bất biến xuyên luồng

## Nguồn và giới hạn

- **Nguồn:** DB dev `shoponline_dev`, schema `0011_drive_connection`, chụp 2026-11-23 chiều. Không phải production (không mở được kết nối; chủ dự án chọn dùng DB dev). Dữ liệu: đơn đặt từ 2026-11-11 đến 2026-11-20; 129 đơn, 117 DO đã vào sổ kế toán.
- **Cách chạy:** phiên `default_transaction_read_only = on`, chỉ `SELECT/WITH/SHOW/EXPLAIN`. SQL đầy đủ nằm trong scratchpad (`invariants.sql`, không commit). Chỉ ghi số đếm, không có tên, số điện thoại hay địa chỉ.
- **Điều dev DB không kiểm được:** `sales_history_exported` có 0 dòng nên I7b, I11, I14 trống vì chưa có dữ liệu xác nhận, không phải vì đã được chứng minh an toàn. I15 không kiểm được (`ops.backup_request` rỗng, chưa có lần khôi phục). Cần chạy lại các câu này trên production hoặc bản phục hồi của nó.
- **Phần mã đã đọc:** `accounting/ledger.py`, `accounting/runs.py` (danh sách hàm, các điểm ghi sổ), `reconcile/report_ingest.py` (ghi tiền vô), `importers/settlement_files.py`, `db/models.py`.

## Kết quả

| # | Luồng | Bất biến | Số đếm | Kết luận |
|---|---|---|---:|---|
| I1a | Đơn | Đơn cùng sàn với lô của nó | 0 | Đạt |
| I1b | Đơn | Không trùng `(platform, platform_order_id)` | 0 | Đạt; còn được khóa bằng ràng buộc duy nhất `models.py:107` |
| I2 | Đơn | Mỗi đơn có ít nhất một dòng, số lượng > 0 | 0 vi phạm | Đạt |
| I3a | SO/DO | Một DO không thuộc hai đơn | 0 | Đạt |
| I3b | SO/DO | SO của đơn có trong `sap_so_ref` | 0 | Đạt |
| I3c | SO/DO | Mỗi SO trong `sap_so_ref` khớp một đơn theo PO | 0 | Đạt |
| I3d | SO/DO | Một PO không có hai SO | 0 | Đạt (SO tạo tay trùng PO chưa gặp trong dữ liệu này) |
| I4a | SO/DO | Trạng thái khớp SO/DO (DELIVERED có DO và SO, SO_LINKED có SO, đơn chưa DELIVERED không có DO) | 0 | Đạt |
| I5 | Kế toán | Mỗi DO gửi tối đa một lần | 0 | Đạt theo cấu trúc: `delivery` là khóa chính của sổ (`models.py:386`); chốt hai đợt chồng DO sẽ lỗi khóa thay vì ghi trùng |
| I5a | Kế toán | DO trong sổ đều có đơn trong hệ thống | 0 | Đạt (cả sổ nền 12 DO) |
| I5b | Kế toán | Sổ chỉ trỏ tới đợt FINALIZED | 0 | Đạt |
| I6 | Kế toán | DO đã giao có ngày GI trước lần chốt cuối mà chưa vào sổ | 0 | Đạt |
| I6b | Kế toán | DO đã giao chưa vào sổ, mọi ngày | 0 | Đạt |
| I7a | Lịch sử | Một đơn nằm trong tối đa một file lịch sử | 0 | Đạt (dev chỉ có 1 file, 37 đơn) |
| I7b | Lịch sử | Đơn đã xác nhận nằm trong file của nó | 0 | Chưa kiểm được: không có dòng xác nhận |
| I8 | Lịch sử | Đơn DELIVERED chưa xuất, đặt hơn 45 ngày | 117 chưa xuất, 0 quá 45 ngày | Chưa có dữ liệu để kết luận (chưa xác nhận lần nào trên dev) |
| I9 | Hóa đơn | DO đã giao đều có hóa đơn | 25 thiếu | Giải thích được: cả 25 DO (Shopee 17, TikTok 6, Lazada 2) có ngày GI 2026-11-20, còn hóa đơn mới nhất là 2026-11-19. Thiếu do chưa đọc zrsd003 của ngày đó, không phải mất liên kết |
| I10 | Hóa đơn | Hóa đơn không khớp DO nào | 163 | Bình thường: zrsd003 gồm khách ngoài ba sàn. Chưa đối chiếu được theo khách (cần danh sách sold-to ba sàn trên production) |
| I11 | Tiền vô | Tiền vô đổi sau khi xuất | 0 | Chưa kiểm được: chưa có file lịch sử đã xác nhận |
| I12 | Tiền vô | Dòng quyết toán không khớp đơn nào | Shopee 154, TikTok 112 | Xem phát hiện F1 |
| I13 | Tiền vô | Cùng đơn, số tiền, ngày, khác `line_key` | 0 | Đạt trong dữ liệu này |
| I14 | Xóa | Đơn đã xóa tên khách mà chưa xuất | 0 | Chưa kiểm được: dữ liệu mới (< 90 ngày), nên chưa có đơn bị xóa |
| I14b | Xóa | `customer_info` mồ côi | 0 | Đạt |
| I15 | Khôi phục | Đơn hoặc DO xuất lại sau lần khôi phục | — | Chưa kiểm được: chưa từng khôi phục trên DB này |
| X1 | Đơn | Đơn đã tiến triển nhưng lô chưa chốt | 0 | Đạt |

## Phát hiện

| # | Mức | Luồng | Bằng chứng | Đề xuất |
|---|---|---|---|---|
| F1 | Low (cần xác minh) | Tiền vô | 66 trong 266 dòng quyết toán không khớp đơn có ngày thanh toán từ 2026-11-11 trở đi (Shopee 56, TikTok 10), tức nằm trong khoảng ngày của dữ liệu đơn. 200 dòng còn lại có ngày trước 2026-11-11, hợp lý là đơn đặt trước khi hệ thống nhập. Dữ liệu dev không phân biệt được "đơn đặt trước 2026-11-11" với "mã đơn sai". | Chạy lại trên production, so ngày đặt đơn với mã đơn của 66 dòng (chỉ mã đơn); nếu có đơn tồn tại nhưng khác định dạng mã thì mới là lỗi |
| F2 | Info | Tiền vô | Lazada có 0 dòng quyết toán, 14/14 đơn Lazada DELIVERED không có Tiền Vô. Đã được thiết kế: file Balance Transactions của Lazada không có mã đơn (`importers/settlement_files.py:3,147-149`). | Chấp nhận (quyết định đã có); chỉ cần nhắc lại trong hướng dẫn nếu chưa có |
| F3 | Info | Hóa đơn | 25 DO ngày GI 2026-11-20 chưa có hóa đơn (I9). | Không phải lỗi; ghi để phase 4 so với cách xuất file lịch sử xử lý DO chưa có hóa đơn |

Không có phát hiện mức Critical, High hay Medium từ truy vấn trên dev DB. Chưa kết luận gì về production.

## Việc còn lại để kết luận cho production

1. Chạy lại cùng `invariants.sql` trên production hoặc bản phục hồi của nó (chỉ cần SQL và kết nối chỉ đọc).
2. Thêm các câu SQL "cần chạy" do phase 2–5 chuyển sang (nằm trong file phát hiện của từng phase).
3. I7b, I8, I11, I14, I15 chỉ có nghĩa khi đã có xác nhận lịch sử, dữ liệu quá 90 ngày và lần khôi phục thật.

## Bổ sung: chạy trên production (2026-11-23, kết nối chỉ đọc)

Kết nối bằng SSH tới máy chạy thật, chạy `invariants.sql` qua công cụ chỉ đọc của ứng dụng (phiên read-only, chỉ SELECT; chuỗi kết nối không được in), rồi xóa file tạm trên máy đó. DB: `shoponline`, 157 đơn từ 2026-11-11 đến 2026-11-23. Mọi con số dưới đây là của production.

| # | Số đếm production | Kết luận |
|---|---:|---|
| I1a, I1b, I2, I3a–I3d, I4a, I5a, I5b, I6, I6b | 0 | Đạt |
| I7a, I7b, I11, I13, I14b, X1 | 0 | Đạt (nhưng chưa có file lịch sử nào, xem I7c) |
| I7c | 0 file, 0 đơn | Production chưa từng tạo file lịch sử; I7b, I11 chưa có ý nghĩa |
| I8 | 127 đơn DELIVERED chưa xuất, 0 quá 45 ngày | Chưa kết luận (chưa xác nhận lần nào) |
| I9 | 10 DO đã giao chưa có hóa đơn | Chờ đọc zrsd003 (dev có 25; production có đọc zrsd003 tới 2026-11-23, chưa kiểm ngày GI của 10 DO này) |
| I10 | 163 hóa đơn không khớp DO | Bình thường (khách ngoài ba sàn) |
| I12 | Shopee 154, TikTok 112 dòng quyết toán không khớp đơn | Xem dưới |
| I14 | 26 | Không phải xóa sớm: đều là đơn READY chưa có tên khách (Shopee 25, TikTok 1), đặt từ 2026-11-20 đến 11-23. Trình đọc Shopee và TikTok không lấy tên khách (chỉ Lazada có, `lazada_orders.py:123`), nên tên do người dùng nhập tay; đơn đang chờ nhập |
| I15 | Không có lần khôi phục | `ops.backup_request` chỉ có backup, verify, retry_drive; chưa có `restore` |

**Quyết toán không khớp đơn (F1):** Shopee 149/154 dòng có mã đơn đặt trước 2026-11-11, trước khi hệ thống có đơn đầu tiên (hợp lý: đơn cũ). 5 dòng Shopee còn lại thuộc đơn đặt ngày 2026-11-11, số tiền dương, đã thanh toán 11-14 đến 11-17, nhưng không có đơn trong hệ thống (hệ thống có 6 đơn Shopee ngày 11-11, đơn đầu lúc 10:32). Khả năng cao là đơn đặt sáng 11-11 trước khi hệ thống chạy thật, xử lý tay. Mức: Low, cần chủ dự án xác nhận. TikTok 112 dòng: 69 thanh toán tháng 10 và 43 tháng 11, trước hoặc ngoài khoảng đơn hệ thống nhập.

**Tiền vô so với đơn đã giao:** Shopee 23/90 đơn DELIVERED có dòng quyết toán, TikTok 2/22, Lazada 0/15 (do thiết kế). Phần lớn đơn chưa có tiền vô vì sàn chưa thanh toán; đây là trạng thái, không phải lỗi.

**Hàng đợi SAP:** `read_zrsd001` 24 DONE + 1 FAILED; `read_zrsd004` 26 DONE + 2 FAILED; `read_zrsd003` 3 DONE (id 47, 48, 61). Một số lô có `read_zrsd001` chạy lặp (lô 1 và 3: 3 lần, lô 9 và 12: 2 lần), và không sinh trùng dữ liệu (I3a–I3d bằng 0).
