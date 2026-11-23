# Rà soát toàn vẹn dữ liệu: file lịch sử Shop Online (261116-1354, 261119-0828)

## Nguồn và giới hạn

- Mã đọc tại `main` (2026-11-23); số đếm từ **dev DB, 2026-11-23** qua công cụ chỉ đọc. Không phải production.
- Dev: 117 đơn `DELIVERED`, 1 file `sales_history` (37 đơn), `sales_history_exported` có **0 dòng**: luồng xác nhận, gỡ xác nhận và chồng đơn giữa các file chưa từng chạy ở dữ liệu này, chỉ kiểm được bằng mã và test.
- Test: ba file liên quan (route, workbook, tên báo cáo) 72 passed; `ruff check` sạch. Chưa tái hiện bằng test riêng vì fixture nằm trong `tests/` (chỉ chép được kèm toàn bộ `conftest`); các phát hiện dựa trên mã và test hiện có, ghi "chưa tái hiện".
- Không có phát hiện High hoặc Critical.

## Trả lời 6 câu hỏi

1. **Đánh dấu đã xuất lúc nào?** Chỉ lúc bấm "Xác nhận đã dán". Tải file chỉ ghi `sales_history_file_order` (`sales_history.py:234-238`), chưa ghi `sales_history_exported`. Tải hai lần không xác nhận thì đơn có trong **cả hai file** (không có kiểm tra, vì `collect_rows` chỉ loại đơn đã xác nhận, `sales_history_workbook.py:141-157`). Xác nhận file cũ thay vì file mới: đơn của file đó vào sổ, đơn chỉ có ở file mới vẫn chờ; đơn có ở cả hai được ghi một lần và báo "bỏ qua" (`:380-388`). Rủi ro nằm ở dán cả hai file: phát hiện 1.
2. **Xóa file đã tải (`59c361a`):** chỉ xóa được khi chưa đơn nào xác nhận qua file đó (`:447-454`); xóa thì gỡ `sales_history_file_order` và các đơn quay lại hàng chờ (`:455-468`). Không đơn nào bị coi là đã xuất mãi. File đã xác nhận phải gỡ xác nhận trước. Test `:225,249`.
3. **Đơn nhiều DO hoặc nhiều dòng:** một `HistoryRow` mỗi dòng sản phẩm (`sales_history_workbook.py:251-274`), không thừa, không thiếu. `SalesOrder.do_number` là một DO duy nhất mỗi đơn và `sap_tax_invoice` khóa theo DO, nên "nhiều DO" không xảy ra trong mô hình. Dev: 3 đơn DELIVERED nhiều dòng; 0 đơn không có dòng; 0 dòng thiếu mã vật tư; 0 DO dùng chung cho nhiều đơn. `Tiền Vô` chỉ ở dòng đầu của đơn (`:263`), đúng thiết kế.
4. **Đơn bị chặn mãi mà không ai thấy:** có. Trang chỉ liệt kê khi có người mở và chọn tháng không sớm hơn ngày đặt (`sales_history.py:164-201`); không có cảnh báo theo tuổi; `customer_info` của đơn không bao giờ xuất được giữ vô thời hạn (`retention.py:102-108`): phát hiện 4. **Đơn tồn từ tháng trước có được gom vào tháng sau:** có, vì không có cận dưới theo ngày đặt, chỉ có cận trên cuối tháng đã chọn (`sales_history_workbook.py:150-155`). Dev: toàn bộ 117 đơn đặt trong tháng 11/2026; mặc định của trang là tháng 10, nên mở trang không chọn tháng thì thấy 0 đơn (không mất dữ liệu, chỉ gây hiểu nhầm; phát hiện 6).
5. **File nháp:** không ghi DB hay đĩa (`sales_history.py:242-265`, `collect_rows` chỉ `SELECT`, `Response` từ bộ đệm); test `test_sales_history_routes.py:478-502`. Phân biệt với dòng thật: tên file có `NHÁP`, cột 21 `Trạng thái`, dòng chữ trên trang; **cùng tên sheet `sheet1` và 20 cột đầu giống hệt** (`sales_history_workbook.py:277`), nên dán nhầm không bị Excel phát hiện: phát hiện nháp 1.
6. **Ranh giới tháng, múi giờ:** đơn 23:30 ngày cuối tháng thuộc tháng đó (`ordered_at < 00:00 ngày kế`, `:153`; cột `month` lấy từ chính `ordered_at`). Sắp xếp theo `ordered_at` rồi mã đơn không làm mất dòng nào (chỉ là `ORDER BY`). Dev: 5 đơn đặt từ 23:00 tới 00:59, 2 đơn từ 23:00, không đơn nào lệch tháng. Giả định chưa kiểm: `ordered_at` đã là giờ Việt Nam cho cả ba sàn, importer không đổi múi giờ (`shopee_orders.py:36-45`, `tiktok_orders.py:44-50`): phát hiện 5.

## Bảng phát hiện

| # | Plan | Phát hiện | Mức | Bằng chứng | Đề xuất |
|---|---|---|---|---|---|
| H1 | 261116-1354 | Hai file chưa xác nhận chồng đơn; xác nhận file này, file kia vẫn chứa dòng của đơn đã xác nhận và còn trên đĩa; dán cả hai lặp dòng. `GET` tải file ghi file và sổ nên bấm đúp cũng tạo chồng | Medium | `sales_history.py:204-239,365-411`; `retention.py:158-166`; `test_sales_history_routes.py:206` (chỉ phủ trường hợp hai file giống hệt). Chưa tái hiện: dựng bằng file A đơn {1,2}, thêm đơn 3, file B {1,2,3}, xác nhận A | `/ak-fix`: khi tải, báo hoặc loại đơn đã nằm trong file chưa xác nhận; hoặc đổi tải thành POST; hoặc trên trang cảnh báo "file X chồng đơn với file Y" |
| H2 | 261116-1354 | Tiền Vô và Tax Invoice chốt lúc tải; giao dịch đến sau hoặc hóa đơn bị ghi đè không phản ánh vào file đã dán, không có cảnh báo | Medium | `sales_history_workbook.py:184-207`; `report_ingest.py:93-103,147-175`; dev: 0 đơn nhiều dòng tiền vô, 0 thay đổi sau xác nhận (không có đơn xác nhận) | SQL S5, S5b, S8 trên production; nếu có lệch: `/ak-fix` ghi nhận giá trị lúc xác nhận để so sánh |
| H3 | 261116-1354 | Tên khách bắt đầu bằng `=`, `+`, `-`, `@` thành công thức Excel | Medium | `sales_history_workbook.py:287,307`; openpyxl đã thử với `=`: `data_type` ra `f`; nguồn tên: `lazada_orders.py:123`, `order_import.py:239-247` | `/ak-fix`: ép chuỗi (tiền tố `'` hoặc `data_type = "s"`) cho cột tên, tên báo cáo, biến thể |
| H4 | 261116-1354 | Đơn tồn lâu không có cảnh báo tuổi; PII giữ vô thời hạn | Low | `sales_history.py:164-201`; `retention.py:102-108`; dev: 0 đơn quá 60 ngày (S2) | Chấp nhận rủi ro hoặc thêm dòng cảnh báo "đơn chờ quá N ngày"; SQL S2 trên production |
| H5 | 261116-1354 | Giả định `ordered_at` là giờ Việt Nam chưa kiểm cho TikTok và Lazada | Low | importer không đổi múi giờ | Đối chiếu một đơn cuối tháng với màn hình sàn; không cần mã |
| H6 | 261116-1354 | Plan lệch mã: 17 cột (mã 20), ô "đến ngày" mặc định hôm nay (mã: tháng, mặc định tháng trước), lý do chặn thiếu hóa đơn và tiền vô | Low | `sales_history_workbook.py:55-76`; `sales_history.py:76-86` | Sửa văn bản plan khi chủ dự án duyệt |
| H7 | 261116-1354 | `Transaction` gộp hai đơn cùng tên và cùng phút thành một; `createTime` bỏ giây | Low | `sales_history_workbook.py:284,291`; dev: 1 cặp (S4) | Hỏi kế toán định nghĩa giao dịch; chấp nhận nếu đúng ý |
| D1 | 261119-0828 | Nháp cùng tên sheet và 20 cột đầu như file thật; dán nhầm thì đơn vẫn chưa xác nhận và xuất lại: lặp dòng | Low | `sales_history_workbook.py:277`; `sales_history.html:18-20` | Đặt tên sheet nháp khác `sheet1` (một dòng mã); chờ chủ dự án |
| D2 | 261119-0828 | Tiền Vô trong nháp là số tạm | Low | cùng H2 | Theo H2 |

Bác (có nguồn): hai lần xác nhận ghi trùng (khóa chính `models.py:433-438`, `sales_history.py:384`, test `:206`); xóa file mất ghi nhận (`sales_history.py:447-454`, test `:249`); đơn cuối tháng lệch tháng (`sales_history_workbook.py:153`); số dòng thừa hoặc thiếu (`:251-274`, dev); đơn tồn tháng trước bị bỏ (`:141-157`); retention xóa tên sớm (`retention.py:102-108`); viewer ghi (`require_admin` ở `sales_history.py:370,419,441`); nháp ghi DB, đơn đã xác nhận lọt vào nháp, lý do chặn khác lọt vào nháp, tên file có dấu hỏng, cột 21 lệch file thật (xem `plan.md` của `261119-0828`).

## Đối chiếu tiêu chí plan 261116-1354

Validation log cũ có 32 điều kiện đã xác minh, 0 chưa xác minh, nên không kiểm lại. Tiêu chí 1 (24 đơn tại 2026-11-16) và 6 đã lỗi thời so với mã (H6); phase 5 vẫn `in-progress` (chờ admin duyệt tên báo cáo, xuất và xác nhận lần đầu trên production), mã đã vượt xa phạm vi gốc (tax invoice, tiền vô, nháp, xóa file, chọn tháng).

## SQL cần chạy (chỉ đọc) — cho phase 7

Đã chạy trên dev DB, 2026-11-23, kết quả trong ngoặc. Chạy lại trên production với `SET default_transaction_read_only = on`.

```sql
-- S1 đơn có trong 2 file chưa xác nhận trở lên (dev: 0)
select f.sales_order_id from sales_history_file_order f
left join sales_history_exported e on e.sales_order_id = f.sales_order_id
where e.sales_order_id is null group by 1 having count(*) > 1;

-- S2 đơn DELIVERED chưa xuất quá 60 ngày (dev: 0)
select o.platform, o.platform_order_id from sales_order o
where o.status = 'DELIVERED' and o.ordered_at < now() - interval '60 days'
  and not exists (select 1 from sales_history_exported e where e.sales_order_id = o.id) limit 20;

-- S3 đơn đã xác nhận qua file này nhưng còn trong file chưa xác nhận khác (dev: 0)
select count(*) from sales_history_file_order f
join sales_history_exported e on e.sales_order_id = f.sales_order_id
 and e.generated_file_id <> f.generated_file_id;

-- S4 nhóm cùng tên khách và cùng phút nhưng khác đơn (dev: 1); không in tên
select count(*) from (select c.customer_name, date_trunc('minute', o.ordered_at) m
  from sales_order o join customer_info c on c.platform = o.platform
   and c.platform_order_id = o.platform_order_id
  where o.status = 'DELIVERED' group by 1, 2 having count(distinct o.id) > 1) t;

-- S5 tiền vô đổi sau khi xác nhận (dev: 0, chưa có đơn xác nhận)
select count(*) from sales_history_exported e
join sales_order o on o.id = e.sales_order_id
join platform_settlement s on s.platform = o.platform and s.platform_order_id = o.platform_order_id
where s.updated_at > e.confirmed_at;

-- S5b hóa đơn đổi sau khi xác nhận (dev: 0)
select count(*) from sales_history_exported e
join sales_order o on o.id = e.sales_order_id
join sap_tax_invoice t on t.delivery = o.do_number
where t.updated_at > e.confirmed_at;

-- S6 đơn đã xác nhận mà không còn DELIVERED (dev: 0)
select count(*) from sales_history_exported e
join sales_order o on o.id = e.sales_order_id where o.status <> 'DELIVERED';

-- S7 đơn nằm trong file chưa xác nhận quá 7 ngày (dev: 0)
select count(distinct f.sales_order_id) from sales_history_file_order f
join generated_file g on g.id = f.generated_file_id
left join sales_history_exported e on e.sales_order_id = f.sales_order_id
where e.sales_order_id is null and g.created_at < now() - interval '7 days';

-- S8 đơn có nhiều dòng tiền vô (dev: 0)
select platform, platform_order_id, count(*) from platform_settlement
group by 1, 2 having count(*) > 1 limit 20;
```

Số đếm dev khác (2026-11-23): 117 đơn DELIVERED; 37 đơn trong file đã tải (1 file, chưa xác nhận); 80 đơn chưa có trong file nào; thiếu hóa đơn 25; chờ tiền vô 78 (Shopee 61, TikTok 17); thiếu tên báo cáo 0; thiếu tên khách 0; thiếu địa chỉ 0.

## Câu hỏi cho chủ dự án

1. Sửa H1 bằng cách nào: cảnh báo chồng đơn trên trang, tự loại đơn đã nằm trong file chưa xác nhận, hay đổi tải file thành thao tác `POST`?
2. Có sửa H3 (ép tên khách thành chuỗi) ngay không?
3. Kế toán có cần số `Tiền Vô` được khóa lúc xác nhận để so sánh về sau (H2) không?
4. TikTok và Lazada xuất giờ theo múi giờ nào (H5)? Một đơn cuối tháng đối chiếu với màn hình sàn là đủ.
5. Có đặt tên sheet nháp khác `sheet1` (D1) không?
