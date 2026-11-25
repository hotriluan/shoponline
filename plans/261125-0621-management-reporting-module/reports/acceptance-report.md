# Báo cáo nghiệm thu: module báo cáo cho quản lý

Ngày 2026-11-25, trên database dev `shoponline_dev` đã đồng bộ từ máy chạy thật (181 đơn, schema `0012`, sau đó migrate lên `0016` và nạp file lịch sử). Chưa deploy lên máy chạy thật; các bước deploy ở [phase 7](../phase-07-docs-and-acceptance.md) và [deployment-guide.md](../../../docs/deployment-guide.md#báo-cáo-quản-lý-việc-một-lần-khi-bật).

## Tiêu chí của plan

| Tiêu chí | Kết quả | Bằng chứng |
|---|---|---|
| `retention --apply` không xóa `customer_info` | Đạt | Test `tests/maintenance/test_retention.py` (phase 1); `customer_info` trên dev vẫn 181 dòng sau đồng bộ |
| Tiền Lazada nhập tay hiện ở cột "Tiền Vô" và ở đường tiền thực nhận | Đạt | Test phase 2 (`tests/accounting/test_manual_settlement.py`, `tests/web/test_lazada_settlements.py`); `tests/reports/test_report_views.py::test_a_lazada_order_gets_its_hand_typed_money` |
| Mỗi đơn mới mang đúng shop; file lịch sử ghi Division theo shop | Đạt | Test phase 3 (`tests/importers/test_import_shop.py`, `tests/web/test_shops.py`); dev sau migrate: Shopee 131 đơn `SHOPEE_BD`, TikTok 31 `TIKTOK_BD`, Lazada 19 `LAZADA_MALL` |
| Tổng `Customer paid` theo năm và Division khớp file gốc; nạp lại không trùng | Đạt | File 3.006 dòng, loại 0 dòng. So tổng từng (năm, Division) trong file gốc với `report_sale_line`: 19/19 nhóm khớp, 3.006/3.006 dòng. `--apply` lần 1 nạp 3.006 dòng, lần 2 nạp 0 (3.006 đã có) |
| Ba đường doanh thu của một tháng mẫu khớp truy vấn tay | Đạt | Tháng 11/2026 trên dev: `monthly_overview` cho 37.508.836 (trên sàn), 27.758.997 (hóa đơn), 17.193.712 (tiền nhận); truy vấn tay trên `sales_order_item`, `sap_tax_invoice`, `platform_settlement` ra đúng ba số đó |
| `/reports` mở được cho viewer; mỗi bảng tải Excel; tháng 11/2026 ghi rõ thiếu 01–10/11 | Đạt | `tests/web/test_reports.py` (5 trang × có/không bộ lọc, Excel, khoảng đảo ngược); ảnh chụp bằng tài khoản viewer tạm (đã xóa) cho cả 5 trang; ghi chú "Tháng 11/2026 thiếu đơn từ ngày 01 đến 10/11" hiện ở mọi trang |
| `uv run pytest` và `uv run ruff check` sạch | Đạt | `pytest`: 937 đạt, 1 bỏ qua (cần PDF hóa đơn thật), chạy trước khi thêm test trang báo cáo; sau đó 22 test trang và Excel đạt riêng. `ruff check`: sạch |

## Hiệu năng

`monthly_overview` cho cả 59 tháng 2022–2026 trên dev: 57 ms (mục tiêu dưới 500 ms).

## Điều cần biết khi đọc số

- Chênh giá/trợ giá tháng 11/2026 là −229.521: doanh thu hóa đơn gồm thuế nên có thể lớn hơn giá trị trên sàn. Đây là kết quả phép trừ, không phải lỗi.
- Phí sàn 5.405.286 chỉ tính trên đơn có cả hóa đơn lẫn tiền thực nhận; 28 đơn đã giao còn chờ hóa đơn, 57 đơn chờ tiền về.
- 46 dòng lịch sử (19 tên) chưa quy đổi được sang tỉnh: tên huyện trùng ở nhiều tỉnh (Châu Thành, Chợ Mới, Tân Châu, Bảo Lâm, Phước Long, Hòa An…) và ô bị che bằng `*`. Hiện ở "Chưa xác định" cho tới khi admin khai ở **Quy đổi tỉnh**.
- Tháng 11/2026 chưa có phần 01–10/11 (file kế toán chưa có); số tháng này thấp hơn thực tế cho tới khi kế toán gửi file cộng dồn.

## Chưa làm

- Deploy lên máy chạy thật (việc của chủ dự án, theo deployment-guide).
- Chưa kiểm giao diện tối (app không có chế độ tối).
