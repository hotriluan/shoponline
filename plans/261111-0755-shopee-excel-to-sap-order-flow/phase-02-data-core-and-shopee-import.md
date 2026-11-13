---
title: "Phase 2: Lõi dữ liệu và nhập file Shopee, TikTok"
status: done
priority: P1
effort: 5d
dependencies: [1]
---

# Phase 2: Lõi dữ liệu và nhập file Shopee, TikTok

## Overview

Xây schema PostgreSQL và phần logic thuần, không chạm SAP: đơn chung, bộ đọc file "chờ giao hàng" của Shopee và TikTok, ánh xạ sản phẩm sang mã SAP, quy tắc ngày goods issue, trạng thái đơn. Mọi con số đi vào SAP và file gửi kế toán đều qua phần này, nên đây là phần được test dày nhất.

## Key Insights

Lấy từ `docs/Order.toship.20261111_20261111.xlsx` và `docs/Chờ vận chuyển đơn hàngtiktok-2026-11-11-15_44.xlsx`:

| Điểm | Shopee | TikTok |
|---|---|---|
| Sheet, dòng tiêu đề | `orders`, dòng 1 | `OrderSKUList`, dòng 1; **dòng 2 là dòng mô tả cột, không phải dữ liệu** |
| Mã đơn | `Mã đơn hàng`, chuỗi | `Order ID`, chuỗi 18 chữ số |
| Sản phẩm, phân loại | `Tên sản phẩm`, `Tên phân loại hàng` | `Product Name`, `Variation` |
| SKU người bán | `SKU phân loại hàng` = `10` cho mọi màu | `Seller SKU` = `5`; không dùng làm khóa được |
| Số lượng, giá | `Số lượng`, `Giá gốc` (`"120000.00"`) | `Quantity`, `SKU Unit Original Price` (`"120000"`) |
| Trợ giá | `Người bán trợ giá` + `Được Shopee trợ giá`, theo một đơn vị | `SKU Seller Discount` + `SKU Platform Discount`, **theo cả dòng** |
| Ngày đặt | `Ngày đặt hàng`, `2026-11-11 00:04` | `Created Time`, `11/11/2026 11:36:57` |
| Địa chỉ dùng được | `TP / Quận / Huyện`, `Tỉnh/Thành phố` | `District`, `Province` |
| Tên người nhận | Bị che | Bị che |

- Tiêu đề cột Shopee không ở dạng Unicode NFC, và có hai cột chỉ khác chữ hoa/thường: `Tổng số tiền Người mua thanh toán` và `Tổng số tiền người mua thanh toán`. So tên cột sau khi chuẩn hóa NFC và cắt khoảng trắng, có phân biệt hoa thường.
- Cùng một màu, tên phân loại khác nhau giữa hai sàn: Shopee `Cánh gián - 2004,0.8 lít`, TikTok `Cánh gián - 2004, 0.8 lít`. Bảng ánh xạ vì vậy theo từng sàn.
- Mỗi dòng file là một sản phẩm của một đơn. Một đơn có thể nhiều dòng.
- Bộ sản phẩm vẫn là một dòng ra một mã SAP (mã bộ); SAP tự bung thành phần.

## Requirements

- Mỗi sàn một bộ đọc trả về cùng một kiểu đơn chung. Thêm sàn là thêm một file bộ đọc, không sửa phần còn lại.
- Thiếu cột bắt buộc, sai sheet, hoặc một dòng không đọc được thì từ chối cả file, không nhập một phần.
- Mọi ô đọc dạng chuỗi. Tiền chuyển sang số nguyên đồng; có phần lẻ khác 0 thì từ chối.
- Trợ giá lưu theo một đơn vị. Với TikTok, tổng trợ giá của dòng không chia hết cho số lượng thì đơn sang `NEED_REVIEW`.
- Khóa duy nhất `(platform, platform_order_id)`. Nhập lại cùng file không đổi dữ liệu; nhập file mới cập nhật đơn đã có, không lùi trạng thái.
- Dòng không có ánh xạ làm đơn sang `MAPPING_ERROR` kèm tên sản phẩm và phân loại thiếu. Bổ sung ánh xạ xong thì đơn tự được xét lại.
- Chuyển trạng thái chỉ qua một hàm, có ghi `event_log`.

## Architecture

**Bảng**

| Bảng | Nội dung | Ràng buộc |
|------|----------|-----------|
| `platform_setting` | sàn, mã khách hàng SAP, chế độ (`manual`, `shadow`, `live`) | một dòng mỗi sàn |
| `import_batch` | loại file, tên, mã băm, người nhập, thời điểm, số đơn mới / cập nhật / không đổi | |
| `sales_order` | sàn, mã đơn, ngày đặt, trạng thái, ngày xử lý D, ngày goods issue, số SO, số DO | duy nhất `(platform, platform_order_id)` |
| `sales_order_item` | tên sản phẩm, phân loại, số lượng, giá gốc, trợ giá một đơn vị, mã vật tư, tên SAP | |
| `sku_mapping` | sàn, tên sản phẩm, phân loại → mã vật tư, tên SAP | duy nhất `(platform, product_name, variation_name)` sau chuẩn hóa |
| `customer_info` | sàn, mã đơn, tên khách, địa chỉ | duy nhất `(platform, platform_order_id)`; không phụ thuộc `sales_order` để dùng được cho Lazada |
| `event_log` | chuyển trạng thái, nhập file, đổi chế độ, người làm | chỉ thêm |
| `app_user` | người dùng web và vai trò | |

Dữ liệu khởi tạo `platform_setting`: Shopee `1200001145`, Lazada `1200001118`, TikTok `1200001146`, tất cả ở chế độ `manual`.

**Trạng thái đơn:** `NEW` → `READY` → `SO_LINKED` → `DELIVERED`. Nhánh: `MAPPING_ERROR`, `NEED_REVIEW`, `CANCELLED`. `SO_LINKED` là đã lưu số SO; `DELIVERED` là đã thấy DO trong `zrsd004`.

**Mã**

```
domain/order.py          đơn chung và dòng đơn, độc lập với sàn
domain/states.py         bảng chuyển trạng thái hợp lệ, hàm transition
domain/sku_mapping.py    chuẩn hóa khóa (NFC, gộp khoảng trắng), tra mã vật tư
domain/gi_date.py        đề xuất ngày goods issue
domain/expected_value.py giá trị SO mong đợi = Σ (giá gốc − trợ giá) × số lượng
importers/excel_table.py đọc sheet theo tên cột, mọi ô là chuỗi
importers/shopee_orders.py
importers/tiktok_orders.py
importers/order_import.py  upsert đơn, tạo customer_info với địa chỉ mặc định
```

Địa chỉ mặc định: Shopee `"{TP / Quận / Huyện}, {Tỉnh/Thành phố}, Việt Nam"`, TikTok `"{District}, {Province}, Việt Nam"`. Đây là dạng admin đang ghi trong `NOTE TT KH T11.XLSX`.

## Related Code Files

- Create: `src/shoponline/db/models.py`, `migrations/versions/<rev>_core_schema.py`
- Create: `src/shoponline/domain/order.py`, `states.py`, `sku_mapping.py`, `gi_date.py`, `expected_value.py`
- Create: `src/shoponline/importers/excel_table.py`, `shopee_orders.py`, `tiktok_orders.py`, `order_import.py`
- Create: `tests/domain/`, `tests/importers/`, `tests/db/test_constraints.py`
- Create: `tests/fixtures/build_fixtures.py` (dựng file Excel test đúng cấu trúc file thật, dữ liệu tự đặt)

## Implementation Steps

1. Viết `build_fixtures.py`: sinh file Shopee và TikTok có đúng tên sheet, đúng toàn bộ tiêu đề cột của file thật (gồm dạng Unicode và dòng mô tả của TikTok), dữ liệu tự đặt. Không chép dòng dữ liệu thật vào repo.
2. Viết model và migration cho các bảng trên; test ràng buộc duy nhất.
3. Viết `excel_table.py`: tìm sheet theo tên, đọc tiêu đề, chuẩn hóa NFC, báo lỗi liệt kê đủ các cột bắt buộc còn thiếu.
4. Viết `shopee_orders.py` và `tiktok_orders.py`. TikTok bỏ dòng mô tả bằng cách chỉ nhận dòng có `Order ID` toàn chữ số.
5. Viết `sku_mapping.py`; test hai tên chỉ khác khoảng trắng hoặc dạng Unicode ra cùng một khóa, và cùng tên ở hai sàn không dùng lẫn ánh xạ của nhau.
6. Viết `gi_date.py`; test: thứ Hai ra thứ Ba, thứ Sáu ra thứ Hai, thứ Sáu 30/10/2026 ra chính ngày đó vì thứ Hai là 02/11, ngày 31/12 ra chính ngày đó.
7. Viết `states.py` và `expected_value.py`.
8. Viết `order_import.py`; test nhập hai lần không đổi số dòng, nhập file thứ hai trong ngày cộng thêm đơn mới, đơn đã `SO_LINKED` không bị đưa về `READY`.
9. Chạy bộ đọc trên hai file thật trong `docs/` trên máy phát triển và so số đơn, số lượng, giá với file tay `ĐƠN HÀNG ONLINE … 111126`.

## Todo

- [x] File test tự dựng đúng cấu trúc Shopee và TikTok
- [x] Model, migration, test ràng buộc
- [x] Đọc bảng Excel theo tên cột (không dùng chế độ read-only: file sàn thật khai sai kích thước sheet)
- [x] Bộ đọc Shopee
- [x] Bộ đọc TikTok
- [x] Ánh xạ sản phẩm theo từng sàn
- [x] Quy tắc ngày goods issue
- [x] Trạng thái đơn và giá trị SO mong đợi
- [x] Nhập đơn cộng dồn, không lùi trạng thái
- [x] Đối chiếu với file thật trong `docs/` (8/8 đơn Shopee khớp file tay; mã TikTok 18 chữ số giữ nguyên)
- [x] Bộ đọc Lazada (2026-11-13): gom theo `orderNumber`, mỗi dòng là một đơn vị sản phẩm, lấy tên và địa chỉ khách từ cột billing

## Success Criteria

- Hai file thật trong `docs/` nhập được, kết quả khớp file tay về mã đơn, mã vật tư, số lượng, đơn giá.
- File thiếu một cột bắt buộc bị từ chối với thông báo nêu tên cột.
- Mã đơn TikTok 18 chữ số giữ nguyên từng ký tự.

## Verification

- `uv run pytest tests/domain tests/importers tests/db` thoát mã 0.
- `shoponline migrate`, `alembic downgrade base`, `shoponline migrate` không lỗi.

## Risk Assessment

- **Quy tắc trợ giá TikTok chưa có ví dụ thật.** File mẫu có trợ giá bằng 0. Đơn TikTok có trợ giá khác 0 đầu tiên được admin kiểm tra tay; kết quả thêm thành một ca test.
- **Ngày TikTok hiểu nhầm tháng và ngày.** Bộ đọc so ngày đặt với ngày trong tên file và ngày nhập; lệch quá 31 ngày thì từ chối file.
- **Bảng ánh xạ chưa đầy đủ.** Đơn thiếu ánh xạ dừng ở `MAPPING_ERROR`, không đoán.

## Security Considerations

- File sàn che tên và số điện thoại; hệ thống không lưu hai cột này.
- `event_log` không ghi tên hay địa chỉ khách.
- File tải lên lưu ngoài repo, trong thư mục giới hạn quyền.

## Next Steps

Phase 3 dùng đơn đã nhập để sinh file đơn hàng và dựng web.
