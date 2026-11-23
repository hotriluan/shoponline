# Rà soát toàn vẹn dữ liệu: đơn hàng, SO/DO và báo cáo SAP (plan 261111-0755)

## Nguồn và giới hạn

- Soi mã và test của `261111-0755-shopee-excel-to-sap-order-flow` (đơn hàng, SO/DO, báo cáo SAP, hàng đợi `sap_job`), đối chiếu với DB dev.
- **Mọi số đếm là "dev DB, 2026-11-23"**, không phải production. Dữ liệu dev trải từ 2026-11-11 đến 2026-11-20; `sales_history_exported` có 0 dòng nên luồng file lịch sử không thuộc phase này. Chín đơn READY của lô 2026-11-20 chưa xác nhận (lô còn đang xử lý), không tính là lỗi.
- Test DB (`*_test`) không mở được trên máy dev (`OperationalError`), nên test tái hiện chỉ chạy được cho hàm thuần (đọc file); phần cần DB ghi "chưa tái hiện, lập luận từ mã".
- Không sửa `src/`, `tests/`, `migrations/`, `docs/`. Không có PII trong file này; chỉ có mã đơn mẫu.

## Trả lời 6 câu hỏi trùng/sót

1. **Nhập lại cùng file hoặc hai file chồng ngày.** An toàn về trùng: khóa `(platform, platform_order_id)` là UNIQUE (`db/models.py:107`), và `import_orders` tìm đơn theo khóa này, không theo lô (`importers/order_import.py:151-155`). Nhập lại đúng nội dung: `unchanged` (test `test_import_twice_changes_nothing`; dev có 3 lần nhập lại cùng ngày, đều `new=0, updated=0`). Đơn còn mở mà nội dung đổi: ghi đè item (`order_import.py:180-196`). Đơn đã có SO, đã giao hoặc đã hủy: **bỏ qua im lặng** (`order_import.py:178-179`), kể cả khi sàn đổi số lượng. Xem phát hiện 5. Đơn đổi trạng thái hoặc bị hủy trên sàn: hệ thống không có tín hiệu từ sàn; chỉ admin hủy tay (`web/routes/orders.py:65`). Xem phát hiện 1.
2. **Một đơn thuộc hai lô?** Không, vì khóa đơn toàn cục. Nhưng đơn nhập lần đầu vào lô D1 và xuất hiện lại trong file của D2 vẫn nằm ở lô D1 và chỉ được đếm `unchanged` (`order_import.py:178-179`, không có dòng nào gán lại `order_batch_id`). Lô D2 không có đơn đó, không báo. Đơn nhập ngày D nhưng giao ngày D+1 nằm ở lô D (ngày xử lý), và `gi_date` của lô là ngày làm việc kế tiếp (`get_or_create_batch`, dòng 41-52). Xem phát hiện 4. Dev: 0 đơn có ngày đặt lệch quá 3 ngày so với ngày lô (SQL #8), nên chưa thấy ở dev.
3. **Đơn nhiều sản phẩm.** Shopee và Lazada: dòng thiếu mã đơn làm cả file bị từ chối (`shopee_orders.py:55-56`, `lazada_orders.py:77-78`). TikTok: dòng có mã đơn rỗng hoặc không phải chữ số **bị bỏ im lặng** (`tiktok_orders.py:58-60`). Đã tái hiện bằng test trong scratchpad. Mọi dòng cùng mã đơn gộp vào một đơn, không bỏ dòng (`shopee_orders.py:70-78`); Lazada gộp theo `(sản phẩm, phân loại, giá, trợ giá)` và đếm số dòng làm số lượng (`lazada_orders.py:99-100`). Dev: 4 đơn có nhiều dòng hàng. Commit `aad031b` chỉ là test về file đơn hàng **đầu ra** (các dòng sau để trống cột đơn, `exports/order_workbook.py:88-92`), không phải đầu vào.
4. **SKU chưa ánh xạ.** Đơn chuyển `MAPPING_ERROR`, **không** vào file đơn hàng (`order_workbook.py:63-64`, chỉ đếm `excluded`), không bao giờ xuất mã trống. An toàn khi xuất; nhưng sau khi xác nhận lô, đơn này không nằm trong danh sách "READY chưa có SO" (`so_link.py:247-250` chỉ lấy READY). Xem phát hiện 7. Dev: 0 đơn mở nào có dòng thiếu mã (SQL #9).
5. **Nhiều SO, nhiều DO, SO tạo tay, "No data", đọc lại cùng khoảng ngày.**
   - Nhiều SO cùng PO No: `link_orders` bỏ qua, `batch_report` liệt kê vào `duplicate_po` (`so_link.py:150`, `:262-266`). Dev: 0 PO trùng.
   - `sap_so_ref` khóa theo số SO, đọc lại: so chữ ký, `unchanged` hoặc cập nhật tại chỗ (`so_link.py:72-99`); không trùng, không ghi đè mất dòng.
   - **Nhiều DO cho một SO: chỉ DO đầu được lưu** vào `sales_order.do_number` (`so_link.py:304-306`, `:314`); DO thứ hai không đến sổ hóa đơn/file lịch sử theo đơn. Xem phát hiện 3. Dev: không có trường hợp (số DO trùng trên đơn = 0; SQL #6).
   - SO tạo tay (nối tay): `link_manually` kiểm tra SO tồn tại, đơn chưa có SO, SO chưa gắn đơn khác (`so_link.py:164-188`). An toàn ở tầng mã, nhưng DB không chặn (phát hiện 8).
   - zrsd001 "No data": job `FAILED` có lý do, **không** nhập gì, hiện ra trên trang robot; nhưng tính vào bộ đếm lỗi liên tiếp của robot (`saprobot/worker.py:363-368`, `sapjobs/queue.py:287-299`). Phát hiện 11. zrsd004/zrsd003 "No data": `DONE`, trung tính (`worker.py:127-129`, `:363-365`).
   - Đọc lại cùng khoảng ngày: SO an toàn như trên; `mark_delivered` chỉ chạm đơn `SO_LINKED`, nên đọc lại không đổi gì; zrsd003 và tiền vô dùng `ON CONFLICT DO UPDATE` theo khóa (`report_ingest.py:407-421`, `:483-494`). Mỗi lần đọc lại tạo thêm một `import_batch` và một file lưu, chỉ tốn chỗ.
6. **Hàng đợi `sap_job`.** An toàn: chỉ mục duy nhất từng phần theo `dedupe_key` trên trạng thái chưa xong (`migrations/versions/0004_sap_job.py:46-52`), `claim` dùng `FOR UPDATE SKIP LOCKED` (`queue.py:119`). Việc đọc chết giữa chừng quay về `PENDING` lúc robot khởi động (`queue.py:224-239`); kết quả nhập cùng một giao dịch với `complete` (`worker.py:420-423`), nên chạy lại không ghi hai lần dữ liệu SO (chữ ký) và `mark_delivered` chỉ chạm `SO_LINKED`. Rủi ro còn lại: web tải tay và robot cùng nhập một SO mới đồng thời thì một bên gặp `IntegrityError` (khóa chính `sap_so_ref`), rollback sạch, job `FAILED` có thể chạy lại. Mức Low (phát hiện 9).

## Bảng phát hiện

Cột "Lens": FM = Failure Mode, AD = Assumption Destroyer, TS = trùng/sót dữ liệu, SC = Scope & Complexity (không có phát hiện nào vì phạm vi là yêu cầu, không phải phát hiện); SA = Security Adversary (chỉ xét dữ liệu bị lộ/ghi nhầm, không có phát hiện vượt phạm vi toàn vẹn).

| # | Mức | Luồng | Lens | Phát hiện | Bằng chứng | Đề xuất |
|---|-----|-------|------|-----------|------------|---------|
| 1 | High | SO/DO, file kế toán | FM, TS | Đơn đã hủy mà SO vẫn còn trong SAP: không có cảnh báo, và nếu SO có DO thì DO vẫn vào file kế toán kèm mã đơn đã hủy | `reconcile/so_link.py:143-146` (chỉ nối đơn OPEN), `:252-261` (SO có PO khớp một đơn của sàn nên không vào `unmatched_sos`), `:269` (bỏ qua đơn CANCELLED khi so giá trị), `:313` (`mark_delivered` chỉ đơn `SO_LINKED`), `exports/accounting_workbook.py:54-58` (tra cứu theo số SO, không xét trạng thái đơn). Dev DB, 2026-11-23: 2 đơn CANCELLED, một có SO đã nối, một có SO (`sap_so_ref`) không còn nối với đơn nào; SQL #1, #2 đều ra 2 và 1. Không có DO cho chúng trong sổ đã gửi. Tái hiện: chưa (cần test DB) | `/ak-fix`: `batch_report` thêm mục "SO của đơn đã hủy"; `lookup` của file kế toán thêm cảnh báo khi đơn CANCELLED |
| 2 | High | SO/DO | AD | 14,5% đơn đã nối có giá trị SO khác giá trị tính từ file sàn, vẫn được giao và đưa kế toán: `batch_report` chỉ báo, không chặn | Dev DB, 2026-11-23: 17/117 đơn có SO nối và không hủy có `net_value_incl` khác `Σ(giá gốc − trợ giá) × số lượng` (SQL #11): Lazada 8, TikTok 5, Shopee 4. 13 đơn có trợ giá, SO cao hơn 300 đến 99.999 đồng; 4 đơn Shopee lệch ±1 đồng. Mã: `so_link.py:268-296` (chỉ danh sách), `:303-318` và `accounting/runs.py:99-110` không kiểm lệch giá | Hỏi chủ dự án về Giả định 1 và 2 (xem Validation Log). Nếu đúng là lệch thật: `/ak-fix` hoặc plan nhỏ thêm cổng chặn/ghi nhận chấp nhận lệch trước khi gửi kế toán. Lệch ±1 đồng nên có dung sai làm tròn |
| 3 | Medium | SO/DO | TS | Một SO nhiều DO: chỉ DO đầu được lưu; DO thứ hai không vào hóa đơn/tiến độ theo đơn | `so_link.py:304-306` (`setdefault` giữ DO đầu), `:314`; `db/models.py:118` (`do_number` một cột); `exports/sales_history_workbook.py:183,228`, `reconcile/order_progress.py:33,67` (tra theo `do_number`). Dev: 0 trường hợp (số DO trùng 0). File kế toán lấy dòng thẳng từ zrsd004 nên DO thứ hai vẫn vào file kế toán | Cần SQL #6 trên production để biết có DO thứ hai không; nếu có, bảng DO riêng. Tạm thời: cảnh báo khi zrsd004 có hai DO cho một SO |
| 4 | Medium | Đơn hàng | TS | Đơn đã có ở lô D1 mà xuất hiện trong file nhập cho D2 vẫn ở lô D1, chỉ đếm `unchanged`, lô D2 thiếu đơn mà không báo | `importers/order_import.py:178-179` (`unchanged`), `:133-139` (tìm đơn không theo lô); không có chỗ nào gán lại `order_batch_id`. Dev: 3 lần nhập lại, tất cả cùng ngày (event_log `file_imported`), nên chưa thấy; tái hiện: chưa (cần test DB) | Hiện số đơn "đã có ở lô khác" trên trang kết quả nhập, kèm ngày lô cũ |
| 5 | Medium | Đơn hàng | FM, TS | Sàn đổi nội dung đơn sau khi đã có SO (số lượng, giá): file nhập lại bị bỏ qua, `batch_report` so SO với dữ liệu đơn cũ nên không bao giờ thấy lệch | `order_import.py:178-179` (đơn không còn OPEN bỏ qua im lặng), `so_link.py:274-296` (so SO với `order.items` đã cũ) | Nếu nội dung file khác đơn đã có SO, ghi sự kiện `order_changed_after_so` và hiện trên trang lô (không ghi đè) |
| 6 | Medium | Đơn hàng | TS | TikTok: dòng có mã đơn rỗng hoặc không phải chữ số bị bỏ im lặng, đơn mất dòng hàng hoặc mất cả đơn mà không báo | `importers/tiktok_orders.py:58-60`. Tái hiện thành công trong scratchpad (`repro_orders.py`, test 1: 3 dòng vào, 1 dòng ra, không lỗi). Ghi chú: mã đơn là số trong ô Excel (float) mất chữ số từ chữ số thứ 16 (`excel_table.py:142-143`; test 2) nhưng chỉ khi file đã bị Excel lưu số, và không phát hiện được ở mã | Chỉ bỏ dòng mô tả (dòng 2) và dòng trống hẳn; dòng có dữ liệu mà mã đơn sai thì từ chối cả file, như Shopee/Lazada |
| 7 | Medium | Đơn hàng, SO | TS | Đơn `MAPPING_ERROR`/`NEED_REVIEW` không vào file đơn hàng, và sau khi xác nhận lô không nằm trong "đơn READY chưa có SO", nên có thể không bao giờ có SO mà không ai thấy | `exports/order_workbook.py:63-64,116`, `so_link.py:247-250` (`missing_so` chỉ READY), `web/routes/batches.py:90-92` (có hiện số "bị loại" và `open_orders` trên trang lô, nhưng không có cảnh báo khi xác nhận). Dev: 0 đơn trong trạng thái này (SQL #5) | `missing_so` lấy mọi đơn OPEN chưa có SO; chặn hoặc cảnh báo ở nút xác nhận lô khi còn đơn bị loại |
| 8 | Low | SO/DO | TS | `sales_order.so_number` và `do_number` không có ràng buộc UNIQUE; duy nhất chỉ do mã bảo đảm | `db/models.py:117-118` (chỉ chỉ mục thường), `migrations/versions/0002_core_schema.py:125`, `so_link.py:139-140,150,173-175`, `accounting_workbook.py:55` (`scalar` lấy dòng đầu nếu trùng). Dev: 0 SO trùng, 0 DO trùng (SQL #6) | Ràng buộc UNIQUE từng phần (`WHERE so_number IS NOT NULL`) khi có plan sửa; chấp nhận được trước mắt |
| 9 | Low | Đơn hàng, SO | FM | Hai người cùng tải file chồng nhau, hoặc web và robot cùng nhập SO mới: một bên gặp `IntegrityError`, rollback toàn bộ, không hỏng dữ liệu | `order_import.py:41-52,151-176` (đọc rồi chèn, không khóa), `so_link.py:80-85`. Khóa UNIQUE chặn trùng nên chỉ là lỗi 500 | Chấp nhận rủi ro; ghi trong sổ tay vận hành |
| 10 | Low | Đơn hàng | TS | Tải file đơn hàng hai lần trước khi đọc zrsd001: file thứ hai lại liệt kê các đơn READY đã nhập SO, sales admin có thể tạo SO hai lần; chỉ bị bắt sau khi xác nhận lô và đọc zrsd001 (`duplicate_po`) | `exports/order_workbook.py:63` (mọi READY, không biết đã nhập SO chưa), `web/routes/batches.py:127-146`, `so_link.py:262-266`. Dev: 0 PO trùng | Chấp nhận; nhắc trong sổ tay |
| 11 | Low | SO/DO | FM | zrsd001 "No data" tính như lỗi robot và dồn vào bộ đếm lỗi liên tiếp: vài lô chưa có SO liên tiếp có thể tự dừng robot | `saprobot/worker.py:363-368`, `:462` (`record_outcome`), `sapjobs/queue.py:287-299`. Dev: 1 việc `read_zrsd001` FAILED vì NoReportData (việc #35) | Coi "No data" của zrsd001 là trung tính khi lô chưa có SO, hoặc chấp nhận |
| 12 | Low | SO/DO | TS | `sap_so_ref` không bao giờ bị xóa: SO bị hủy/tạo lại trong SAP với cùng PO No để lại hai bản, `link_orders` bỏ qua đơn đó mãi và chỉ nối tay được | `so_link.py:71-100` (chỉ upsert), `:150` (`len(refs) != 1`). Dev: 0 PO trùng | Chấp nhận: `duplicate_po` đã báo, nối tay là đường xử lý |

Tổng: 2 High, 5 Medium, 5 Low (12 phát hiện, dưới mức 15).

Ghi chú khi phân xử: bỏ phát hiện "đơn do sàn hủy không có tín hiệu" thành một dòng riêng vì cùng nguyên nhân với phát hiện 1 (hệ thống chỉ biết hủy khi admin bấm); bỏ "mật khẩu/quyền SAP" vì thuộc bảo mật ngoài phạm vi toàn vẹn dữ liệu.

## Kết quả test tái hiện

File `C:\Users\luanh\AppData\Local\Temp\claude\657bf492868ad14a\d38a5670-5b61-42dd-a5e1-cb21cd4008fc\scratchpad\repro_orders.py`, chạy `uv run pytest <file> --rootdir c:/dev/shoponline`: **2 passed**.

- `test_blank_or_nondigit_order_id_row_is_dropped_without_error`: file TikTok 3 dòng (một mã hợp lệ, một mã rỗng, một mã `5871X`) đọc ra 1 đơn 1 dòng, không lỗi. Xác nhận phát hiện 6.
- `test_numeric_cell_order_id_loses_digits`: ô số 18 chữ số qua `cell_text` không giữ nguyên. Xác nhận ghi chú cuối phát hiện 6.
- Phát hiện 1 đến 5, 7 chưa tái hiện: cần DB test, hiện `tests/reconcile/test_so_link.py` không chạy được trên máy dev (lỗi kết nối test DB). Kết luận dựa vào mã và số đếm dev.

## SQL cần chạy (chỉ đọc, dành cho phase 7, đã chạy trên dev DB, 2026-11-23)

```sql
-- #1 đơn CANCELLED còn SO hoặc còn SO trong zrsd001            -- dev: 2
SELECT count(*) FROM sales_order o WHERE o.status='CANCELLED' AND (o.so_number IS NOT NULL
  OR EXISTS (SELECT 1 FROM sap_so_ref r WHERE r.po_no=o.platform_order_id));
-- #2 SO trong sap_so_ref không nối với đơn nào                  -- dev: 1
SELECT r.so_number, r.po_no, r.doc_date FROM sap_so_ref r
 WHERE NOT EXISTS (SELECT 1 FROM sales_order o WHERE o.so_number=r.so_number);
-- #3 SO có ngày chứng từ khác ngày lô của đơn đã nối            -- dev: 0
SELECT count(*) FROM sales_order o JOIN order_batch b ON b.id=o.order_batch_id
 JOIN sap_so_ref r ON r.so_number=o.so_number WHERE r.doc_date<>b.processing_date;
-- #4 lần nhập chỉ có đơn đã tồn tại (nhập chồng ngày)            -- dev: 3 lần, đều cùng ngày
SELECT at, detail FROM event_log WHERE kind='file_imported' AND detail LIKE '%"new": 0%' ORDER BY id;
-- #5 đơn còn mở, không SO, trong lô đã xác nhận                  -- dev: 0
SELECT o.platform, o.platform_order_id, o.status FROM sales_order o
 JOIN order_batch b ON b.id=o.order_batch_id
 WHERE o.status IN ('NEW','READY','MAPPING_ERROR','NEED_REVIEW') AND o.so_number IS NULL
   AND b.confirmed_at IS NOT NULL;
-- #6 SO/DO trùng trên nhiều đơn; hóa đơn của DO không có đơn     -- dev: SO trùng 0, DO trùng 0, hóa đơn không đơn 163/255
SELECT so_number, count(*) FROM sales_order WHERE so_number IS NOT NULL GROUP BY 1 HAVING count(*)>1;
SELECT do_number, count(*) FROM sales_order WHERE do_number IS NOT NULL GROUP BY 1 HAVING count(*)>1;
SELECT count(*) FROM sap_tax_invoice t WHERE NOT EXISTS (SELECT 1 FROM sales_order o WHERE o.do_number=t.delivery);
-- #7 PO No trùng trong sap_so_ref                                 -- dev: 0
SELECT po_no, count(*) FROM sap_so_ref GROUP BY 1 HAVING count(*)>1;
-- #8 đơn có ngày đặt lệch quá 3 ngày so với ngày lô              -- dev: 0
SELECT count(*) FROM sales_order o JOIN order_batch b ON b.id=o.order_batch_id
 WHERE o.ordered_at::date < b.processing_date - 3;
-- #9 dòng hàng đơn đã xuất mà thiếu mã vật tư                     -- dev: 0
SELECT count(*) FROM sales_order_item i JOIN sales_order o ON o.id=i.sales_order_id
 WHERE i.material_number IS NULL AND o.status IN ('READY','SO_LINKED','DELIVERED');
-- #10 việc đọc zrsd001/zrsd004 lỗi hoặc treo                      -- dev: zrsd001 FAILED 1, zrsd004 FAILED 2
SELECT kind, status, count(*) FROM sap_job GROUP BY 1,2 ORDER BY 1,2;
-- #11 SO lệch giá trị so với file sàn                             -- dev: 17/117 (Lazada 8, TikTok 5, Shopee 4)
WITH e AS (SELECT o.platform, o.platform_order_id, o.so_number,
                  sum((i.unit_price-i.unit_subsidy)*i.quantity) AS exp
           FROM sales_order o JOIN sales_order_item i ON i.sales_order_id=o.id
           WHERE o.so_number IS NOT NULL AND o.status<>'CANCELLED' GROUP BY 1,2,3)
SELECT e.platform, count(*) AS linked, sum((e.exp<>r.net_value_incl)::int) AS mismatch
  FROM e JOIN sap_so_ref r ON r.so_number=e.so_number GROUP BY 1;
```

Câu hỏi "một SO có hơn một DO" không trả lời được bằng DB: số DO theo SO chỉ có trong file zrsd004 gốc (đã xóa sau khi nhập) nên production chỉ kiểm được bằng cách đọc lại zrsd004 theo ngày và đếm DO theo `SO Reference`.
