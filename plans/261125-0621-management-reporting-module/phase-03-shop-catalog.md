---
phase: 3
title: "Danh mục shop, đơn mang shop"
status: in-progress
priority: P1
effort: "6h"
dependencies: []
---

# Phase 3: Danh mục shop, đơn mang shop

## Goal

Mỗi đơn ghi shop bán ra. Admin chọn shop khi tải file "chờ giao hàng"; file lịch sử Shop Online ghi Division theo shop. Danh mục shop bật hoặc tắt được, để các shop đã ngừng bán lại hoạt động khi cần.

## Bối cảnh

- Các shop cùng một sàn dùng chung một khách hàng SAP (chủ dự án xác nhận). Robot, `platform_setting.sap_customer`, đối chiếu `zrsd001`/`zrsd003`/`zrsd004`, đợt gửi kế toán, `order_batch (platform, processing_date)` và file `ĐƠN HÀNG ONLINE <SÀN>` giữ nguyên.
- Hiện Division là hằng `DIVISION` trong [sales_history_workbook.py](../../src/shoponline/exports/sales_history_workbook.py): SHOPEE → `Shopee Bình Dương`, TIKTOK → `tiktok Bình Dương`, LAZADA → `Lazada Mall`.
- **Không tự nhận shop** (chủ dự án đã bỏ khỏi kế hoạch).

## Thiết kế

- **Migration `0014_shop`:**
  - Bảng `shop`: `code` (String 30, PK), `platform` (FK `platform_setting`), `division` (String 50, unique, đúng chữ ghi vào file lịch sử), `active` (bool), `sort_order` (int).
  - Seed 6 shop:

    | code | platform | division | active |
    |---|---|---|---|
    | `SHOPEE_BD` | SHOPEE | Shopee Bình Dương | true |
    | `SHOPEE_PGT` | SHOPEE | Shopee PGT | false |
    | `SHOPEE_DN` | SHOPEE | Shopee Da Nang | false |
    | `TIKTOK_BD` | TIKTOK | tiktok Bình Dương | true |
    | `LAZADA_MALL` | LAZADA | Lazada Mall | true |
    | `LAZADA` | LAZADA | Lazada | false |

  - Thêm `sales_order.shop_code` (FK `shop`): backfill đơn hiện có bằng shop đang bán của sàn, rồi đặt NOT NULL. <!-- Updated: Validation Session 1 - giả định "mọi đơn hiện có thuộc shop đang bán" chưa kiểm trên production --> **Production (đọc ngày 2026-11-25):** 181 đơn, gồm Shopee 131, TikTok 31, Lazada 19. Dữ liệu đơn không ghi shop, nên backfill chỉ đúng nếu toàn bộ 131 đơn Shopee là của `Shopee Bình Dương`. Chủ dự án đã xác nhận ngày 2026-11-25 rằng cả 131 đơn Shopee hiện có thuộc `Shopee Bình Dương`, nên backfill theo shop đang bán là đúng. <!-- Updated: Validation Session 3 - đã xác nhận -->Sau migration, đếm đơn theo `shop_code` để chắc rằng mỗi đơn đều có shop.
  - Thêm `import_batch.shop_code` (NULL) để biết file nào tải cho shop nào và để chọn sẵn shop tải gần nhất.
- **Trang tải file `/imports`:** sau ô chọn sàn có ô chọn shop (bắt buộc), chỉ hiện shop đang bán của sàn đó (lọc bằng JS trong `app.js`, server kiểm tra lại). Chọn sẵn: sàn chỉ có một shop đang bán thì chọn shop đó; nếu không thì chọn shop của `import_batch` gần nhất của sàn. Shop không thuộc sàn hoặc đã tắt thì từ chối.
- **`import_orders(..., shop_code)`:** đơn mới nhận shop đã chọn. Đơn đã có mà khác shop thì **không đổi**, và trang kết quả liệt kê "đơn X đã thuộc shop Y, giữ nguyên". Admin sửa shop của một đơn ở trang chi tiết đơn (ghi `event_log` `order_shop_changed`).
- **File lịch sử Shop Online:** Division lấy từ `order.shop.division`; bỏ hằng `DIVISION` và lý do chặn `DIVISION_MISSING`.
- **Trang `/shops`** (nhóm "Dữ liệu gốc"): danh sách shop; admin bật/tắt, sửa tên Division, thêm shop mới cho một sàn đã có. Không xóa shop đã có đơn.
- **Hiển thị:** cột Shop ở trang chi tiết lô và chi tiết đơn.

## Files to Create / Modify

- Create: `migrations/versions/0014_shop.py`
- Modify: `src/shoponline/db/models.py` (`Shop`, `SalesOrder.shop_code`, `ImportBatch.shop_code`)
- Modify: `src/shoponline/importers/order_import.py`, `src/shoponline/web/routes/imports.py`, `src/shoponline/web/templates/import_form.html`, `import_result.html`, `src/shoponline/web/static/app.js`
- Modify: `src/shoponline/exports/sales_history_workbook.py`
- Create: `src/shoponline/web/routes/shops.py`, `src/shoponline/web/templates/shops.html`
- Modify: `src/shoponline/web/routes/orders.py`, `batch_detail.html`, `order_detail.html`, `_nav.html`, `src/shoponline/web/app.py`
- Modify: `tests/fixtures/build_fixtures.py` và các helper tạo đơn trong test (`tests/sales_history_setup.py` …) để mỗi đơn có shop.
- Create: `tests/importers/test_import_shop.py`, `tests/web/test_shops.py`

## Tasks & Steps

- [x] Migration, model, backfill (đã chạy trên database test).
- [ ] Chạy `alembic upgrade head` trên database dev (sao lưu trước) và đếm đơn theo `shop_code`.
- [x] `import_orders` nhận shop; kết quả liệt kê đơn khác shop.
- [x] Form tải file và kiểm tra phía server.
- [x] Division theo shop trong file lịch sử.
- [x] Trang `/shops`, sửa shop của đơn, cột Shop.
- [x] Sửa helper test, chạy toàn bộ test.

## Verification

- `uv run pytest` (toàn bộ, vì `import_orders` và file lịch sử là đường dùng chung)
- `uv run ruff check`
- Trên máy chạy thật, trước migration (chỉ đọc): `SELECT platform, count(*), min(ordered_at), max(ordered_at) FROM sales_order GROUP BY platform;`
- Mở `/imports` trên web dev: chọn Shopee thì chỉ thấy `Shopee Bình Dương` được chọn sẵn; bật `Shopee PGT` ở `/shops` thì có hai lựa chọn.

## Risk

- Test và fixture cũ tạo `SalesOrder` không có shop sẽ hỏng khi cột NOT NULL. Đây là phần tốn công nhất; sửa một lần ở helper dùng chung.

## Kết quả (2026-11-25)

Đã làm: migration `0014_shop` (bảng `shop`, seed 6 shop, `sales_order.shop_code` NOT NULL có backfill, `import_batch.shop_code`); model `Shop`; `domain/shops.py` (`active_shops`, `default_shop_code`, `require_choice`, `default_shop`); `import_orders(..., shop_code=None)` (không truyền thì dùng shop mặc định của sàn; đơn đã có giữ shop cũ và vào `result.in_other_shop`); form `/imports` có ô Shop, lọc bằng JS ở `app.js`, server kiểm tra lại; `import_result.html` liệt kê đơn khác shop; Division trong file Shop Online lấy từ `order.shop.division` (bỏ hằng `DIVISION` và lý do `DIVISION_MISSING`); trang `/shops` (bật/tắt, sửa Division, thêm, xóa shop chưa có đơn, luôn giữ ít nhất một shop đang bán mỗi sàn); đổi shop của đơn ở trang chi tiết (`order_shop_changed`); cột Shop ở lô và đơn. Test: `tests/importers/test_import_shop.py`, `tests/web/test_shops.py`; helper `tests/shop_codes.py` (`SHOP`) và tham số `shop_code` của `sales_history_setup.order`. Toàn bộ test đạt khi chạy lần cuối (còn `tests/web` chạy lại sau sửa: 232 đạt).

Còn lại của cổng A: chạy migration trên database dev và đếm đơn theo `shop_code` (mọi đơn phải có shop; đơn Shopee phải đều là `SHOPEE_BD`).
