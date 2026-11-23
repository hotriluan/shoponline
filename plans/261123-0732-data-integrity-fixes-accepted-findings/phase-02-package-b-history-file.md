---
title: "Phase 2: Gói B — file lịch sử"
status: completed
priority: P1
effort: 1d
dependencies: [1]
---

# Phase 2: Gói B — file lịch sử

## Overview

Chặn các đường làm dòng bị lặp hoặc sai khi dán vào file lịch sử Shop Online, và chặn tên khách trở thành công thức Excel.

Bằng chứng: [báo cáo file lịch sử](../reports/data-integrity-audit-261123-1320-history-file.md), mục H1–H7 và D1–D2 của plan `261119-0828`.

## Phát hiện trong gói

| Mã | Mức | Vấn đề | Mã nguồn | Sửa đề xuất |
|---|---|---|---|---|
| H3 | Medium | Tên khách bắt đầu bằng `=`, `+`, `-`, `@` thành công thức Excel; tên từ file sàn | `exports/sales_history_workbook.py:287,307`; nguồn tên `importers/lazada_orders.py:123` | Ghi mọi ô chữ có thể bị hiểu thành công thức dưới dạng chuỗi (`data_type = "s"` hoặc tiền tố `'`) cho cột tên, tên báo cáo và biến thể |
| H1 | Medium | Hai file chưa xác nhận có thể chứa cùng đơn; xác nhận file này, file kia vẫn còn dòng của đơn đã xác nhận; bấm đúp link tải (GET ghi file và sổ) cũng tạo file chồng | `web/routes/sales_history.py:204-239,365-411`; `maintenance/retention.py:158-166` | Xem phương án dưới |
| H2 | Medium | Tiền Vô và Tax Invoice chốt lúc tải; số đến sau hoặc hóa đơn ghi đè không phản ánh vào file đã dán | `exports/sales_history_workbook.py:184-207`; `reconcile/report_ingest.py:93-103,147-175` | Cổng dữ liệu: chạy SQL S5, S5b, S8 của báo cáo trên production. Nếu có lệch thật: khi xác nhận, hiện cảnh báo nếu số đã đổi từ lúc tạo file (so `updated_at` với `generated_file.created_at`). Nếu không có lệch: chấp nhận rủi ro, ghi sổ tay |
| H7 | Low | `Transaction` gộp hai đơn cùng tên, cùng phút (`createTime` bỏ giây) | `exports/sales_history_workbook.py:284,291` | Hỏi kế toán định nghĩa giao dịch; chấp nhận nếu đúng ý |
| D1 (0828) | Low | File nháp cùng tên sheet `sheet1` và 20 cột đầu như file thật, dễ dán nhầm | `sales_history_workbook.py:277`; `templates/sales_history.html:18-20` | Đổi tên sheet của file nháp (một dòng mã) |
| H4, H5, D2 (0828) | Low | Đơn chờ lâu không cảnh báo tuổi; giả định giờ Việt Nam; Tiền Vô trong nháp là số tạm | | Chấp nhận rủi ro, ghi tài liệu |

### Quyết định H1 (chủ dự án chọn phương án 1, 2026-11-23)

- **Phương án 1 (đề xuất):** khi **xác nhận** một file, xóa các file chưa xác nhận khác có chứa đơn vừa xác nhận (file đó chỉ là bản chưa dùng; không ghi sổ nên không mất gì), và khi **tải** mà đã có file chưa xác nhận chứa cùng đơn thì hiện cảnh báo. Không đổi route.
- **Phương án 2:** đổi tải về `POST` (không ghi trên GET) và dùng lại file chưa xác nhận giống hệt. Chống bấm đúp triệt để hơn nhưng đổi hợp đồng route và giao diện.
- Phương án 1 phụ thuộc vào giả định người dùng không đã dán file thứ hai trước khi xác nhận file đầu; hết đúng khi nhiều người cùng làm một tháng.

## Files

- Sửa: `src/shoponline/exports/sales_history_workbook.py`, `src/shoponline/web/routes/sales_history.py`, `src/shoponline/web/templates/sales_history.html`; có thể `src/shoponline/maintenance/retention.py`
- Test: `tests/exports/` (test sales_history workbook), `tests/web/test_sales_history_routes.py`
- Tài liệu (nếu hành vi đổi): `docs/` mục file lịch sử

## Implementation Steps

1. Viết test tái hiện: H3 (ô tên `=1+1` có `data_type` ra `f`), H1 (file A {1,2}, thêm đơn 3, file B {1,2,3}, xác nhận A rồi kiểm B), D1 (tên sheet nháp khác `sheet1`).
2. Sửa H3 và D1 (nhỏ, độc lập).
3. Chốt phương án H1 với chủ dự án rồi làm.
4. H2: chạy SQL trên production (chỉ đọc) và quyết làm cảnh báo hay chấp nhận. Production hiện chưa có file lịch sử nào, nên rất có thể chấp nhận cho tới khi có dữ liệu.
5. Test từng bộ một, `ruff` sạch, cập nhật bảng theo dõi, commit.

## Todo

- [x] Test tái hiện H3, H1, D1
- [x] Sửa H3, D1
- [x] Chốt phương án H1 và làm
- [x] Quyết H2 theo số liệu production
- [x] Ghi H4, H5, H7, D2 là rủi ro chấp nhận
- [x] Test, `ruff`, bảng theo dõi, commit

## Success Criteria

- Tên khách bắt đầu bằng ký tự công thức được ghi thành chuỗi trong file xuất.
- Xác nhận một file không để lại file chưa xác nhận khác chứa đơn đó, và việc tải lại có cảnh báo (hoặc theo phương án 2 đã chọn).
- File nháp có tên sheet khác file thật.
- Mỗi mục có trạng thái cuối.

## Risk

- **Xóa file chưa xác nhận khi xác nhận file khác:** chỉ xóa file không ghi sổ nào. Test phải chứng minh đơn đã xác nhận ở file kia không bị mất.
- **Đổi ô thành chuỗi:** có thể ảnh hưởng ô số; chỉ áp cho cột chữ.

## Rollback

Mỗi sửa là một commit; revert nếu gây lỗi. Không có thay đổi schema.
