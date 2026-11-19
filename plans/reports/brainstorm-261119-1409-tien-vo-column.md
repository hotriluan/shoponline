# Brainstorm: cột "Tiền Vô" trong file Shop Online 2022-2026

Ngày: 2026-11-19. Trạng thái: đã chốt hướng, chờ lập plan.

## Kết quả phân tích file mẫu (`docs/tienvo/`)

| Sàn | File / sheet | Cột tiền | Khóa theo đơn | Dùng được? |
|---|---|---|---|---|
| Shopee | `shopee.xlsx`, sheet "Transaction Report", header ở dòng 18 | "Số tiền" | "Mã đơn hàng" | **Có.** 174 dòng "Doanh Thu Đơn Hàng / Tiền vào", 3 dòng "Doanh Thu Đơn Hàng / Tiền ra" (-2.700, đơn giao thất bại), 3 dòng "Điều chỉnh" có Mã đơn hàng "-". Mã đơn khớp mã trong file đơn Shopee và zrsd001 đang nhập (ví dụ 12/12 mã trong `ĐƠN HÀNG ONLINE SHOPEE 111126.xlsx`). |
| TikTok | `tiktok.xlsx`, sheet "Chi tiết đơn hàng", header dòng 1 | "Tổng số tiền quyết toán" (chữ số dạng text) | "ID đơn hàng/điều chỉnh" | **Có.** 115 dòng, tất cả "Đơn hàng", không trùng ID; 21 đơn quyết toán 0 (hoàn tiền toàn bộ). ID 18 chữ số, cùng dạng "Order ID" của importer TikTok. File mẫu không trùng kỳ với file đơn có sẵn nên chưa đối chiếu được mã thật. |
| Lazada | `lazada.xlsx`, sheet "Balance Transactions" | "Amount" | **Không có** | **Không.** Chỉ có Settlement gộp theo ngày ("Statement No. …-2026-1116"), Penalty và Auto Withdrawal. Không gắn được vào từng đơn. |

Quyết toán đến sau ngày đặt khoảng 5–10 ngày (TikTok đặt 13/11, quyết toán 18/11; Shopee đặt 28/10, tiền vào 01/11).

## Brainstorm contract

**Outcome:** Người dùng upload file export của Shopee/TikTok vào chương trình; file "Dòng cho file Shop Online 2022-2026" có thêm cột **Tiền Vô** (cột T, sau "Tax Invoice Doc.") ghi tổng tiền sàn trả cho đơn.

**Constraints:**
- Giữ cơ chế hiện có: file tải được với các đơn đủ dữ liệu; đơn thiếu nằm ở danh sách riêng và vào lần tải sau (`collect_rows` → `blocked`).
- File gốc upload bị xóa ngay sau khi nhập, như zrsd003 (`docs/security-and-data-retention.md`).
- Upload lại file trùng kỳ không làm cộng trùng tiền.

**Quyết định của người dùng:**
- Đơn Shopee/TikTok chưa có tiền vô: **không vào file lần này**, nằm ở mục riêng "Đơn chờ tiền vô" trên trang; file vẫn tải được với các đơn đã có tiền vô. Đơn tự vào lần tải sau khi đã upload file sàn có đơn đó.
- Lazada: cột Tiền Vô **để trống**, không chờ.
- Đơn nhiều dòng: tiền vô ghi ở **dòng đầu của đơn**, các dòng sau để trống.
- Shopee "Điều chỉnh" (Mã đơn hàng "-"): **không tính**.

**Non-goals:** đọc file Balance Transactions của Lazada; đối soát tiền vô với ngân hàng hoặc với "Customer paid"; tự tải file từ sàn; điền tiền vô cho đơn đã xác nhận dán trước đây.

**Acceptance criteria:**
1. Trang Shop Online có form upload file tiền vô; chương trình nhận ra Shopee hay TikTok từ header, từ chối file khác (kể cả Balance Transactions Lazada) với thông báo rõ.
2. Upload báo số đơn đọc được, mới, cập nhật; upload lại cùng file không đổi tổng.
3. File xuất có cột 20 "Tiền Vô", định dạng `#,##0`; đơn Shopee = tổng "Số tiền" các dòng có Mã đơn hàng đó; đơn TikTok = tổng "Tổng số tiền quyết toán" theo ID; đơn Lazada trống; chỉ dòng đầu của đơn có số.
4. Đơn Shopee/TikTok chưa có tiền vô không có trong file, hiện ở mục "Đơn chờ tiền vô" kèm số lượng và chỗ upload; đơn hoàn tiền (tiền vô 0) vẫn xuất với số 0.
5. Test cho hai reader, tính tổng, cột mới và việc chặn; docs vận hành mô tả cách upload.

## Hướng thiết kế đề xuất

- **Reader** `importers/settlement_files.py`: tìm header theo tên cột (Shopee header không ở dòng 1), trả về các dòng (platform, mã đơn, số tiền, thời điểm, khóa dòng). Shopee bỏ dòng Mã đơn "-". TikTok parse số từ text.
- **Lưu trữ**: bảng mới lưu từng dòng giao dịch có khóa duy nhất (TikTok: ID đơn hàng/điều chỉnh; Shopee: mã đơn + thời gian + loại + số tiền), upsert khi upload. Tổng theo đơn tính lúc xuất. Lưu theo dòng thay vì theo tổng để upload các kỳ chồng nhau không cộng trùng mà cũng không mất dòng của kỳ trước. Cần một migration Alembic.
- **Xuất**: `collect_rows` thêm lý do chặn mới (ví dụ `SETTLEMENT`, chỉ cho SHOPEE/TIKTOK), `HistoryRow` thêm tiền vô, `COLUMNS` thêm "Tiền Vô", `MONEY_COLUMNS` thêm "T".
- **Trang**: tách các đơn có lý do duy nhất là chờ tiền vô ra một hộp riêng "Đơn chờ tiền vô" (giống hộp chờ Tax Invoice), kèm form upload; đơn thiếu cả thứ khác vẫn ở bảng "Đơn bị chặn".

## Rủi ro còn lại

- Đơn mà sàn không bao giờ quyết toán (thất lạc, tranh chấp) sẽ nằm mãi ở "Đơn chờ tiền vô". Danh sách hiện rõ để người dùng xử lý; chưa thêm nút bỏ qua vì chưa có yêu cầu.
- Định dạng export của sàn có thể đổi tên cột; reader báo lỗi tên cột thiếu thay vì đoán.
- Mã đơn TikTok chưa đối chiếu được với dữ liệu thật trong DB; cần kiểm tra khi chạy thử.
