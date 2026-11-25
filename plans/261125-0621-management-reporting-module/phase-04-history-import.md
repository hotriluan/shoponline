---
phase: 4
title: "Nạp file lịch sử 2022–2026"
status: completed
priority: P1
effort: "10h"
dependencies: [3]
---

# Phase 4: Nạp file lịch sử 2022–2026

## Goal

Toàn bộ dòng hợp lệ của `docs/history/Shop Online 2022-2026-10-luan.xlsx` nằm trong database, đã làm sạch, gắn shop và tỉnh. Phần đơn 01–10/11/2026 nạp được thêm từ file của kế toán sau này mà không trùng dòng.

## Bối cảnh (đã kiểm trên file)

- 3.006 dòng, 19 cột, cùng 17 cột đầu với file hệ thống xuất (`COLUMNS` trong `sales_history_workbook.py`, có dấu cách cuối ở `unitPrice `).
- Không có mã đơn, mã vật tư hay số hóa đơn. Một đơn được nhận biết bằng Division + `billingName` + `createTime` gốc.
- **Kỳ lấy theo cột `month`/`year`** (chủ dự án chốt). `createTime` có ba dạng: `yyyy-mm-dd HH:MM` (2.891), `dd-mm-yyyy HH:MM` (102), `yyyy-dd-mm HH:MM` (185), cộng 13 ô kiểu khác. Các dòng ghi `2026-11-08`/`2026-12-08` mang kỳ 8/2026, tức là đảo ngày với tháng.
- Division có 8 cách viết (`tiktok`/`Tiktok Bình Dương`, `shopee`/`Shopee Bình Dương` …) quy về 6 shop của phase 3, so khớp không phân biệt hoa thường và khoảng trắng.
- `billingCity` có 327 giá trị: tỉnh cũ trước sáp nhập 2025 lẫn tên huyện. Một số ô tiền là chuỗi.

## Thiết kế

- **Migration `0015_history_sales`:**
  - Bảng `history_sale_line`:
    - kỳ và ngày: `period` (Date, ngày 1 của tháng), `ordered_on` (Date, NULL khi không suy ra được);
    - shop và khách: `shop_code` (FK), `customer_name`, `customer_phone`, `city_raw`;
    - sản phẩm và tiền: `item_name`, `size`, `variation`, `quantity`, `customer_paid` (BigInteger), `unit_price` / `seller_discount` / `shipping_fee` (BigInteger NULL);
    - khóa và nguồn: `order_key`, `line_key` (unique), `source_row`, `import_batch_id`.
  - Bảng `province_alias`: `raw_key` (PK, tên đã chuẩn hóa), `province` (một trong 34 tỉnh), `updated_by`, `updated_at`. Seed 63 tỉnh/thành cũ → 34 tỉnh mới theo Nghị quyết 202/2025/QH15. Sáp nhập 2025 gộp nguyên tỉnh, nên quy đổi tỉnh cũ là xác định.
  - Thêm `customer_info.province` (NULL), điền bằng `province_of(address)` khi nhập đơn (`_ensure_customer`) và backfill cho dòng hiện có trong migration.
- **Hằng `REPORTING_CUTOVER = datetime(2026, 11, 11)`** trong `src/shoponline/reports/__init__.py`, dùng chung cho bộ nạp và view.
- **Bộ đọc `src/shoponline/importers/history_file.py`:** nhận cột theo tên; thiếu cột bắt buộc thì từ chối cả file (như các bộ đọc khác). Với mỗi dòng:
  - `period` từ `year`/`month`. Thử ba dạng ngày; `ordered_on` là dạng đầu tiên cho ra đúng tháng của `period`, nếu không có dạng nào thì để NULL.
  - Division → shop; không khớp thì loại dòng.
  - Số lượng và tiền ép về số nguyên; ô không đọc được thì loại dòng (`customer_paid`, `quantity` bắt buộc).
  - **Quy tắc ranh giới:** nhận kỳ ≤ 10/2026. Nhận kỳ 11/2026 chỉ khi `ordered_on` có và trước 2026-11-11. Mọi dòng khác bị loại với lý do.
  - `line_key` = SHA-256 của các trường chuẩn hóa (Division, `createTime` gốc, tên, tên hàng, quy cách, màu, số lượng, `customer_paid`) cộng thứ tự lặp trong file. Hai dòng giống hệt nhau trong cùng file vẫn là hai dòng; nạp lại hoặc nạp file cộng dồn có các dòng cũ thì các dòng đó bị bỏ qua.
- **Lệnh `shoponline history-import <file> [--apply]`:** mặc định chạy thử, in số dòng nhận, số dòng bỏ qua vì đã có, các dòng bị loại (số dòng, lý do) và các `city_raw` chưa quy đổi được kèm số dòng. Với `--apply`, ghi trong một giao dịch, tạo `import_batch` kind `history_sales` (không lưu file vào `uploads/`, `stored_path` trỏ tới file đã chép vào `exports/history/` để giữ làm bằng chứng và có quy tắc giữ trong `kept_files`), ghi `event_log` `history_imported`. Trước `--apply` phải chạy `shoponline backup run --kind db`; lệnh in nhắc việc này và từ chối ở **mọi máy** nếu không có bản `db` thành công trong 2 giờ qua (đọc `ops.backup_run`). <!-- Updated: Validation Session 1 - chặn mọi máy, có cờ bỏ qua --> Máy dev dùng cờ `--skip-backup-check` để bỏ qua; khi dùng cờ này, `event_log` `history_imported` ghi thêm `backup_check_skipped`. Test cả hai nhánh.
- **Trang `/province-aliases`** (nhóm "Dữ liệu gốc", admin sửa, viewer xem): danh sách `city_raw` chưa quy đổi được kèm số dòng (cả lịch sử lẫn `customer_info.address` không ra tỉnh), ô chọn 1 trong 34 tỉnh. Lưu thì ghi `province_alias`. View đọc bảng này lúc truy vấn, nên sửa xong báo cáo đổi ngay.

## Files to Create / Modify

- Create: `migrations/versions/0015_history_sales.py`
- Modify: `src/shoponline/db/models.py`
- Create: `src/shoponline/reports/__init__.py`, `src/shoponline/importers/history_file.py`, `src/shoponline/reports/history_import.py`, `src/shoponline/domain/provinces.py` (bảng 63 → 34; tách từ `report_names.py` nếu cần dùng chung `_key`)
- Modify: `src/shoponline/importers/order_import.py` (`customer_info.province`), `src/shoponline/maintenance/retention.py` (`kept_files` giữ file trong `exports/history/`), `src/shoponline/cli.py`
- Create: `src/shoponline/web/routes/province_aliases.py`, `src/shoponline/web/templates/province_aliases.html`; Modify `_nav.html`, `app.py`
- Create: `tests/fixtures/history_sample.xlsx` (tự dựng, có đủ các ca: ba dạng ngày, Division viết khác, ô tiền là chuỗi, kỳ 11/2026 trước và sau ngày 11, dòng trùng hệt), `tests/importers/test_history_file.py`, `tests/reports/test_history_import.py`, `tests/web/test_province_aliases.py`

## Tasks & Steps

- [ ] Migration, model, seed tỉnh.
- [ ] Bộ đọc và các quy tắc; test từng quy tắc với fixture tự dựng.
- [ ] Lệnh CLI chạy thử và `--apply`, chặn khi chưa sao lưu.
- [ ] `customer_info.province` khi nhập đơn và backfill.
- [ ] Trang quy đổi tỉnh.
- [ ] Chạy thử trên file thật ở máy dev, đọc báo cáo, đối chiếu tổng theo năm và Division với tổng tính thẳng từ file.

## Verification

- `uv run pytest tests/importers/test_history_file.py tests/reports tests/web/test_province_aliases.py`
- `uv run shoponline history-import "docs/history/Shop Online 2022-2026-10-luan.xlsx"`: báo cáo chạy thử không có dòng nào bị loại vì lỗi đọc mà không có lý do rõ.
- Chạy `--apply` hai lần trên database dev: lần hai nhận 0 dòng mới.

## Risk

- File gốc chứa tên và số điện thoại khách (một phần đã che). Bản chép trong `exports/history/` nằm trong thư mục dữ liệu, được sao lưu mã hóa như mọi file khác; không đưa file vào git.
- File Excel trong `docs/` đã bị `.gitignore` loại (`docs/**/*.XLSX`, kiểm tra bằng `git check-ignore`), nên file lịch sử không lọt vào git.

## Kết quả (2026-11-25)

Code và test xong: migration `0015_history_sales`, `domain/provinces.py`, `importers/history_file.py`, `reports/history_import.py`, lệnh `history-import`, `customer_info.province`, trang `/province-aliases`, retention giữ `exports/history/`. Test mới đạt; toàn bộ test trước phase này đạt (882).

Đọc thử file thật bằng bộ đọc (không cần database): nhận 3.006 dòng, loại 0 dòng; với từng năm và shop, tổng `Customer paid` từ file khớp tổng các dòng nhận; 199 tên `billingCity` (733 dòng) chưa quy đổi, hầu hết là quận/huyện/thành phố (Thủ Đức, Phan Thiết, Bình Thạnh, Đà Lạt…) để admin gán ở `/province-aliases`.

Quy đổi quận/huyện tự động (`domain/districts.py`, nạp vào `province_alias` ở migration): chỉ liệt kê tên không trùng trên cả nước; "Châu Thành", "Chợ Mới", "Tân Châu", "Bảo Lâm", "Hòa An", "Phước Long" để admin chọn. Dòng chưa quy đổi giảm từ 733 xuống 46 (19 tên, còn lại là tên mơ hồ và ô bị che bằng `*`).

Cổng B đã chạy trên `shoponline_dev` (2026-11-25): sao lưu `db` bằng `shoponline backup run` (thư mục `C:\dev\shoponline-backup-dev`, mật khẩu đặt riêng cho bản này); database ở `0015_history_sales`; mọi đơn có shop (Shopee 90 đơn đều `SHOPEE_BD`, TikTok 23 `TIKTOK_BD`, Lazada 16 `LAZADA_MALL`); chạy thử nhận 3.006 dòng, loại 0; `--apply` lần 1 nạp 3.006 dòng, lần 2 nạp 0 dòng (3.006 đã có).
