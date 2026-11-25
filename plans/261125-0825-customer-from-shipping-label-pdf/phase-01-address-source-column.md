---
phase: 1
title: "Cột nguồn địa chỉ"
status: done
priority: P1
effort: "2h"
dependencies: []
---

# Phase 1: Cột nguồn địa chỉ

## Goal

`customer_info` biết địa chỉ hiện tại do file Excel, nhãn PDF hay admin ghi, để phase 3 quyết định được khi nào
ghi đè không cần hỏi.

## Files

- Create: `migrations/versions/0017_customer_address_source.py` (revises `0016_report_views`)
- Modify: `src/shoponline/db/models.py` (`CustomerInfo`, quanh dòng 181)
- Modify: `src/shoponline/importers/order_import.py` (`_ensure_customer`, dòng 282-308)
- Modify: `src/shoponline/web/routes/customers.py` (`save_customer`)
- Modify tests: `tests/importers/test_order_import.py`, `tests/web/` (test của trang khách hàng hiện có,
  tìm bằng `grep -l "/customers/save" tests/web`)

## Steps

1. Sao lưu database dev trước khi chạy migration (theo quy tắc dự án; dùng lệnh sao lưu `db` có sẵn).
2. Migration thêm `address_source VARCHAR(10) NULL`, có `CHECK (address_source IN ('file','label','admin'))`.
   Không điền ngược dòng cũ. `downgrade` xóa cột. Docstring nêu ý nghĩa NULL: chưa rõ nguồn, nhãn hỏi trước khi
   ghi đè.
3. Model: `address_source: Mapped[str | None] = mapped_column(String(10))` kèm comment ngắn.
4. `_ensure_customer`: mọi chỗ gán `address = parsed.default_address` (tạo mới và điền ô trống) đặt thêm
   `address_source = "file"`.
5. `save_customer`: so địa chỉ mới (đã `strip`) với địa chỉ cũ; chỉ khi khác thì gán địa chỉ, tính lại
   `province`/`place_key` và đặt `address_source = "admin"` (địa chỉ bị xóa trống thì đặt NULL). Ô tự lưu gửi cả
   hàng, nên sửa tên không được đổi nguồn địa chỉ.

## Todo

- [ ] Sao lưu database dev
- [ ] Migration `0017` + model
- [ ] `_ensure_customer` đặt `file`
- [ ] `save_customer` đặt `admin` chỉ khi địa chỉ đổi
- [ ] Test

## Verification

- Test: nhập Excel tạo dòng mới thì `address_source == "file"`; điền ô địa chỉ trống cũng `file`.
- Test: admin lưu cùng địa chỉ, chỉ đổi tên, thì nguồn giữ nguyên; admin đổi địa chỉ thì `admin`.
- `uv run alembic upgrade head` rồi `downgrade -1` rồi `upgrade head` trên database dev chạy sạch.
- `uv run pytest tests/importers/test_order_import.py tests/web -q`.

## Risks

- Dòng cũ có NULL nên đơn cũ phải xác nhận khi tải nhãn. Chấp nhận (quyết định của chủ dự án); đơn mới đều có nguồn.
