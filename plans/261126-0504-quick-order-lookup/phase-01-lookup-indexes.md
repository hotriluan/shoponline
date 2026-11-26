---
phase: 1
title: "Index cho các cột tra cứu"
status: pending
priority: P2
effort: "1h"
dependencies: []
---

# Phase 1: Index cho các cột tra cứu

## Goal

Tra theo mã đơn (không biết sàn), theo DO và theo số hóa đơn VAT đã bỏ số 0 ở đầu đều dùng được index, để vẫn nhanh khi dữ liệu tăng qua nhiều năm.

## Context

- `sales_order` chỉ có unique `(platform, platform_order_id)`; cột đầu là `platform` nên tra theo mã đơn mà không biết sàn thì không dùng được index này.
- `sales_order.so_number` đã có index; `do_number` chưa có.
- `sap_tax_invoice.tax_invoice_doc` lưu kèm số 0 ở đầu; code kế toán đã so khớp bằng `ltrim(tax_invoice_doc, '0')` ([settlement_invoice_file.py:106](../../src/shoponline/accounting/settlement_invoice_file.py#L106)).
- `sales_return.doc_no` đã unique. Số phiếu ít, nên không thêm index biểu thức cho nó.

## Files to Create / Modify

- Create: `migrations/versions/0020_order_lookup_indexes.py` (`down_revision = "0019_report_views_net_of_returns"`)
- Modify: `src/shoponline/db/models.py`: khai báo cùng các index trong `__table_args__` hoặc `index=True`, để model khớp với schema

## Tasks & Steps

- [ ] Sao lưu DB dev trước khi chạy migration, theo cách đã dùng trước đây: `pg_dump -Fc -f backups-local/shoponline_dev-before-0020-261126.dump <db>`.
- [ ] Viết migration, `upgrade()` gồm:
  - `CREATE INDEX ix_sales_order_platform_order_id_upper ON sales_order (upper(platform_order_id))`
  - `CREATE INDEX ix_sales_order_do_number ON sales_order (do_number)`
  - `CREATE INDEX ix_sap_tax_invoice_doc_trimmed ON sap_tax_invoice (ltrim(tax_invoice_doc, '0'))`
  - `downgrade()` drop cả ba index.
- [ ] Cập nhật `models.py`: `do_number` thêm `index=True` (tên index sinh ra phải trùng với tên trong migration), thêm `Index("ix_sales_order_platform_order_id_upper", func.upper(platform_order_id))` và index tương tự cho `SapTaxInvoice`.
- [ ] Chạy `uv run shoponline migrate` trên DB dev. Chạy `alembic downgrade -1` rồi `upgrade head` để thử đường lùi.

## Verification

- `uv run pytest tests/db`: test DB dùng head revision (`tests/conftest.py::_head_revision`), nên migration mới được áp dụng.
- `\d sales_order` và `\d sap_tax_invoice` có index mới.

## Risk / Rollback

Thêm index không đổi dữ liệu và chạy nhanh trên bảng nhỏ. Lùi bằng `alembic downgrade 0019_report_views_net_of_returns`.
