# Phase 2: Dựng file gộp nhiều nguồn

## Bối cảnh

[accounting_workbook.py](../../src/shoponline/exports/accounting_workbook.py) nhận một file `zrsd004`, chèn ba cột sau `SO Reference` và giữ nguyên mọi dòng, kể cả dòng tổng. `build_accounting_workbook(source, lookup)` còn được gọi ở [report_ingest.py:46](../../src/shoponline/reconcile/report_ingest.py) (xem trước khi tải lên và kết quả của việc robot, qua [worker.py:121-129](../../src/shoponline/saprobot/worker.py)) và ở các test [test_accounting_workbook.py](../../tests/exports/test_accounting_workbook.py). Hàm này **không đổi chữ ký**.

Mẫu thật (gitignore, chứa dữ liệu cá nhân, chỉ dùng kiểm tay ở phase 6):

- `docs/zrsd004.XLSX`: 12 dòng dữ liệu toàn `PC`, **một** dòng tổng: Delivery Qty 16, Tonase 13,4 `LT/KG`, Actual Delivery Qty 16 `PC`, Net Weight 11,462 `KG`, Volume 13,4 `LT`.
- `docs/SHOP ONLINE 111126.XLSX` (gộp 3 sàn): 15 dòng dữ liệu, **hai** dòng tổng: dòng `SET` mang Delivery Qty 1, Tonase 16,4, Actual Delivery Qty 1, Net Weight 14,032, Volume 15,65; dòng `PC` chỉ mang Delivery Qty 20, Actual Delivery Qty 20 (Tonase, Net Weight, Volume trống, các ô đơn vị là chuỗi rỗng).

Quy tắc suy ra: SAP tính tổng **từng cột số lượng theo cột đơn vị của chính nó** (Delivery Qty và Actual Delivery Qty theo `Sales Unit`, Tonase theo `Tonase Unit`, Net Weight theo `Weight Unit`, Volume theo `Volume Unit`). Số dòng tổng bằng số đơn vị khác nhau lớn nhất ở một cột; mỗi cột điền các tổng của nó từ dòng đầu xuống. Trong mẫu hai đơn vị, `SET` đứng trước `PC`; giả thuyết là thứ tự mã đơn vị nội bộ của SAP (`PC` lưu là `ST`).

## Yêu cầu

Thêm hàm mới `build_merged_accounting_workbook(sources, lookup, *, exclude_deliveries, cutoff, today, platform_sold_to)`; dùng chung với hàm cũ phần chèn ba cột và tra khách (tách thành hàm chung). Trả về `AccountingFile` cùng thêm: tập số Delivery và số SO có trong file, số dòng bị bỏ theo từng lý do.

- **Nguồn:** danh sách đường dẫn hoặc luồng. Mọi nguồn phải có cùng tập tiêu đề; lệch thì từ chối cả file và nêu nguồn nào lệch cột nào.
- **Lọc dòng dữ liệu** (đếm từng lý do, không im lặng):
  - `Sold-to Party` không thuộc `platform_sold_to` (bộ mã khách của các sàn đã cấu hình, lấy từ `platform_by_customer`);
  - `Actual GI Date` trống hoặc sau `today`;
  - `Total Movement Goods Stat` khác `C`;
  - `Actual GI Date` ≤ `cutoff`;
  - `Delivery` nằm trong `exclude_deliveries`.
- **Gộp:** bỏ dòng tổng của từng nguồn; trùng theo `(Delivery, Line Item)` thì giữ dòng của nguồn đứng trước; sắp theo `Delivery` rồi `Line Item`.
- **Dòng tổng:** tính lại theo quy tắc trên, cộng bằng `Decimal` rồi ghi về số với đúng số chữ số thập phân của nguồn (không có sai số dấu phẩy động). Thứ tự đơn vị khai báo ở một bảng hằng (`SET` trước `PC`, đơn vị lạ sau cùng theo thứ tự chữ cái), có chú thích nguồn gốc suy luận. Ô không có tổng để trống như SAP (số trống, ô đơn vị là chuỗi rỗng).
- **Tên file** lấy ngày goods issue lớn nhất của các dòng còn lại.
- Không còn dòng dữ liệu: ném `FileRejected("Không có DO mới")`.
- Các dòng chưa goods issue bị bỏ hay lý do khác: trả kèm để phase 4 giữ cặp tương ứng ở trạng thái chờ.

Hàm cũ `build_accounting_workbook` giữ nguyên hành vi (một nguồn, giữ dòng tổng gốc). Dùng khi chỉ cần xem trước một file đơn lẻ.

## Tệp được sửa

- `src/shoponline/exports/accounting_workbook.py`
- `tests/exports/test_accounting_workbook.py`
- `tests/fixtures/build_fixtures.py`: `zrsd004_row` nhận thêm `tonase`, `net_weight`, `volume`, ba cột đơn vị, `sales_unit`, `goods_status`, `gi_date`; `zrsd004_file` ghi dòng tổng đúng quy tắc SAP (một dòng với một đơn vị, nhiều dòng với nhiều đơn vị). Dữ liệu hoàn toàn bịa, theo ghi chú đầu file fixture.

## Các bước

1. Mở rộng fixture, rồi viết test trước:
   - một nguồn một đơn vị: một dòng tổng; hai đơn vị `PC`/`SET`: hai dòng tổng có tổng khớp giá trị tính tay;
   - ghép 3 nguồn theo sàn cho kết quả bằng đúng bảng tính được dựng sẵn từ cùng dữ liệu (so từng ô, trừ ba cột chèn);
   - cộng không sinh `…000002`: ví dụ `0,664 + 0,744 + …` ra đúng chuỗi thập phân;
   - các lọc: khách lạ, `Actual GI Date` trống, trạng thái khác `C`, tương lai, ≤ mốc, DO bị loại (DO nhiều dòng biến mất hết);
   - trùng `(Delivery, Line Item)` giữ nguồn đầu; tiêu đề lệch bị từ chối;
   - không còn dòng: `FileRejected`.
2. Tách hàm chèn cột và tra khách dùng chung, rồi cài hàm mới.
3. Chạy lại toàn bộ test cũ để chắc đường một nguồn không đổi.

So sánh với file thật `docs/SHOP ONLINE 111126.XLSX` chỉ làm tay ở phase 6, không đưa vào CI.

## Kiểm tra

- `uv run pytest tests/exports tests/importers tests/saprobot` qua; test cũ không sửa.
- Các test mới ở bước 1.

## Rủi ro và hoàn tác

- Thứ tự đơn vị và việc `SET` mang tổng trọng lượng chỉ suy ra từ hai mẫu; kiểm bằng file thứ ba ở phase 6.
- Hoàn tác: bỏ hàm mới, hàm cũ không bị đụng.
