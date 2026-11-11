---
title: "Phase 3: Mô hình dữ liệu và lõi đơn hàng"
status: todo
priority: P1
effort: 4d
dependencies: [1]
---

# Phase 3: Mô hình dữ liệu và lõi đơn hàng

## Overview

Xây schema PostgreSQL và phần logic thuần (không gọi mạng, không chạm SAP): đơn chung, máy trạng thái, ánh xạ SKU, tính giá và phân bổ voucher, nhật ký sự kiện, mã hóa token. Đây là phần được kiểm thử dày nhất vì mọi con số kế toán đi qua nó.

Ứng với V2 mục 3.3 và mục 5 (trạng thái đơn).

## Requirements

- Schema đủ các bảng của V2 mục 3.3, tạo bằng migration.
- Khóa duy nhất `(shop_id, platform_order_id)` trên bảng đơn.
- Mỗi chứng từ SAP gắn với một đơn và một loại; không thể có hai SO cho một đơn.
- Tiền lưu bằng số nguyên đồng. Không dùng số thực cho tiền.
- Chuyển trạng thái chỉ đi qua một hàm; hàm này từ chối chuyển không hợp lệ và ghi `event_log`.
- Token và dữ liệu cá nhân người mua được mã hóa khi lưu.

## Architecture

**Bảng**

| Bảng | Nội dung chính | Ràng buộc đáng chú ý |
|------|----------------|----------------------|
| `shop` | sàn, mã shop, mã khách hàng SAP, nhà máy, kho, token mã hóa, hạn quyền kết nối | duy nhất `(platform, platform_shop_id)` |
| `sync_cursor` | mốc thời gian lấy đơn gần nhất | một dòng mỗi shop |
| `sales_order`, `sales_order_item` | đơn chung, trạng thái, các khoản tiền, bản gốc JSON từ sàn | duy nhất `(shop_id, platform_order_id)` |
| `sku_mapping`, `sku_mapping_component` | SKU sàn → một hoặc nhiều mã vật tư SAP, hệ số quy đổi | duy nhất `(shop_id, platform_sku)` |
| `sap_document` | loại (SO, DO, BILLING, RETURN), số chứng từ, trạng thái | duy nhất `(order_id, doc_type)` cho chứng từ còn hiệu lực |
| `shipment` | vận đơn, hãng, tracking, thời điểm in, đóng gói, bàn giao | |
| `sap_job` | hàng đợi SAP | khóa chống trùng `(job_type, order_id)` cho việc tạo chứng từ |
| `event_log` | chuyển trạng thái, thao tác SAP/API, người duyệt | chỉ thêm, không sửa |
| `settlement_line`, `invoice_export` | đối soát và hóa đơn | tạo bảng ở phase 9 và 10 |
| `app_user` | người dùng Web UI và vai trò | |

Bảng đơn đặt tên `sales_order` vì `order` là từ khóa SQL.

**Máy trạng thái**

`NEW → VALIDATING → READY_FOR_SO → SO_CREATED → DO_CREATED → LABEL_READY → PACKED → PGI_DONE → HANDED_OVER`

Nhánh: `MAPPING_ERROR`, `STOCK_SHORT`, `SAP_ERROR`, `NEED_REVIEW`, `CANCELLED`, `RETURNED`. Bảng chuyển hợp lệ là một cấu trúc dữ liệu duy nhất trong `domain/states.py`. Đơn bị hủy hoặc hoàn khi đã có chứng từ SAP luôn sang `NEED_REVIEW`.

**Tính giá**

`domain/pricing.py` nhận đơn chung và quy tắc từ sổ quyết định, trả về danh sách dòng SO mong đợi (mã vật tư, số lượng, giá, các điều kiện giảm giá) và tổng giá trị mong đợi. Phân bổ voucher cấp theo đơn dùng phương pháp số dư lớn nhất trên số nguyên đồng, để tổng phân bổ luôn bằng đúng voucher.

## Related Code Files

- Create: `src/shoponline/db/models.py`
- Create: `migrations/versions/<rev>_core_schema.py`
- Create: `src/shoponline/domain/order.py` (đơn chung, độc lập với sàn)
- Create: `src/shoponline/domain/states.py`
- Create: `src/shoponline/domain/sku_mapping.py`
- Create: `src/shoponline/domain/pricing.py`
- Create: `src/shoponline/domain/events.py`
- Create: `src/shoponline/crypto.py`
- Create: `tests/domain/test_states.py`, `tests/domain/test_sku_mapping.py`, `tests/domain/test_pricing.py`, `tests/db/test_constraints.py`

## Implementation Steps

1. Viết model và migration cho các bảng trên, trừ `settlement_line` và `invoice_export`.
2. Viết test ràng buộc: chèn hai đơn cùng `(shop_id, platform_order_id)` phải lỗi; chèn hai SO còn hiệu lực cho một đơn phải lỗi.
3. Định nghĩa đơn chung trong `domain/order.py`: mã đơn sàn, thời điểm, dòng hàng, giá niêm yết, voucher shop, voucher sàn, phí vận chuyển, hình thức thanh toán (gồm COD), hạn giao cho shipper, địa chỉ.
4. Viết `states.py` với bảng chuyển hợp lệ và hàm `transition(order, new_state, reason, actor)` ghi `event_log` trong cùng giao dịch.
5. Viết `sku_mapping.py`: tra SKU, bung combo thành nhiều mã vật tư theo hệ số, trả lỗi `MAPPING_ERROR` kèm SKU thiếu.
6. Viết `pricing.py` theo `docs/decisions/business-rules.md`. Mỗi quy tắc là một hàm nhỏ có tên trùng với mục trong sổ quyết định.
7. Viết test giá bằng 20 đơn mẫu mỗi sàn của phase 2, so với số kế toán đã xác nhận. Thêm test thuộc tính: tổng phân bổ bằng voucher, không dòng nào âm, kết quả không phụ thuộc thứ tự dòng.
8. Viết `crypto.py` mã hóa và giải mã bằng khóa từ biến môi trường; áp dụng cho token và các trường cá nhân người mua.

## Todo

- [ ] Model và migration lõi
- [ ] Test ràng buộc duy nhất
- [ ] Đơn chung
- [ ] Máy trạng thái và `event_log`
- [ ] Ánh xạ SKU có combo
- [ ] Tính giá và phân bổ voucher
- [ ] Test giá trên đơn mẫu đã được kế toán xác nhận
- [ ] Mã hóa token và dữ liệu cá nhân

## Success Criteria

- Giá trị SO mong đợi do `pricing.py` tính khớp tuyệt đối với số kế toán xác nhận trên toàn bộ đơn mẫu.
- Mọi chuyển trạng thái không có trong bảng đều bị từ chối và có test.
- Migration chạy lên và chạy xuống sạch trên database trống.

## Verification

- `uv run pytest tests/domain tests/db` thoát mã 0.
- `shoponline migrate` rồi `alembic downgrade base` rồi `shoponline migrate` không lỗi.

## Risk Assessment

- **Quy tắc giá chưa chốt.** Viết phần còn lại trước; `pricing.py` chỉ hoàn tất khi các mục giá trong sổ quyết định đã ký. Không tự đoán quy tắc.
- **Đơn mẫu chưa phủ hết trường hợp.** Mỗi sai lệch phát hiện ở shadow mode (phase 7) được thêm thành một đơn mẫu mới.

## Rollback

`alembic downgrade` về phiên bản trước. Chưa có dữ liệu thật ở phase này.

## Security Considerations

- Bản gốc JSON từ sàn có thể chứa dữ liệu cá nhân; cột này được mã hóa và có thời hạn lưu (đặt ở phase 12).
- `event_log` không ghi tên, điện thoại, địa chỉ người mua.

## Next Steps

Phase 4 chuyển dữ liệu sàn về đơn chung. Phase 6 dùng `sap_job`.
