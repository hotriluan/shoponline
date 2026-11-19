---
phase: 1
title: "Bảng quyết toán, bộ đọc và nhập"
status: completed
priority: P2
effort: "4h"
dependencies: []
---

# Phase 1: Bảng quyết toán, bộ đọc và nhập

## Goal
Đọc file quyết toán Shopee hoặc TikTok (tự nhận sàn theo sheet/header), lưu từng dòng giao dịch theo khóa duy nhất để nhập lại không cộng trùng.

## Bằng chứng từ file mẫu
- **Shopee** `shopee.xlsx`: sheet "Transaction Report"; phần tóm tắt ở trên (dòng 6 có tên đăng nhập người bán), header bảng chi tiết ở dòng 18 (`Ngày`, `Loại giao dịch`, `Chi tiết`, `Mã đơn hàng`, `Dòng tiền`, `Số tiền`, `Trạng thái`, `Số dư Ví sau giao dịch`). Số tiền là số thực (`90300.0`, `-2700.0`). `Ngày` là text `%Y-%m-%d %H:%M:%S`. `Trạng thái` đều "Giao dịch thành công". Dòng "Điều chỉnh" có `Mã đơn hàng` = `-` (mã đơn chỉ nằm trong `Chi tiết`; theo quyết định 4 không tính). 3 đơn chỉ có một dòng "Tiền ra" -2.700 (giao không thành công). Không có mã giao dịch.
- **TikTok** `tiktok.xlsx`: 4 sheet, sheet đầu "Chi tiết đơn hàng", header dòng 1, 66 cột. Sheet "Giải thích về phí" định nghĩa `ID đơn hàng/điều chỉnh` là ID giao dịch và `ID đơn hàng liên quan` (cột 55) là đơn liên quan; với 115 dòng "Đơn hàng" hai cột bằng nhau. `Tổng số tiền quyết toán` là chữ số dạng text, có thể bằng 0 (21 dòng) và **có thể âm** (1 dòng `-2565`). `Thời gian quyết toán đơn hàng` là text `%Y/%m/%d`. Có cột `Số tiền điều chỉnh`. Lưu ý: mở với `read_only=True` chỉ thấy 21 cột, phải mở thường như `read_table` đang làm. **[Red team]**
- **Lazada** `lazada.xlsx`: sheet "Balance Transactions", không có mã đơn, phải bị từ chối.

## Files to Create / Modify
- Modify: `.gitignore` — thêm `docs/**/*.xlsx` (và `.XLSX`, `.xls`) để file mẫu có mã đơn thật trong `docs/tienvo/` không bị commit. **[Red team]**
- Create: `migrations/versions/0009_platform_settlement.py` — bảng `platform_settlement`.
- Modify: `src/shoponline/db/models.py` — model `PlatformSettlement`.
- Modify: `src/shoponline/importers/excel_table.py` — tách `read_sheet(ws, …)` khỏi `read_table` để nhận sàn và đọc bảng dùng chung một lần mở workbook; tham số `header_marker`; hàm `parse_signed_money`. **[Red team]**
- Create: `src/shoponline/importers/settlement_files.py` — `read_settlement_file(path) -> SettlementFile(platform, rows, skipped)`.
- Modify: `src/shoponline/reconcile/report_ingest.py` — `ingest_settlement(session, record, actor)`.
- Modify: `tests/fixtures/build_fixtures.py` — dựng file Shopee/TikTok/Lazada quyết toán nhỏ theo đúng bố cục mẫu.
- Create: `tests/importers/test_settlement_files.py`, `tests/reconcile/test_settlement_ingest.py`.

## Tasks & Steps
0. `.gitignore`: thêm mẫu cho `docs/**`; kiểm bằng `git check-ignore -v docs/tienvo/shopee.xlsx` ra dòng khớp. Làm trước mọi commit của kế hoạch. **[Red team]**
1. Bảng `platform_settlement`: `id` PK, `platform` String(20), `platform_order_id` String(40), `line_key` String(200), `amount` BigInteger (có dấu), `settled_at` DateTime (giờ VN, không zone), `import_batch_id` FK `import_batch.id` NOT NULL, `updated_at`. Unique `(platform, line_key)`; index `(platform, platform_order_id)`. Migration `0009_platform_settlement`, `down_revision = "0008_sap_tax_invoice"`.
2. `excel_table`: tách phần đọc một worksheet thành `read_sheet(ws, …, header_row=1, header_marker=None)`; `read_table` mở workbook như cũ (không `read_only`) rồi gọi `read_sheet`, chữ ký và hành vi với 7 nơi gọi hiện có không đổi. `header_marker`: dòng đầu tiên có ô đầu bằng marker (so bằng `normalize_header`) là header; số dòng trong thông báo lỗi tính theo header tìm được. Không tìm thấy thì `FileRejected`. **[Red team]**
3. `parse_signed_money(text, field)`: dùng chung phần đọc số với `parse_money` (DRY) nhưng cho phép âm; **ô trống là lỗi** (không thành 0); số phải hữu hạn (`Decimal.is_finite()`), nguyên, và trị tuyệt đối < 10^15, sai thì `ValueError` để gom thành lỗi dòng. `parse_money` giữ nguyên hành vi (trống → 0, âm → lỗi, cùng câu báo lỗi). Cả Shopee và TikTok đọc tiền bằng `parse_signed_money`. **[Red team]**
4. `read_settlement_file`: mở workbook một lần, nhận sàn rồi gọi `read_sheet` trên sheet đó:
   - sheet "Transaction Report" → Shopee: bảng từ marker `Ngày`; cột bắt buộc gồm cả `Trạng thái`. Bỏ dòng có `Mã đơn hàng` rỗng hoặc `-`. Chỉ giữ dòng `Trạng thái` = "Giao dịch thành công"; dòng có mã đơn nhưng trạng thái khác thì đếm vào số bỏ qua. `settled_at` = `Ngày` theo `%Y-%m-%d %H:%M:%S`. `line_key` = `mã đơn|Ngày|Loại giao dịch|Số tiền|#n`, trong đó `n` là thứ tự lần xuất hiện của bộ bốn đó trong cùng file (1, 2, …), để hai giao dịch giống hệt vẫn là hai dòng, file chồng kỳ vẫn cho cùng khóa, và một câu upsert không chạm một khóa hai lần. **[Red team]**
   - sheet đầu có cột `Tổng số tiền quyết toán`, `ID đơn hàng/điều chỉnh` và `ID đơn hàng liên quan` → TikTok: `line_key` = `ID đơn hàng/điều chỉnh`; `platform_order_id` = `ID đơn hàng liên quan` (trống thì lấy ID giao dịch); `settled_at` = `Thời gian quyết toán đơn hàng` theo `%Y/%m/%d` (không dùng lại bộ đọc ngày của `tiktok_orders`, nó đọc ngày trước). Chỉ giữ `Loại giao dịch` = `Đơn hàng` (quyết định 6); dòng loại khác được trả về trong `skipped` kèm ID giao dịch và `ID đơn hàng liên quan` để báo cho người dùng. ID giao dịch lặp trong file → lỗi dòng. **[Red team]**
   - sheet "Balance Transactions" → `FileRejected("File Lazada Balance Transactions không có mã đơn, không lấy được tiền vô theo đơn")`.
   - khác → `FileRejected` liệt kê hai mẫu nhận được.
   Mã đơn dài quá 40 ký tự hoặc `line_key` quá 200 ký tự là lỗi dòng. Lỗi từng dòng gom lại, có lỗi thì từ chối cả file (như `read_zrsd003`). Không có dòng nào được giữ thì từ chối.
5. `ingest_settlement`: thêm `record`, đặt `record.platform` theo sàn đã nhận; upsert theo `(platform, line_key)` (cập nhật `amount`, `settled_at`, `import_batch_id`, `updated_at`). Đếm: `new_count` = khóa chưa có; `updated_count` = khóa có sẵn mà `amount` hoặc `settled_at` khác; `unchanged_count` = phần còn lại. Trả `SettlementImport(platform, kept, skipped, orders, new, updated, unchanged)`. **[Red team]**
6. Đối chiếu mã đơn TikTok ngay trong phase này: so `ID đơn hàng liên quan` của `docs/tienvo/tiktok.xlsx` với Order ID trong các file đơn TikTok đã có ở `docs/` (reviewer đã thấy trùng vài mã) và ghi kết quả vào journal. Không khớp thì dừng, hỏi chủ dự án trước phase 2. **[Red team]**
   <!-- Updated: Validation Session 1 - kết quả sơ bộ trên file mẫu -->
   Validate đã đối chiếu sơ bộ: 7/7 mã 18 số trong `Chờ vận chuyển đơn hàngtiktok-2026-11-11-15_44.xlsx`, `tiktok.xlsx`, `ĐƠN HÀNG ONLINE TIKTOK 111126.xlsx` đều có trong `ID đơn hàng liên quan`; bước này chỉ cần chạy lại bằng code thật và ghi journal.
7. Test:
   - hai file mẫu dựng bởi fixture ra đúng sàn, số dòng, số âm (Shopee -2.700, TikTok -2565), bỏ "Điều chỉnh";
   - Shopee bỏ dòng trạng thái khác "Giao dịch thành công" và đếm vào bỏ qua;
   - Shopee có hai dòng giống hệt → lưu hai dòng, tổng gấp đôi; nhập lại vẫn hai dòng;
   - TikTok dòng loại khác "Đơn hàng" nằm trong `skipped` kèm ID; `platform_order_id` lấy từ `ID đơn hàng liên quan`;
   - tiền trống, `Infinity`, `1E+30`, mã đơn quá dài → từ chối với số dòng đúng;
   - Lazada và file lạ bị từ chối; header Shopee lệch vài dòng vẫn đọc được;
   - nhập lại cùng file không đổi số dòng, đếm vào `unchanged`; hai file Shopee chồng kỳ không cộng trùng;
   - `parse_money` giữ hành vi cũ (test hiện có vẫn xanh).

## Verification
- `uv run pytest tests/importers tests/reconcile -q`
- `uv run alembic upgrade head` trên DB dev, rồi `uv run alembic downgrade -1` và `upgrade head` lại.
- Chạy `read_settlement_file` trên ba file trong `docs/tienvo/`: Shopee 177 dòng, TikTok 115, Lazada bị từ chối.
- `git check-ignore -v docs/tienvo/shopee.xlsx` có kết quả.

## Risks
- Shopee đổi câu chữ header (`Ngày`), tên sheet hoặc chữ "Giao dịch thành công": từ chối file hoặc bỏ dòng, sửa hằng số.
- Shopee chỉnh lại số tiền của cùng giao dịch trong lần export sau sẽ thành khóa mới và cộng cả hai (số tiền nằm trong khóa vì file không có mã giao dịch). Chưa thấy trong mẫu; chấp nhận và ghi ở docs.
