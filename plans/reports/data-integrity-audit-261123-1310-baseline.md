# Rà soát toàn vẹn dữ liệu: số đếm nền

## Nguồn dữ liệu và giới hạn

- **Nguồn:** database dev (`shoponline_dev` trên `localhost:5432`, role `shoponline_app`), schema ở revision `0011_drive_connection` (đúng head). Chủ dự án chọn dùng DB dev hiện tại (2026-11-23) vì không mở được kết nối tới production (`192.168.18.123:5432` đóng từ máy dev) và chưa có bản sao lưu để diễn tập.
- **Chụp lúc:** 2026-11-23 13:05 (giờ máy dev).
- **Giới hạn:** số đếm phản ánh dữ liệu dev, không phải production. Dữ liệu trải từ 2026-11-11 đến 2026-11-20 (đơn đặt), có vẻ là bản chạy thử thật nhưng không có bằng chứng nó trùng khớp production. Bảng `sales_history_exported` có 0 dòng, nên luồng xác nhận file lịch sử chưa được thử ở dữ liệu này; các bất biến về nó chỉ kiểm được bằng mã và test.
- **Truy cập chỉ đọc:** mọi truy vấn qua công cụ chỉ đọc (phiên `default_transaction_read_only = on`, chỉ chấp nhận `SELECT/WITH/SHOW/EXPLAIN`). Chuỗi kết nối không được in.
- Hai schema: `public` (nghiệp vụ) và `ops` (vận hành, sống sót khi khôi phục `public`).

## Số dòng mỗi bảng

| Bảng | Số dòng | Bảng | Số dòng |
|---|---:|---|---:|
| accounting_baseline | 1 | platform_setting | 3 |
| accounting_run | 5 | platform_settlement | 292 |
| accounting_run_read | 14 | report_item_name | 74 |
| accounting_run_source | 0 | robot_control | 1 |
| accounting_sent_delivery | 117 | sales_history_exported | 0 |
| customer_info | 129 | sales_history_file_order | 37 |
| event_log | 1294 | sales_order | 129 |
| generated_file | 40 | sales_order_item | 134 |
| import_batch | 85 | sap_job | 54 |
| order_batch | 19 | sap_settings | 1 |
| sap_so_ref | 119 | sap_so_ref_item | 128 |
| sap_tax_invoice | 255 | sku_mapping | 549 |
| ops.app_user | 2 | ops.backup_run | 6 |
| ops.backup_settings | 1 | ops.drive_connection | 1 |
| ops.backup_request | 0 | ops.system_state | 1 |

## Phân bố

- **Đơn theo sàn và trạng thái:** Shopee 84 DELIVERED, 6 READY; TikTok 19 DELIVERED, 3 READY, 1 CANCELLED; Lazada 14 DELIVERED, 1 READY, 1 CANCELLED. Không có đơn ở NEW, SO_LINKED, MAPPING_ERROR, NEED_REVIEW.
- **Lô (`order_batch`):** Shopee 7, TikTok 6, Lazada 6; ngày xử lý 2026-11-12 đến 2026-11-20; đã chốt 6, 5, 5.
- **Lô nhập (`import_batch`):** shopee_orders 8, tiktok_orders 7, lazada_orders 7, sku_mapping 9, settlement 3 (Shopee 1, TikTok 2), zrsd001 23, zrsd003 3, zrsd004 25.
- **File sinh ra (`generated_file`):** order_file 27, accounting_file 12, sales_history 1.
- **Đợt kế toán:** 5 đợt, cả 5 FINALIZED (2026-11-16 đến 2026-11-20).
- **Sổ DO đã gửi:** 117 DO; 12 là sổ nền (không có đợt), 105 thuộc đợt.
- **Tiền vô (`platform_settlement`):** TikTok 115 dòng (2026-10-01 đến 2026-11-18), Shopee 177 dòng (2026-11-01 đến 2026-11-19); không có dòng Lazada.

## Lệch trạng thái plan

| Plan | Lệch | Xử lý |
|---|---|---|
| `261113-1230-merged-accounting-file` | `status: pending` và cả 6 phase `pending`, trong khi mã đã commit (`1db7fdb`, 2026-11-13), có test `tests/accounting/*`, journal ghi phase 1-5 và tài liệu xong, và DB có 5 đợt đã chốt | Sửa: `in-progress`; phase 1-5 `completed`; phase 6 `in-progress` (tài liệu xong, chưa có biên bản chạy thử Production) |
| `261111-0755-shopee-excel-to-sap-order-flow` | `status: in-progress`; bảng phase dùng cột "chặng" thay cho trạng thái, không thấy trạng thái phase | Chưa sửa; phase 2 của audit quyết |
| `261111-0431-ecommerce-sap-automation` | `cancelled`, ngoài phạm vi | Không đụng |
| `261113-1142-robot-manual-run-on-demand` | `pending`, khớp (chưa làm) | Phase 6 của audit xác minh |

Các plan còn lại có trạng thái phase ghi tay khớp với journal ở mức quét nhanh; phase phụ trách sẽ kiểm kỹ hơn.
