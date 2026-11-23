---
title: "Phase 3: Gói C — nhập đơn bỏ qua im lặng"
status: completed
priority: P1
effort: 1d
dependencies: [1]
---

# Phase 3: Gói C — nhập đơn bỏ qua im lặng

## Overview

Mỗi chỗ nhập đơn đang bỏ dòng hoặc bỏ đơn mà không báo phải chuyển thành lỗi rõ hoặc cảnh báo hiển thị cho người dùng. Gói này **không đổi dữ liệu của đơn đã có SO hoặc DO**: chỉ báo.

Bằng chứng: [báo cáo đơn hàng và SAP](../reports/data-integrity-audit-261123-1320-orders-sap.md), mục 4–7 và 10 của Red Team Review plan `261111-0755`.

## Phát hiện trong gói

| Mã | Mức | Vấn đề | Mã nguồn | Sửa đề xuất |
|---|---|---|---|---|
| 6 | Medium | TikTok: dòng có mã đơn rỗng hoặc không phải chữ số bị bỏ im lặng, đơn mất dòng hàng hoặc mất cả đơn. Đã tái hiện: 3 dòng vào, 1 dòng ra, không lỗi. Mã đơn là số trong ô Excel (float) có thể mất chữ số | `importers/tiktok_orders.py:58-60` | Từ chối file bằng `FileRejected` kể tên số dòng bị bỏ; đọc cột mã đơn dưới dạng chữ, không qua float. Dòng mở rộng của đơn nhiều sản phẩm (cột đơn trống đúng quy ước) vẫn hợp lệ nếu quy ước TikTok có; **kiểm quy ước trước khi từ chối** |
| 5 | Medium | Sàn đổi nội dung đơn (số lượng, giá) sau khi đã có SO: file nhập lại bị bỏ qua, `batch_report` so SO với dữ liệu đơn cũ nên không thấy lệch | `importers/order_import.py:178-179`, `reconcile/so_link.py:274-296` | Khi file khác nội dung đơn đã có SO/DO/hủy: ghi sự kiện `order_changed_after_so` và hiện số đơn này trong kết quả nhập và báo cáo lô. **Không ghi đè** dữ liệu đơn |
| 4 | Medium | Đơn đã ở lô D1 mà xuất hiện trong file nhập cho D2 vẫn ở D1, chỉ đếm `unchanged` | `importers/order_import.py:133-139,178-179` | Đếm riêng "đã thuộc lô khác" và hiện trong kết quả nhập, kèm ngày lô. Không chuyển lô tự động |
| 7 | Medium | Đơn `MAPPING_ERROR`/`NEED_REVIEW` không vào file đơn hàng, và sau khi xác nhận lô không nằm trong "đơn READY chưa có SO", nên có thể không bao giờ có SO mà không ai thấy | `exports/order_workbook.py:63-64,116`, `reconcile/so_link.py:247-250`, `web/routes/batches.py:90-92` | Thêm vào báo cáo lô mục "đơn bị loại khỏi file đơn hàng và chưa có SO" (MAPPING_ERROR, NEED_REVIEW) với liên kết tới đơn |
| 10 | Low | Tải file đơn hàng hai lần trước khi đọc zrsd001: file thứ hai liệt kê lại đơn READY đã nhập SO | `exports/order_workbook.py:63`, `web/routes/batches.py:127-146` | Chấp nhận rủi ro: `duplicate_po` bắt sau khi đọc zrsd001; ghi sổ tay |
| 8, 9, 12 | Low | Không có UNIQUE trên `so_number`/`do_number`; hai người nhập chồng gây lỗi 500 nhưng không hỏng dữ liệu; `sap_so_ref` không xóa | `db/models.py:117-118`, `order_import.py:41-52`, `so_link.py:71-100` | Chấp nhận rủi ro; ghi sổ tay. Không thêm migration |

## Files

- Sửa: `src/shoponline/importers/tiktok_orders.py`, `src/shoponline/importers/order_import.py`, `src/shoponline/reconcile/so_link.py`, `src/shoponline/web/routes/batches.py`, `src/shoponline/web/templates/batch_detail.html` (và mẫu kết quả nhập)
- Test: `tests/importers/test_order_import.py`, `tests/importers/test_platform_readers.py`, `tests/reconcile/test_so_link.py`, `tests/web/test_web_flow.py`
- Tài liệu: `docs/` hướng dẫn nhập đơn (chỉ phần cảnh báo mới)

## Implementation Steps

1. Test tái hiện cho 6 (dựng lại từ kịch bản scratchpad: dòng mã đơn rỗng và không phải số), 5 (đơn có SO, file mới đổi giá), 4 (đơn D1 xuất hiện trong file D2), 7 (đơn MAPPING_ERROR sau xác nhận lô). Xác nhận fail.
2. Mục 6 trước: kiểm quy ước dòng mở rộng của TikTok trong mã và file mẫu để không từ chối nhầm dòng hợp lệ.
3. Sửa 6, 5, 4, 7 theo bảng, chỉ thêm cảnh báo và đếm.
4. Ghi 10, 8, 9, 12 là rủi ro chấp nhận (làm trong phase 6).
5. Test từng bộ một: importers, reconcile, web; `ruff` sạch; cập nhật bảng theo dõi; commit.

## Todo

- [x] Test tái hiện 6, 5, 4, 7
- [x] Kiểm quy ước dòng mở rộng TikTok
- [x] Sửa 6, 5, 4, 7
- [x] Test, `ruff`, bảng theo dõi, commit

## Success Criteria

- File TikTok có dòng mã đơn rỗng hoặc không phải số bị từ chối với số dòng cụ thể (trừ dòng mở rộng hợp lệ); đơn nhiều sản phẩm vẫn nhập đúng.
- Nhập lại file đổi nội dung đơn đã có SO tạo cảnh báo hiển thị, không đổi dữ liệu.
- Kết quả nhập nêu số đơn đã thuộc lô khác.
- Báo cáo lô liệt kê đơn bị loại khỏi file đơn hàng và chưa có SO.

## Risk

- **Từ chối nhầm file hợp lệ (mục 6):** kiểm bằng file mẫu thật trong `tests/fixtures`. Nếu có nghi ngờ thì chỉ cảnh báo, không từ chối.
- **Cảnh báo quá nhiều:** chỉ cảnh báo khi nội dung thực sự khác.

## Rollback

Revert commit; không có thay đổi schema.
