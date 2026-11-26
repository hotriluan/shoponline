---
phase: 2
title: "Route /search và trang kết quả"
status: pending
priority: P1
effort: "2.5h"
dependencies: []
---

# Phase 2: Route /search và trang kết quả

## Goal

`GET /search?q=` nhận một mã bất kỳ trong năm loại và đưa người dùng tới đơn: 1 kết quả thì 303 sang trang đơn, nhiều kết quả thì hiện danh sách, không có thì báo "Không tìm thấy".

## Files to Create / Modify

- Create: `src/shoponline/web/routes/search.py`
- Create: `src/shoponline/web/templates/search.html`
- Create: `tests/web/test_order_search.py`
- Modify: `src/shoponline/web/app.py`: import `search` và thêm vào vòng `include_router`

## Design

Chuẩn hóa: `raw = " ".join(q.split())[:100]` (dùng lại `search_words`), `key = raw.replace(" ", "").upper()`. Từ khóa rỗng thì redirect về trang trước hoặc `/`.

Bước 1, khớp chính xác. Mỗi nguồn trả về các cặp `(sales_order.id, nhãn)`; gộp theo id, một đơn có thể mang nhiều nhãn:

| Nhãn | Điều kiện |
|---|---|
| Mã đơn | `func.upper(SalesOrder.platform_order_id) == key` |
| Hóa đơn VAT | join `SapTaxInvoice.delivery == SalesOrder.do_number`, `func.ltrim(tax_invoice_doc, '0') == key.lstrip('0')`, chỉ khi `key.lstrip('0')` khác rỗng |
| SO | `SalesOrder.so_number == key` |
| DO | `SalesOrder.do_number == key` |
| Phiếu trả | `func.replace(func.upper(SalesReturn.doc_no), ' ', '').like(escape(key) + '%', escape='\\')`, mọi `status`; ghi kèm số phiếu, và nhãn "đã hủy" nếu `VOID` |

Escape `\`, `%`, `_` cho LIKE giống `search_filter`. Số phiếu có dạng `NNN/MM.YYYY <hậu tố>` ([numbering.py:31](../../src/shoponline/returns/numbering.py#L31)); bỏ khoảng trắng ở cả hai phía thì gõ đầy đủ hay chỉ phần đầu đều khớp.

Bước 2, quyết định kết quả:
- Đúng 1 đơn: `redirect(f"/orders/{id}")`, dùng helper `redirect` có sẵn (303).
- Từ 2 đơn trở lên: render `search.html` với danh sách.
- 0 đơn và `len(key) >= 4`: khớp một phần bằng `search_filter(raw, SalesOrder.platform_order_id, SalesOrder.so_number, SalesOrder.do_number)`, `limit(50)`, nhãn "Khớp một phần". Nếu khớp một phần cũng chỉ ra đúng 1 đơn thì vẫn hiện danh sách, không tự chuyển trang, vì kết quả gần đúng cần người dùng xác nhận.
- 0 đơn: render trang với thông báo "Không tìm thấy đơn nào khớp với «…»".

Quyền: `Depends(current_user)`. Route chỉ đọc dữ liệu.

`search.html` kế thừa `base.html`, dùng `page_header` từ `_macros.html`. Bảng gồm các cột: Khớp theo · Sàn · Mã đơn (link `/orders/{id}`) · Shop · Lô (link `/batches/{order_batch_id}`, ngày xử lý) · Trạng thái (`states.LABELS`) · Ngày đặt. Sắp xếp `ordered_at` giảm dần. Nạp kèm `batch` và `shop` bằng `selectinload` để tránh N+1.

## Tasks & Steps

- [ ] Viết `search.py`: `normalize`, `exact_matches(db, key) -> dict[int, list[str]]`, `partial_matches`, route `GET /search`.
- [ ] Viết `search.html`; cho ô tìm trên trang kết quả sẵn giá trị `raw`.
- [ ] Đăng ký router trong `app.py`.
- [ ] Viết test với fixture `app` và `login` trong `tests/web/conftest.py`, theo mẫu tạo đơn ở `tests/web/test_return_flags_pages.py` hoặc `test_returns_routes.py`:
  - [ ] mã đơn có khoảng trắng, tab, chữ thường → 303 `/orders/{id}`
  - [ ] số hóa đơn có và không có số 0 ở đầu → cùng một đơn
  - [ ] SO → 303; DO → 303
  - [ ] số phiếu trả đầy đủ, chỉ phần đầu `NNN/MM.YYYY`, và phiếu VOID → ra đơn (VOID có nhãn)
  - [ ] hai đơn khác sàn cùng mã → danh sách 2 dòng, có cột "Khớp theo"
  - [ ] chỉ khớp một phần (≥ 4 ký tự) → danh sách; từ khóa 3 ký tự không khớp → "Không tìm thấy"
  - [ ] từ khóa có `%` hoặc `_` không khớp tràn lan
  - [ ] chưa đăng nhập → chuyển sang `/login`

## Verification

- `uv run pytest tests/web/test_order_search.py -q`
- `uv run ruff check src tests && uv run ruff format --check src tests`

## Risk

Một chuỗi số ngắn có thể vừa là SO vừa là số hóa đơn của hai đơn khác nhau. Khi đó trang danh sách hiện cả hai kèm nhãn, không tự đoán. Chưa kiểm tra xem dải số SO/DO và dải số hóa đơn có thật sự trùng nhau không; dù có trùng thì cách xử lý trên vẫn đúng.
