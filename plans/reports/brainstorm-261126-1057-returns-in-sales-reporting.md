# Brainstorm: đơn hủy, trả hàng trong file Shop Online và báo cáo

Ngày: 2026-11-26. Tiếp nối tính năng phiếu trả hàng ([plan](../261123-0950-invoice-return-documents/plan.md)).

## Mục tiêu

Tổng giá trị bán trong file Shop Online và trong báo cáo là giá trị bán thật: đơn hủy hoặc trả sau hóa đơn được trừ ra. Mọi module có liên quan đều có dấu hiệu cho thấy đơn đã hủy hoặc trả hàng.

## Hiện trạng (đã kiểm trên mã)

- Lập phiếu trả hàng không đổi trạng thái đơn. Đơn vẫn `DELIVERED`, và `DELIVERED` là trạng thái cuối (`domain/states.py`).
- File Shop Online lấy mọi đơn `DELIVERED` chưa xác nhận dán, không kiểm tra phiếu trả (`exports/sales_history_workbook.py`, `pending_orders`). Đơn đã trả vẫn ra dòng dương.
- File của kế toán chỉ được dán thêm xuống dưới, không sửa dòng cũ. Trong 3.010 dòng hiện có, không có dòng âm nào và chưa có quy ước ghi đơn trả.
- Báo cáo: `report_sale_line` tính đủ đơn đã trả. `report_order_revenue.returned_value` là tiền hàng chưa thuế, trong khi `invoice_value` là tiền có thuế, nên tỷ lệ trả thấp hơn thực tế khoảng 8% (migration `0016`).
- Không có liên kết từ dòng phiếu trả (dòng SO SAP) sang dòng đơn sàn (`sales_order_item`). Hai bên chỉ chung `material_number`.
- File lịch sử chỉ được nạp vào báo cáo cho phần trước 11/11/2026 và từ chối số lượng ≤ 0 (`importers/history_file.py`). Dòng âm từ ngày 11/11 trở đi sẽ không đi vào đường nạp đó.
- Có một lỗ hổng: đơn đã có DO, DO bị hủy trong SAP trước khi xuất hóa đơn. Đơn đó không lập được phiếu (chưa có hóa đơn) và cũng không đánh dấu hủy được (web chặn). Đơn kẹt ở `DELIVERED` và vẫn được tính trong báo cáo.

## Ràng buộc

- Không thêm trạng thái đơn mới. File gửi kế toán, tiền về Lazada và các view báo cáo đều lọc theo `DELIVERED`.
- File Shop Online chỉ dán thêm xuống dưới. Muốn trừ thì phải ghi thêm dòng, không sửa dòng đã dán.
- Phiếu có thể được lập trước hoặc sau khi đơn đã dán, và có thể bị hủy rồi lập lại.
- Cột `Customer paid` là giá trị trên sàn (giá trừ trợ giá, nhân số lượng), không phải tiền hóa đơn. Dòng trừ phải dùng cùng cơ sở này thì tổng mới đúng.

## Ngoài phạm vi

Hóa đơn điều chỉnh trên Bkav, chứng từ trong SAP, sửa dữ liệu lịch sử trước 11/11/2026, tự điều chỉnh cột `Tiền Vô` khi sàn hoàn tiền, sửa lại các đợt gửi kế toán đã chốt.

## Các hướng đã cân nhắc

| Hướng | Giả định chính | Hỏng ở đâu trước |
|---|---|---|
| **A. Sổ cái chỉ ghi thêm: mỗi phiếu sinh dòng âm** (đề xuất) | Kế toán chấp nhận dòng âm trong file | Kế toán bắt buộc mỗi đơn chỉ một dòng ròng |
| B. Trừ thẳng trước khi dán, chỉ ghi dòng âm khi phiếu lập sau lúc dán | Phần lớn phiếu được lập trước khi dán | Phải duy trì hai cách xử lý; đơn trả một phần đã dán vẫn phải dùng dòng âm; tổng số dòng giữa file và hệ thống khó đối chiếu |
| C. Chỉ đánh dấu ở cột trạng thái | Kế toán tự trừ tay | Không đạt mục tiêu: tổng cộng vẫn sai |

Chọn A vì mọi trường hợp (trước hay sau khi dán, cả đơn hay một phần, hủy phiếu) đều đi theo một quy tắc: chứng từ nào phát sinh thì ghi thêm dòng của chứng từ đó. Tổng luôn bằng giá trị ròng, và từng dòng âm truy ngược được về số biên bản.

Better approaches: none. Hướng được đề xuất chính là yêu cầu của người dùng (trừ ngay trong file), và cách làm phải là sổ cái chỉ ghi thêm vì file là append-only.

## Thiết kế đề xuất

### 1. Một nguồn duy nhất cho dòng trừ

Lúc phát hành phiếu, quy dòng SAP về dòng đơn sàn và lưu vào bảng mới `sales_return_sale_line` (`return_id`, `sales_order_item_id`, `quantity`, `customer_paid`). Cách quy đổi:

- Lấy các dòng đơn sàn cùng `material_number`.
- Tỷ lệ trả = `return_qty / invoice_qty` của mã đó.
- Số lượng trừ = số lượng dòng sàn × tỷ lệ; tiền trừ = (giá − trợ giá) × số lượng trừ.
- Trả cả đơn thì dòng trừ đúng bằng dòng gốc.
- Nếu tỷ lệ cho ra số lẻ, hoặc không ghép được mã, thì chặn phát hành và nêu rõ lý do.

File Shop Online, báo cáo và các nhãn đều đọc từ bảng này, không module nào tự tính lại.

### 2. File Shop Online

- Lần xuất kế tiếp có thêm các dòng âm cho mọi phiếu `ISSUED` chưa dán: `Quantity` âm, `Customer paid` âm. Tên khách, tỉnh, tên hàng, mã đơn và `Tax Invoice Doc.` (số hóa đơn gốc) giữ như dòng gốc. `Tiền Vô` để trống.
- Cột `Transaction` (I): ở dòng âm, ghi hằng số thay cho công thức. Dòng đầu của phiếu trả cả đơn ghi −1, các dòng khác ghi 0. Như vậy SUM của cột I bằng số đơn bán thật. Nếu dùng công thức, cột này sẽ đếm dòng âm thành một giao dịch mới.
- Hủy phiếu sau khi dòng âm đã dán: lần xuất kế tiếp có dòng dương đảo lại (cột I ghi +1 hoặc 0). Hủy phiếu khi dòng âm chưa dán: không sinh dòng nào.
- Phiếu lập khi đơn chưa dán: file có cả dòng gốc và dòng âm, tổng ròng bằng 0 (hoặc bằng phần còn lại nếu trả một phần).
- Theo dõi đã dán bằng bảng `sales_return_history_exported` (`return_id`, loại `ISSUE` hoặc `VOID`, `generated_file_id`). Bước "xác nhận đã dán" hiện có ghi luôn vào bảng này.
- File NHÁP và file TẤT CẢ ĐƠN: cột Trạng thái ghi "Hủy đơn / Trả hàng (cả đơn / một phần) – biên bản 080/11.2026".
- Ngày ở dòng âm (`createTime`, `month`, `year`): theo ngày đặt đơn gốc (người dùng chốt). Phần trừ rơi vào đúng tháng đã bán, nên file và báo cáo khớp nhau theo tháng đặt đơn.

### 3. Báo cáo

- `report_sale_line`: thêm `UNION ALL` các dòng âm từ `sales_return_sale_line` của phiếu `ISSUED`. Tổng quan, Theo sàn, Theo sản phẩm, Theo tỉnh đều tự ra số ròng. Số đơn đếm theo đơn còn giá trị dương.
- `report_order_revenue`: `marketplace_value` trừ phần trả. `returned_value` đổi sang cùng cơ sở có thuế với `invoice_value` (`returned_net + returned_tax`), và thêm cột giá trị trả theo giá sàn.
- Trang Trả hàng: giữ nguyên, sửa cơ sở thuế.
- Hai việc trên là sửa view, cần một migration mới (sao lưu database trước khi chạy).

### 4. Dấu hiệu ở các module khác

Thêm một hàm dùng chung `returns.flags(session, order_ids)` trả về nhãn của đơn: "Hủy sau HĐ", "Trả hàng" hoặc "Trả một phần", kèm số biên bản. Nhãn này hiện ở:

- danh sách đơn của lô và trang chi tiết đơn;
- trang Hôm nay (nếu có danh sách đơn);
- Tiền về Lazada (nhập tay và tải file theo số hóa đơn): hiện nhãn và cảnh báo trước khi lưu tiền cho đơn đã hủy cả đơn;
- trang đợt gửi kế toán: liệt kê DO thuộc đơn có phiếu trả để kế toán biết;
- file NHÁP và file TẤT CẢ ĐƠN như mục 2;
- Excel tải từ báo cáo (đã có sẵn nhờ view).

### 5. Lấp lỗ hổng "DO hủy trước khi có hóa đơn"

Cho phép admin chuyển `DELIVERED → CANCELLED` chỉ khi DO chưa có hóa đơn trong zrsd003, kèm lý do bắt buộc. Đơn đó rời khỏi báo cáo (view đã loại `CANCELLED`) và không bao giờ vào file Shop Online. Nếu DO đã nằm trong một đợt gửi kế toán đã chốt, hiện cảnh báo "báo kế toán bằng tay", đúng như runbook hiện tại.

## Tiêu chí nghiệm thu

- Đơn A (trả cả đơn trước khi dán) và đơn B (trả một phần sau khi dán): SUM `Customer paid` và SUM `Transaction` của các dòng đã dán bằng giá trị bán thật và số đơn bán thật.
- Hủy phiếu của đơn B sau khi dòng âm đã dán: lần xuất kế tiếp có dòng đảo, tổng quay lại như trước khi trả.
- Báo cáo Tổng quan, Theo sản phẩm, Theo tỉnh của tháng chứa A và B khớp với tổng của file Shop Online (phần từ 11/11/2026).
- Tỷ lệ trả tính trên cùng cơ sở có thuế.
- Nhãn hiện ở mọi nơi trong mục 4 và mất khi phiếu bị hủy.
- Đơn có DO hủy, chưa có hóa đơn: đánh dấu hủy được và rời khỏi báo cáo. Đơn đã có hóa đơn: vẫn bị chặn, phải lập phiếu.
- `uv run pytest` và `uv run ruff check` đạt.

## Rủi ro

- Quy đổi theo mã vật tư giả định dòng đơn sàn và dòng SO SAP cùng mã và cùng đơn vị. Đơn kit (dòng cha) và đơn có hai dòng cùng mã khác giá cần test riêng. Trường hợp không ghép được thì chặn, không đoán.
- Kế toán có thể có công thức hoặc pivot giả định số lượng luôn dương. Cần báo kế toán trước khi dòng âm đầu tiên được dán.
- Cột `Tiền Vô` của đơn đã trả vẫn giữ số sàn trả lúc đầu. Phần sàn hoàn tiền nằm ngoài phạm vi.

## Quyết định của người dùng (2026-11-26)

- Dòng âm mang ngày đặt đơn gốc.
- Cột `Transaction` ở dòng âm và dòng đảo ghi hằng số −1, 0 hoặc +1 thay cho công thức.
- Làm luôn mục 5 (hủy đơn đã có DO nhưng chưa có hóa đơn) trong đợt này.

Câu hỏi còn mở: không còn. Trước khi dòng âm đầu tiên được dán, báo kế toán về cách ghi mới.
