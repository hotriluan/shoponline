---
phase: 1
title: "Dữ liệu: dòng trừ theo giá sàn"
status: completed
priority: P1
effort: "1d"
dependencies: []
---

# Phase 1: Dữ liệu: dòng trừ theo giá sàn

## Goal

Lúc phát hành phiếu, lưu phần bị trừ theo dòng đơn sàn và giá sàn vào một bảng duy nhất, để file Shop Online và báo cáo cùng đọc một nguồn.

## Context

- `sales_return_line` là dòng SO SAP (chỉ dòng chính của kit), không có liên kết tới `sales_order_item`. Hai bên chung `material_number`.
- `reconcile/so_link.py:326` đã ghép dòng chính SAP với dòng sàn theo `(material_number, quantity)`, nên một mã vật tư trên đơn sàn ứng với cùng mã và cùng số lượng trên SO.
- Migration mới nhất: `0017_customer_address_source`.

## Files to Create / Modify

- Create: `migrations/versions/0018_return_sale_lines.py`
- Create: `src/shoponline/returns/sale_lines.py`
- Modify: `src/shoponline/db/models.py` (ba model mới)
- Modify: `src/shoponline/returns/service.py` (`build_preview` chặn khi không quy đổi được; `issue` ghi dòng trừ)
- Modify: `src/shoponline/cli.py` (lệnh bổ sung dòng trừ cho phiếu cũ)
- Create: `tests/returns/test_sale_lines.py`; Modify: `tests/returns/test_service.py`

## Data model

- `sales_return_sale_line`: `return_id` (FK `sales_return`, CASCADE), `sales_order_item_id` (FK `sales_order_item`), `quantity` (int > 0), `customer_paid` (bigint ≥ 0). PK `(return_id, sales_order_item_id)`.
- `sales_history_file_return`: `generated_file_id` (FK `generated_file`), `return_id`, `kind` (`ISSUE` | `VOID`). PK `(generated_file_id, return_id, kind)`. Ghi lại file nào chứa dòng của phiếu nào; phase 3 dùng.
- `sales_return_history_exported`: `return_id`, `kind` (`ISSUE` | `VOID`), `generated_file_id`, `confirmed_by`, `confirmed_at`. PK `(return_id, kind)`. Ghi lại dòng của phiếu đã dán; phase 3 dùng.

Ba bảng tạo trong cùng migration 0018 để chỉ chạy migration một lần.

## Tasks & Steps

1. Sao lưu database dev trước khi chạy migration (quy tắc dự án).
2. Viết `sale_lines.split(order_items, return_lines) -> list[SaleLine] | Blocked` là hàm thuần:
   - Với mỗi mã có `return_qty > 0`: lấy các dòng sàn cùng mã. Tỷ lệ = `return_qty / invoice_qty`.
   - Số lượng trừ của từng dòng sàn = `item.quantity × tỷ lệ`; phải là số nguyên, nếu không thì `Blocked("Mã X trả N không chia đúng vào các dòng của đơn sàn")`.
   - Tiền trừ = `(unit_price − unit_subsidy) × số lượng trừ`.
   - Không có dòng sàn nào cùng mã, hoặc tổng số lượng dòng sàn khác `invoice_qty`: `Blocked` nêu rõ mã.
   - Trả cả đơn cho ra đúng các dòng gốc.
3. `build_preview`: gọi `split` và đưa lý do chặn vào `reasons`. Đưa dòng trừ vào `fields` của fingerprint để bản đã duyệt khớp bản phát hành.
4. `issue`: ghi `sales_return_sale_line` cùng transaction với phiếu.
5. Lệnh CLI `shoponline return-sale-lines backfill`: với mọi phiếu (cả `VOID`) chưa có dòng trừ, tính và ghi. In danh sách phiếu bị chặn, không ghi phiếu đó. Chạy được nhiều lần.
6. Kiểm tra downgrade của 0018 xóa ba bảng mà không đụng `sales_return`.

## Verification

- `uv run pytest tests/returns -q`
- Test `split`: trả cả đơn; trả một phần một dòng; hai dòng sàn cùng mã khác giá; tỷ lệ cho số lẻ bị chặn; mã không có trên đơn sàn bị chặn; đơn kit (dòng chính).
- Test `issue`: dòng trừ được ghi; khi bị chặn thì không cấp số, không ghi file.
- `uv run alembic upgrade head` rồi `downgrade -1` trên database dev đã sao lưu.

## Risks

- Đơn có số lượng sàn và SO khác nhau (combo): `split` chặn. Nếu xảy ra thật thì sửa đơn hoặc mở rộng quy đổi sau, không đoán.
