---
phase: 1
title: "Thu thập dòng, route, form và test"
status: completed
priority: P2
effort: "3.5h"
dependencies: []
---

# Phase 1: Thu thập dòng, route, form và test

## Goal

`GET /sales-history/all?from=YYYY-MM-DD&to=YYYY-MM-DD` trả file `.xlsx` chứa mọi đơn có ngày đặt trong khoảng, ở mọi trạng thái, cùng bố cục file nháp, và không ghi gì vào DB hay đĩa.

## Files to Create / Modify

- Modify: `src/shoponline/exports/sales_history_workbook.py`
- Modify: `src/shoponline/web/routes/sales_history.py`
- Modify: `src/shoponline/web/templates/sales_history.html`
- Modify: `tests/exports/test_sales_history_workbook.py`
- Modify: `tests/web/test_sales_history_routes.py`

## Tasks & Steps

1. **Tách tra cứu dùng chung** (`sales_history_workbook.py`): chuyển khối dựng `customers`, `names`, `invoices`, `settlements` trong `collect_rows` thành một hàm riêng (ví dụ `_lookups(session, orders)` trả một dataclass nhỏ). `collect_rows` gọi hàm đó và giữ nguyên hành vi từng dòng. Chạy test hiện có của file này ngay sau bước này, trước khi thêm gì.
2. **Hàm thu thập mới** `collect_all_rows(session, first: date, last: date) -> list[HistoryRow]`:
   - Chọn `SalesOrder` có `ordered_at >= datetime.combine(first, time())` và `< datetime.combine(last + timedelta(days=1), time())`, mọi `status`, nạp `items` bằng `selectinload`, sắp theo `ordered_at`, `platform_order_id`.
   - Tập đơn đã xác nhận: một truy vấn `SalesHistoryExported.sales_order_id` giới hạn trong id của các đơn đã chọn.
   - Mỗi đơn, mỗi dòng sản phẩm: dựng `HistoryRow` như `collect_rows`, nhưng không có lý do chặn. `division` = `DIVISION.get(platform, platform)`. Tên khách, tỉnh/thành: lấy nếu có, không thì chuỗi rỗng (`province_of` trả `None` thì rỗng). `itemName`/`size`/`variation`: dùng `ReportItemName` nếu có, không thì `sap_name or product_name`, `""`, `variation_name`.
   - `tax_invoice_doc`: tra theo `do_number`, `None` nếu không có. `settlement`: tổng quyết toán, chỉ ở dòng đầu, `None` nếu chưa có.
   - `status`: ghép theo hợp đồng của plan (nhãn trạng thái; `Chờ hóa đơn`/`Chờ tiền vô` chỉ với đơn DELIVERED, tiền vô chỉ với `SETTLED_PLATFORMS`; rồi `Đã xác nhận dán`/`Chưa xác nhận`). Dùng lại `DRAFT_LABELS` cho hai nhãn chờ.
3. **Workbook**: `build_history_workbook(rows, draft=False, title=None)`. Khi `draft` bật thì 21 cột như hiện tại; `title` nếu có thì thay tên sheet. Thêm hằng `ALL_SHEET = "TẤT CẢ ĐƠN - KHÔNG DÁN"` và `history_all_file_name(first, last)` = `f"TẤT CẢ ĐƠN SHOP ONLINE {first:%d%m%y}-{last:%d%m%y}.xlsx"`. Cập nhật docstring đầu module một câu.
4. **Route** (`sales_history.py`): `GET /sales-history/all` với `current_user`. Nhận `from` và `to` là `str | None` (`Query(None, alias="from")`, `Query(None, alias="to")`) và tự `date.fromisoformat` trong `try`, để ngày sai định dạng không ra trang lỗi JSON 422.
   - Thiếu một ngày, sai định dạng, hoặc `first > last`: flash lỗi loại `error`, redirect về `/sales-history`.
   - Không có dòng nào: flash `Không có đơn nào trong khoảng này.` rồi redirect.
   - Có dòng: ghi workbook vào `BytesIO`, trả `Response` với `XLSX` và `Content-Disposition: attachment; filename*=utf-8''<quote(name)>`. Không gọi `save_generated`, không `add`, không `commit`. Nếu phần trả file trùng với route nháp quá vài dòng thì đưa vào một helper chung.
5. **Trang** (`sales_history.html`): thêm một khối nhỏ dưới `card` hiện có, `<form method="get" action="/sales-history/all">` với hai ô `type="date"` `name="from"` và `name="to"` (cùng `required`) và nút **Tải tất cả đơn**. Một dòng `muted`: "Mọi đơn đặt trong khoảng, ở mọi trạng thái, cả đã và chưa xác nhận dán (cột Trạng thái). Để đối chiếu, không dán vào file lịch sử; không có trong bảng File đã tải." Mặc định `from` là ngày 1 của tháng đang chọn và `to` là `until`, truyền từ `sales_history_page` (đã có `first_day` và `until`).
6. **Test workbook** (dùng `tests/sales_history_setup.py`): theo tiêu chí 1 đến 4 của plan.
   - Sáu đơn trong khoảng và một ngoài khoảng; kiểm số đơn, cột 21, ô S và T của từng đơn.
   - Đơn nhiều sản phẩm: `Tiền Vô` và `Trạng thái` chỉ ở dòng đầu.
   - Đơn 23:59 ngày `to` có, đơn 00:00 ngày sau không có; `from == to`.
   - Đơn thiếu mã vật tư dùng `sap_name`/`product_name`; đơn thiếu khách có tên và tỉnh trống.
   - `build_history_workbook(..., draft=True, title=ALL_SHEET)` có 21 cột và đúng tên sheet; file chính vẫn 20 cột tên `sheet1`.
7. **Test route**:
   - Tải thành công, tên file giải mã khớp, `generated_file`, `sales_history_file_order`, `sales_history_exported` không đổi số dòng, và thư mục file sinh ra không có file mới.
   - Từ ngày sau đến ngày; thiếu một ngày; ngày sai định dạng: redirect kèm flash lỗi, không có file.
   - Khoảng không có đơn: flash `Không có đơn nào trong khoảng này.`
   - Tài khoản xem tải được.
   - Trang có form và hai ô ngày có giá trị mặc định.
   - Tải file chính sau khi tải tất cả ra giống trước.

## Verification

- `uv run pytest tests/exports/test_sales_history_workbook.py tests/web/test_sales_history_routes.py`
- `uv run pytest`
- `uv run ruff check`
- Chạy app cục bộ, tải thử một khoảng và mở file bằng Excel để xem sheet và cột 21.

## Risk & Rollback

- Rủi ro chính là bước tách tra cứu làm lệch `collect_rows`. Test hiện có chạy qua không sửa ở bước 1 là cổng chặn trước khi thêm hàm mới.
- Rollback: revert commit. Không migration, không dữ liệu mới.
