---
phase: 1
title: "Bảng mới, tách tỉnh/thành, retention"
status: completed
priority: P2
effort: "5h"
dependencies: []
---

# Phase 1: Bảng mới, tách tỉnh/thành, retention

## Goal
Có nơi lưu tên báo cáo theo mã vật tư và sổ đơn đã vào file lịch sử, một hàm thuần lấy tỉnh/thành từ địa chỉ, và retention không xóa tên của đơn chưa xuất.

## Bối cảnh
- Models: [models.py](../../src/shoponline/db/models.py). Migration mới nhất: [0006_accounting_runs.py](../../migrations/versions/0006_accounting_runs.py).
- Địa chỉ mặc định được ghép bởi [`default_address`](../../src/shoponline/domain/order.py) thành `<phường/xã>, <tỉnh/thành>, Việt Nam`; Lazada có thêm số nhà phía trước. Admin có thể sửa địa chỉ ở trang Khách hàng.
- Trên production mọi địa chỉ kết thúc bằng `, <tỉnh/thành>, Việt Nam`; có tiền tố `Thành phố `/`Tỉnh ` hoặc không (Lazada, một phần TikTok).
- File lịch sử ghi tỉnh/thành không tiền tố: `Hồ Chí Minh`, `Hà Nội`, `An Giang`.
- Retention ([retention.py:57-81](../../src/shoponline/maintenance/retention.py)) xóa `customer_info` quá hạn khi đơn không tồn tại, đã hủy, hoặc DO đã có trong `accounting_sent_delivery`; ngược lại giữ (`held_orders`). Test: [test_retention.py](../../tests/maintenance/test_retention.py).

## Files to Create / Modify
- Modify: `src/shoponline/db/models.py`: thêm `ReportItemName`, `SalesHistoryFileOrder`, `SalesHistoryExported`.
- Create: `migrations/versions/0007_sales_history.py`. <!-- Updated: Validation Session 1 - migration also holds the export ledger -->
- Create: `src/shoponline/domain/report_names.py`: tách tỉnh/thành và gợi ý tên báo cáo.
- Modify: `src/shoponline/maintenance/retention.py`: điều kiện giữ tên mới và docstring.
- Create: `tests/domain/test_report_names.py`.
- Modify: `tests/maintenance/test_retention.py`.

## Tasks & Steps
1. **Bảng `report_item_name`:** `material_number` String(20) khóa chính, `item_name` Text, `size` Text, `variation` Text (cả ba bắt buộc, không rỗng), `updated_by` String(50), `updated_at` timestamptz `server_default now()`, `onupdate now()`.
2. **Bảng `sales_history_file_order`:** `generated_file_id` (FK `generated_file`), `sales_order_id` (FK `sales_order`), khóa chính gồm cả hai. Ghi danh sách đơn có trong một file đã tải. <!-- Updated: Validation Session 1 - export ledger -->
3. **Bảng `sales_history_exported`:** `sales_order_id` khóa chính (FK `sales_order`), `generated_file_id` (FK `generated_file`, có index), `confirmed_by` String(50), `confirmed_at` timestamptz `server_default now()`. Khóa chính bảo đảm một đơn chỉ được xác nhận một lần.
4. Migration `0007_sales_history`, `down_revision = "0006_accounting_runs"`, `downgrade()` xóa ba bảng theo thứ tự ngược.
5. **`province_of(address: str | None) -> str | None`** trong `domain/report_names.py`:
   - chuẩn hóa NFC, tách theo dấu phẩy, bỏ phần rỗng;
   - bỏ phần cuối nếu là `Việt Nam` (không phân biệt hoa thường), lấy phần cuối còn lại;
   - bỏ tiền tố `Thành phố `, `Tỉnh `, `TP. `, `TP ` (không phân biệt hoa thường);
   - trả về tên trong `PROVINCES` nếu khớp (so sánh sau NFC và `casefold`), còn lại trả `None`.
   - `PROVINCES`: 34 tỉnh/thành sau sáp nhập 2025, ghi đúng chính tả như file lịch sử: Hà Nội, Huế, Lai Châu, Điện Biên, Sơn La, Lạng Sơn, Quảng Ninh, Thanh Hóa, Nghệ An, Hà Tĩnh, Cao Bằng, Tuyên Quang, Lào Cai, Thái Nguyên, Phú Thọ, Bắc Ninh, Hưng Yên, Hải Phòng, Ninh Bình, Quảng Trị, Đà Nẵng, Quảng Ngãi, Gia Lai, Khánh Hòa, Lâm Đồng, Đắk Lắk, Hồ Chí Minh, Đồng Nai, Tây Ninh, Cần Thơ, Vĩnh Long, Đồng Tháp, Cà Mau, An Giang. Chấp nhận thêm cách viết dấu cũ (`Khánh Hoà`, `Thanh Hoá`) và ánh xạ về chính tả trên.
6. **`suggest_report_name(platform_names) -> ReportNameSuggestion`** (hàm thuần; `platform_names` là các cặp tên sản phẩm và tên phân loại từ `sku_mapping` của cùng mã):
   - kích cỡ: phần sau dấu phẩy cuối của tên phân loại (`Cánh gián - 2004,0.8 lít` ra `0.8 lít`), cắt khoảng trắng;
   - variation: `Màu sắc:` + phần trước dấu phẩy cuối; không có phần màu thì để trống;
   - itemName: tên sản phẩm bắt đầu bằng `Propan - ` có đuôi ` - <kích cỡ>`, bỏ đuôi đó; không có thì để trống;
   - các cặp cho kết quả khác nhau: chọn giá trị xuất hiện nhiều nhất, hòa thì để trống.
7. **Retention:** với đơn `DELIVERED`, chỉ xóa `customer_info` quá hạn khi DO đã có trong `accounting_sent_delivery` **và** đơn có trong `sales_history_exported`; thiếu một trong hai thì vào `held_orders`. Đơn không tồn tại hoặc đã hủy giữ nguyên cách cũ. Cập nhật docstring đầu file và thông báo "giữ lại" trên CLI nếu đang nói lý do (`cli.py`, lệnh `retention`). <!-- Updated: Validation Session 1 - keep names until exported -->
8. Test:
   - `province_of`: mọi dạng ở tiêu chí 7 của plan, địa chỉ `None`, địa chỉ không có tỉnh hợp lệ, chữ NFD, cách viết `Hoà`;
   - `suggest_report_name`: `('Propan - ULTRAN VERNIS - V-09 - Sơn Dầu Bóng Màu - 0.8 lít', 'Cánh gián - 2004, 0.8 lít')` ra `Propan - ULTRAN VERNIS - V-09 - Sơn Dầu Bóng Màu` / `0.8 lít` / `Màu sắc:Cánh gián - 2004`; chỉ có tên kiểu Shopee (`V-09 VN-0.8L - …`) thì itemName trống;
   - retention: đơn `DELIVERED` có DO đã gửi kế toán nhưng chưa xuất được giữ; có cả hai thì xóa; các test retention cũ vẫn qua (sửa dữ liệu test cũ để thêm dòng `sales_history_exported` nơi chúng mong đợi bị xóa).

## Verification
- `uv run pytest tests/domain/test_report_names.py tests/maintenance`
- `uv run pytest tests/db` (schema dựng lại từ đầu trên database `*_test`)
- `uv run ruff check src tests`

## Risk & Rollback
- Danh sách tỉnh sai chính tả làm chặn xuất oan; phase 5 kiểm trên dữ liệu thật.
- Retention giữ tên lâu hơn cho đơn chưa xuất; ghi trong tài liệu bảo mật (phase 5).
- Lùi lại: `alembic downgrade 0006_accounting_runs` xóa ba bảng; hoàn lại `retention.py`.
