# Brainstorm: thêm Tax Invoice Doc. từ zrsd003 vào file "Shop Online 2022-2026"

Ngày: 2026-11-19. Nguồn: `docs/zrsd003.XLSX`, `docs/zrsd004.XLSX`, `docs/Shop Online 2022-2026_10.xlsx`, code trong `src/shoponline`.

## Bằng chứng

- `zrsd003` (sheet `Sheet1`, 16 cột, 650 dòng, Billing Date 02–19/11/2026) có các cột `Billing Type`, `Billing Date`, `Billing Doc.`, `OD Doc.`, `Tax Invoice Doc.`, `Bill-to`, `Name`, `Net Value`, `Tax (VND)`… Không có dòng tổng.
- 650 dòng có 650 `OD Doc.` khác nhau: mỗi DO đúng một hóa đơn. File chứa mọi khách của sales org (Shopee 179, TIKTOK 39, LAZADA 25, còn lại là khách doanh nghiệp).
- `OD Doc.` chính là `Delivery` của `zrsd004`. Ví dụ DO `1910061168` (TIKTOK, Bill-to `1200001146`) có Tax Invoice Doc. `7914`; DO `1910061169` (Shopee, `1200001145`) có `7903`. Tax Invoice Doc. là chuỗi số ngắn, giữ dạng text.
- Database đã lưu DO của mỗi đơn ở `sales_order.do_number` (gán khi nhập zrsd004, `reconcile/so_link.py` `mark_delivered`). Vậy nối trực tiếp `zrsd003.OD Doc.` = `sales_order.do_number`; không cần đọc lại zrsd004.
- Bộ dựng file: `exports/sales_history_workbook.py` (17 cột sheet1 + cột 18 `Mã đơn`). Đơn thiếu dữ liệu đi vào `blocked` với `Reason(kind, text)`.
- Robot hiện chỉ có `read_zrsd001`, `read_zrsd004` (khung chung `transactions/report_screen.py`, control id trong `config/sap_screens.yaml`, nhập kết quả ở `saprobot/worker.py`). Chưa có bản ghi VBS của màn hình chọn ZRSD003.

## Contract

**Outcome:** File `SHOP ONLINE LỊCH SỬ ddmmyy.xlsx` có thêm cột 19 `Tax Invoice Doc.` sau `Mã đơn`, lấy từ zrsd003 theo DO của đơn. Robot đọc zrsd003 từ SAP và nhập vào database.

**Quyết định của người dùng (19/11/2026):**
- Nguồn: robot tự đọc ZRSD003, **và** có ô upload tay zrsd003 ở trang Báo cáo SAP làm đường dự phòng khi robot hỏng (bổ sung 19/11, cùng bộ nhập với robot).
- Hóa đơn luôn xuất **sau** khi làm DO. Đơn mới có DO mà chưa có hóa đơn là trạng thái bình thường, không phải lỗi.
- Đơn đã có DO mà zrsd003 chưa có hóa đơn: **chặn đơn**, lý do "DO … chưa có Tax Invoice Doc. (chờ xuất hóa đơn rồi đọc zrsd003)".
- Vị trí: cột 19, sau `Mã đơn`; 17 cột gốc và cột 18 giữ nguyên.

**Constraints:**
- Chỉ đọc SAP (job `writes=False`), đi qua guard và hàng đợi robot như zrsd001/zrsd004.
- Màn hình ZRSD003 không lọc được theo Bill-to (xem mục "Kết quả bản ghi"). Robot đọc cả sales office 1401 theo khoảng Billing Date; **bộ nhập** lọc theo Bill-to của các sàn (`platform_setting.sap_customer`) và chỉ lưu những dòng đó. File gốc chứa dữ liệu khách doanh nghiệp nên bị xóa ngay sau khi nhập, như zrsd001 (`retention.discard_unused`).
- Lưu thêm bảng mới (gợi ý `sap_tax_invoice`: `delivery` PK, `tax_invoice_doc`, `billing_doc`, `billing_date`, `bill_to`, `import_batch_id`), upsert theo `delivery`. Migration cần backup DB trước khi chạy.
- File zrsd003 do robot tải về theo quy định lưu trữ hiện có (`maintenance/retention.py`).

**Non-goals:**
- Không thêm cột Tax Invoice vào file kế toán `SHOP ONLINE ddmmyy.xlsx` (zrsd004).
- Không đổi 17 cột gốc, không tự điền lại các file đã xác nhận trước đây.
- Không xử lý hóa đơn hủy/điều chỉnh (Billing Type khác `ZBA1`); chỉ nhận `ZBA1`.

**Acceptance criteria:**
1. Nhập file `docs/zrsd003.XLSX` lưu được Tax Invoice của các DO thuộc Bill-to sàn; dòng khách khác bị bỏ qua; nhập lại cùng file không tạo trùng.
2. Thiếu cột bắt buộc (`OD Doc.`, `Tax Invoice Doc.`, `Bill-to`, `Billing Date`) thì file bị từ chối với thông báo rõ.
3. Trang **File Shop Online**: đơn có DO mà chưa có hóa đơn nằm ở **Đơn bị chặn**; còn đơn bị chặn thì không tải được file (hành vi hiện có).
4. File tải về có cột 19 `Tax Invoice Doc.` đúng số theo DO (ví dụ DO `1910061168` → `7914`), ghi dạng text.
5. Robot có job `read_zrsd003` chạy được từ trang Robot (và từ nút trên trang File Shop Online): Sales Org 1000, Sales Office 1401, Billing Date từ–đến, để mặc định "Exist" và "SD". Kết quả tự nhập vào database, chỉ giữ dòng có Bill-to của sàn; file gốc không còn trên đĩa sau khi nhập.
6. Trang Báo cáo SAP có ô tải zrsd003 (chỉ admin); file tải tay và file robot đi qua cùng một hàm nhập, kết quả giống nhau.
7. Test cho bộ nhập, lý do chặn mới và cột 19; tài liệu `docs/daily-operations.md` mục "Xuất dòng cho file Shop Online" cập nhật bước đọc zrsd003.

## Hướng làm

1. Bộ nhập `read_zrsd003` trong `importers/sap_reports.py` (dùng `read_table`), ingest upsert vào bảng mới.
2. Job robot `read_zrsd003`: transaction mới theo khuôn `read_zrsd004`, control id thêm vào `config/sap_screens.yaml`, hậu xử lý `_after_zrsd003` trong worker.
3. Khoảng ngày khi kích từ trang File Shop Online: từ ngày đặt sớm nhất của các đơn đang thiếu hóa đơn tới hôm nay, một job cho mọi sàn. Vì hóa đơn xuất sau DO và DO sau ngày đặt, Billing Date luôn ≥ ngày đặt nên khoảng này không sót hóa đơn.
3b. Ô upload zrsd003 ở `web/routes/sap_reports.py` theo khuôn `upload_zrsd004`, gọi cùng hàm ingest.
4. `collect_rows`: tra Tax Invoice theo `do_number`, thiếu thì thêm `Reason("tax_invoice", …)`; `HistoryRow.tax_invoice_doc`; `COLUMNS` thêm `Tax Invoice Doc.`.

Better approaches: nối qua `sales_order.do_number` thay vì nối qua file zrsd004 như đề xuất ban đầu — cùng khóa (Delivery) nhưng database đã giữ sẵn DO của từng đơn, nên không phải đọc/giữ lại zrsd004 khi xuất file lịch sử.

## Rủi ro

- Bản ghi SAP đã có (19/11/2026), không còn chặn job robot.
- File gốc zrsd003 chứa tên và mã số thuế của khách doanh nghiệp: chỉ dữ liệu của sàn được lưu, file bị xóa ngay sau khi nhập.
- Một SO tách nhiều DO: `do_number` chỉ giữ DO đầu, nên chỉ lấy hóa đơn của DO đó. Hiện chưa thấy trường hợp này.
- Hóa đơn thường xuất cùng ngày GI (mẫu: 13/11), nhưng nếu xuất trễ thì đơn bị chặn tới khi robot đọc lại.

## Kết quả bản ghi ZRSD003 (19/11/2026)

Nguồn: `docs/sap-recordings/zrsd003/Script1.vbs`, 7 ảnh chụp và `zrsd003.XLSX` (gitignore).

- Tiêu đề màn hình: "Report Of Monitoring Tax Invoice". Các ô lọc: Sales Organization `ctxtP_VKORG` (gõ `1000` rồi Enter), Sales Office `ctxtP_VKBUR-LOW` (`1401`, Enter), Billing Type, Billing Doc, Billing Date `ctxtP_FKDAT-LOW` / `ctxtP_FKDAT-HIGH`, Tax Classification, Doc. Currency, Storage Location. Radio "Tax Invoice for Billing Status" mặc định **Exist**; "Report Type" mặc định **SD**. **Không có ô Bill-to/khách hàng.**
- Execute: `wnd[0]/tbar[1]/btn[8]`. Lưới: `wnd[0]/usr/cntlGRID1/shellcont/shell/shellcont[1]/shell` (cùng ID với zrsd001/zrsd004). Cột chuột phải: `TAXSR` (Tax Invoice Doc.). Xuất: `&XXL` → Select Spreadsheet (Continue) → Save As → hai hộp SAP GUI Security (tạo file, mở file). Cả chuỗi này giống zrsd004, `export_result` và `config/sap_popups.yaml` hiện có đã xử lý.
- File xuất có cùng 16 cột với `docs/zrsd003.XLSX`.
- Sau Enter ở ô Sales Org và Sales Office, màn hình được nạp lại; robot phải gửi Enter sau hai ô này như bản ghi.

### Phương án lọc khi không có Bill-to

| Phương án | Giả định chịu lực | Hỏng đầu tiên khi |
|---|---|---|
| **A. Đọc cả sales office 1401 theo Billing Date, lọc Bill-to trong bộ nhập (chọn)** | Một tháng chỉ ~650 hóa đơn cho cả 1401, nên đọc rộng vẫn nhẹ | Khoảng ngày rất dài (vài năm) làm file lớn; vẫn chạy được, chỉ chậm |
| B. Thêm bước lọc ALV theo cột Bill-to sau khi chạy | Thao tác lọc trên lưới ổn định khi phát lại | Chưa ghi các bước này, đổi layout ALV là gãy; thêm hộp thoại phải duyệt |
| C. Lọc theo khoảng Billing Doc | Biết trước số billing của sàn | Không biết trước, nên không dùng được |

A là phương án nhỏ nhất, không cần ghi thêm, và cùng một bộ nhập phục vụ cả robot lẫn upload tay (file tải tay từ SAP cũng không lọc được theo Bill-to). Một job robot cho mọi sàn, khóa job theo khoảng ngày (`read_zrsd003:{từ}:{đến}`), thay vì một job mỗi sàn như dự định trước.

Better approaches: none — phương án A là cách duy nhất không cần ghi thêm bước SAP (bằng chứng: bản ghi không có ô Bill-to).

### Còn thiếu trong bản ghi (không chặn)

- Câu ở thanh trạng thái khi không có dữ liệu. Code đang nhận "no data to display". Nếu ZRSD003 báo câu khác, job sẽ dừng ở trạng thái lỗi chứ không nhập sai. Thực tế gần như không xảy ra vì sales office 1401 có hóa đơn hầu như mỗi ngày làm việc. Lần đầu gặp thì chụp lại và thêm câu đó.
- ID của hai radio (Exist, SD). Robot để nguyên mặc định nên không cần, với điều kiện user AL17016 không lưu variant làm đổi mặc định.

## Yêu cầu bản ghi ZRSD003 (đã gửi người dùng)

Ghi trên Production AEP/300, user robot AL17016, ngôn ngữ EN, cùng máy/phiên bản SAP GUI như các bản ghi 12/11/2026. Lưu ngoài git (thư mục `docs/sap-recordings/` đã bị gitignore):

- `docs/sap-recordings/ZRSD003.vbs`: `/NZRSD003` → gõ Bill-to `1200001145` → gõ Billing Date từ–đến (gõ tay `dd.mm.yyyy`, không chọn lịch F4) → F8.
- `docs/sap-recordings/exportexcel/exportzrsd003.vbs`: trên lưới kết quả, chuột phải một ô cột `OD Doc.` → Spreadsheet… → Continue.
- Ảnh chụp: màn hình chọn đầy đủ (thấy hết các ô), màn hình chọn sau khi bấm F1 → Technical Information ở ô Bill-to và ô Billing Date, lưới kết quả, thanh trạng thái khi lọc một ngày không có hóa đơn, và mọi hộp thoại hiện ra khi xuất.
- File Excel xuất ra từ bản ghi: `docs/sap-recordings/exportexcel/zrsd003.XLSX`.

Code cần từ bản ghi: ID ô Bill-to, ô Billing Date LOW và HIGH, ô Sales Org nếu có và có bắt buộc không, nút Execute, ID lưới kết quả, tên kỹ thuật của cột được chuột phải, câu thông báo khi không có dữ liệu, các hộp thoại chưa có trong `config/sap_popups.yaml`.

## Câu hỏi còn mở

Không còn câu hỏi chặn. Phần robot có thể đưa vào plan cùng phần nhập dữ liệu.
