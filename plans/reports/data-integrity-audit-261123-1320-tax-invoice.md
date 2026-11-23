# Rà soát toàn vẹn dữ liệu: hóa đơn zrsd003

Plan: `261119-0605-zrsd003-tax-invoice-in-history` (soi mã, 4 lens + trùng/sót) và `261119-0854-month-pick-zrsd003-read` (2 lens + trùng/sót).

## Nguồn và giới hạn

- Số đếm lấy từ **dev DB, 2026-11-23** (production không mở được). Dữ liệu dev: đơn đặt 2026-11-11 đến 2026-11-19, 129 đơn, 255 dòng `sap_tax_invoice`, hóa đơn ngày 2026-11-03 đến 2026-11-19.
- `sales_history_exported` có 0 dòng ở dev, nên bất biến "hóa đơn đổi sau khi file đã xác nhận" chỉ kiểm được bằng mã.
- Mẫu `docs/zrsd003.XLSX` chỉ dùng để đếm cột và Bill-to; không in tên khách.
- Không sửa mã, không commit. Test tái hiện ở `scratchpad/repro_dup_invoice.py` (ngoài repo).

## Trả lời 5 câu hỏi của phase

1. **Một DO có hai hóa đơn?** Khóa `sap_tax_invoice.delivery` là khóa chính (`migrations/versions/0008_sap_tax_invoice.py`). Bộ nhập chỉ nhận dòng ZBA1 (`sap_reports.py:162`), rồi gom `{delivery: dòng}` nên **dòng cuối file thắng** (`report_ingest.py:81`), không cảnh báo. Tái hiện: hai dòng ZBA1 cùng `OD Doc.` (số `1111` rồi `2222`) giữ `2222`; đảo thứ tự giữ `1111`. Có thể giữ nhầm hóa đơn đã hủy nếu SAP còn liệt kê dòng ZBA1 đã hủy. zrsd003 không có cột trạng thái hủy (mẫu có 16 cột: Billing Type, Sales Office, Sloc, Billing Date, Billing Doc., OD Doc., Tax Invoice Doc., Bill-to, Name, VAT Reg. No., Tax Classification, Exch. Rate-Acct., Doc. Currency, Net Value, Net Value (VND), Tax (VND)). Mẫu 650 dòng toàn ZBA1 và không có `OD Doc.` trùng; dev DB: 0 DO trùng, 0 số hóa đơn dùng cho hai DO. Chưa biết SAP thật có liệt kê hóa đơn hủy hay không. Phát hiện 1.
2. **Upload tay và robot cùng ghi một DO:** cùng hàm `ingest_zrsd003`; upsert không điều kiện (`report_ingest.py:93-101`), nên **bên chạy sau thắng**, kể cả khi file cũ hơn. Nếu hai nguồn cùng lúc SAP thì cùng giá trị, vô hại. Nếu upload tay một file xuất trước khi hóa đơn bị hủy/xuất lại, số cũ ghi đè số mới. Phát hiện 2.
3. **Khoảng đọc và hóa đơn ngoài khoảng:** khoảng bắt đầu ở ngày đặt sớm nhất của đơn chờ hoặc ngày 1 của tháng (`sales_history.py:105-112`); hóa đơn của đơn chờ luôn sau ngày đặt nên nằm trong khoảng. Dev DB: 0 hóa đơn có `billing_date` trước ngày đặt của đơn. Dòng của khách ngoài ba sàn **không được ghi** (`report_ingest.py:80-81`), mẫu có 650 dòng, 243 dòng sàn, 407 dòng khách khác. Hóa đơn của DO không thuộc app (163/255 dòng dev) vẫn được lưu vì lọc theo Bill-to; vô hại (chỉ mã số). Khoảng có thể lớn khi chọn tháng cũ hoặc có đơn chờ vĩnh viễn (phát hiện 5 của 0605, 1 của 0854).
4. **Khóa chống trùng theo khoảng:** `queue.enqueue` chỉ chặn việc đang mở cùng khóa (`queue.py:89-93`); hai khoảng chồng nhau tạo hai việc, **không hại**: nhập idempotent. Bằng chứng thật trên dev: việc 47 (13-19/11) nhập 80 dòng mới; việc 48 (17-19/11) 0 mới, 56 cập nhật.
5. **Một đơn nhiều DO:** `mark_delivered` giữ DO đầu theo thứ tự dòng file zrsd004 (`so_link.py:306,314`); chỉ DO đó được tra hóa đơn (`sales_history_workbook.py:228`). Đơn có DO đầu đã có hóa đơn và DO sau chưa có vẫn được coi là đủ. Dev DB: không đơn nào chung DO, và 117 DO ở sổ gửi kế toán đúng bằng 117 DO của đơn (không DO dư). Phát hiện 4.

## Bảng phát hiện

| # | Plan | Phát hiện | Mức | Bằng chứng | Đề xuất |
|---|------|-----------|-----|------------|---------|
| 1 | 0605 | DO trùng trong một file: giữ dòng cuối file, không cảnh báo | High (khả năng chưa kiểm chứng) | `report_ingest.py:81`; `sap_reports.py:162`; tái hiện `repro_dup_invoice.py` | `/ak-fix`: giữ `Billing Date` mới nhất, cảnh báo khi trùng; hỏi chủ dự án SAP có liệt kê hóa đơn hủy không |
| 2 | 0605 | File upload tay cũ ghi đè số mới | Medium | `report_ingest.py:93-101` | `/ak-fix`: chỉ ghi đè khi `billing_date` không cũ hơn |
| 3 | 0605 | Một dòng lỗi của khách khác từ chối cả file, hóa đơn sàn không vào | Medium | `sap_reports.py:165-166,178-179`; `report_ingest.py:81` | `/ak-fix`: lọc Bill-to trước khi kiểm lỗi dòng |
| 4 | 0605 | SO nhiều DO: DO thứ hai không kiểm hóa đơn | Medium | `so_link.py:306,314`; `sales_history_workbook.py:228` | SQL #2 trên production; plan riêng nếu có |
| 5 | 0605, 0854 | Đơn không bao giờ có hóa đơn kéo khoảng đọc lùi mãi, nằm vĩnh viễn ở "Đơn bị chặn" | Low | `sales_history.py:105-112` | Theo dõi bằng SQL #1 |
| 6 | 0605 | Tài liệu lệch: runbook còn ghi chưa chạy SAP thật; không có biên bản live-check; tiêu chí "19 cột" nay là 20 | Low | `docs/robot-runbook.md:124`; `plans/reports` không có `live-check-*zrsd003*` | Cập nhật khi chạy thử production |
| 7 | 0854 | Khoảng đọc không có trần khi chọn tháng cũ; robot hết giờ chờ thì việc FAILED | Medium | `sales_history.py:105-112` | Đo thời gian khi deploy; chia khoảng hoặc cảnh báo > 62 ngày |

Bị bác (có bằng chứng): hóa đơn DO ngoài app được lưu (chủ ý, vô hại); khoảng chồng nhau (idempotent); DO billed cho Bill-to khác (không âm thầm, đơn bị chặn có lý do); hóa đơn ngoài khoảng đọc (không xảy ra, 0 hóa đơn trước ngày đặt); khoảng đổi giữa xem và bấm (vô hại); hóa đơn đổi sau khi file đã xác nhận (ngoài phạm vi plan: "sửa lại file lịch sử đã xác nhận").

## SQL cần chạy (chỉ đọc, cho phase 7)

Kết quả dev DB, 2026-11-23, ghi cạnh mỗi câu. Chạy lại trên production hoặc bản phục hồi.

```sql
-- 1. Đơn DELIVERED chưa có hóa đơn, theo ngày đặt (kỳ vọng: chỉ đơn mới, vài ngày gần nhất)
-- dev: 25 đơn (21 đặt 2026-11-18, 4 đặt 2026-11-19); đơn cũ nhất 2026-11-18
SELECT date(o.ordered_at) AS d, count(*) FROM sales_order o
WHERE o.status = 'DELIVERED' AND o.do_number IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sap_tax_invoice t WHERE t.delivery = o.do_number)
GROUP BY 1 ORDER BY 1;

-- 2. DO ở sổ gửi kế toán không thuộc đơn nào (chỉ báo SO nhiều DO; trừ sổ nền run_id IS NULL nếu cần)
-- dev: 0
SELECT count(*) FROM accounting_sent_delivery d
WHERE NOT EXISTS (SELECT 1 FROM sales_order o WHERE o.do_number = d.delivery);

-- 3. Hai đơn chung một DO (kỳ vọng 0)
-- dev: 0
SELECT count(*) FROM (SELECT do_number FROM sales_order WHERE do_number IS NOT NULL
                      GROUP BY 1 HAVING count(*) > 1) x;

-- 4. Hóa đơn của khách không thuộc sàn (kỳ vọng 0)
-- dev: 0
SELECT count(*) FROM sap_tax_invoice t
WHERE t.bill_to NOT IN (SELECT sap_customer FROM platform_setting);

-- 5. Cặp đơn/hóa đơn lệch khách SAP của sàn (kỳ vọng 0)
-- dev: 0
SELECT count(*) FROM sales_order o
JOIN sap_tax_invoice t ON t.delivery = o.do_number
JOIN platform_setting p ON p.platform = o.platform
WHERE p.sap_customer <> t.bill_to;

-- 6. Hóa đơn ghi trước ngày đặt của đơn (kỳ vọng 0)
-- dev: 0
SELECT count(*) FROM sales_order o
JOIN sap_tax_invoice t ON t.delivery = o.do_number
WHERE t.billing_date < date(o.ordered_at);

-- 7. Một số hóa đơn hoặc một chứng từ billing dùng cho hai DO (kỳ vọng 0)
-- dev: 0 và 0
SELECT (SELECT count(*) FROM (SELECT 1 FROM sap_tax_invoice GROUP BY tax_invoice_doc HAVING count(*) > 1) a) AS dup_tax_doc,
       (SELECT count(*) FROM (SELECT 1 FROM sap_tax_invoice GROUP BY billing_doc HAVING count(*) > 1) b) AS dup_billing_doc;

-- 8. Hóa đơn đổi sau khi file lịch sử đã xác nhận (số trong file có thể lỗi thời; kỳ vọng 0)
-- dev: 0 (sales_history_exported rỗng, chưa thử được)
SELECT count(*) FROM sales_history_exported e
JOIN sales_order o ON o.id = e.sales_order_id
JOIN sap_tax_invoice t ON t.delivery = o.do_number
WHERE t.updated_at > e.confirmed_at;

-- 9. Hóa đơn của DO không thuộc app (thông tin, không phải lỗi)
-- dev: 163 trên 255
SELECT count(*) FROM sap_tax_invoice t
WHERE NOT EXISTS (SELECT 1 FROM sales_order o WHERE o.do_number = t.delivery);
```

Không có SQL phát hiện DO trùng trong một file (#1): bộ nhập bỏ dòng thua ngay khi nhập, sau đó không còn dấu vết. Cách kiểm duy nhất là xuất zrsd003 tay trên SAP thật cho một khoảng rộng và đếm `OD Doc.` trùng (hoặc hỏi kế toán).

## Kiểm chứng đã chạy

- `read_zrsd003` trên `docs/zrsd003.XLSX`: 650 dòng, Bill-to ba sàn 179/39/25, DO `1910061168` ra `7914`.
- Test: `tests/importers/test_zrsd003.py`, `tests/web/test_sales_history_routes.py`, `tests/saprobot/test_report_reads.py` qua 51 test; `tests/exports`, `tests/sapjobs`, `tests/reconcile` qua 75 test; `ruff check` sạch.
- Lượt chạy cả bộ đầu tiên báo 410 lỗi fixture do DB test dùng chung với các tác tử khác chạy song song; `tests/web/test_web_flow.py` chạy riêng qua. Kết quả cả bộ lượt sau: xem cuối file nếu có.

## Câu hỏi mở cho chủ dự án

1. SAP thật có liệt kê dòng ZBA1 của hóa đơn đã hủy trong zrsd003 (bộ lọc "Exist") không?
2. Có chạy `/ak-fix` cho phát hiện 1-3 không?
3. SO tách nhiều DO có xảy ra trên production không (SQL #2)?
4. Khi deploy, có đo thời gian lần đọc tháng 10/2026 và ghi journal không?
