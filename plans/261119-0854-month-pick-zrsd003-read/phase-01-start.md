---
title: "Phase 1: Ô chọn tháng và khoảng đọc zrsd003"
status: completed
---

# Phase 1: Ô chọn tháng và khoảng đọc zrsd003

## Overview

Đổi trang File Shop Online từ chọn ngày sang chọn tháng đặt hàng, và tính khoảng Billing Date cho zrsd003 từ tháng đó đến hôm nay.

## Files

- Sửa: `src/shoponline/web/routes/sales_history.py`
- Sửa: `src/shoponline/web/templates/sales_history.html`
- Sửa: `tests/web/test_sales_history_routes.py`

Không đổi `collect_rows`/`pending_orders` trong `src/shoponline/exports/sales_history_workbook.py`: chúng vẫn nhận `until: date`.

## Requirements

- Tham số `month` (chuỗi `YYYY-MM`) thay `until` ở: `GET /sales-history`, `GET /sales-history/file`, `GET /sales-history/draft`, `POST /sales-history/read-zrsd003` (Form), `POST /sales-history/settlement` (Form), và mọi link/redirect `back` trong các route đó.
- `month` vắng mặt thì dùng tháng trước của `today_vn()`.
- `month` sai dạng trả 422 (dùng kiểu FastAPI kiểm được, ví dụ hàm parse ném `RequestValidationError` hoặc `HTTPException(422)`); không để `ValueError` thành 500.
- `until` nội bộ = ngày cuối tháng (`calendar.monthrange`).
- `_invoice_range(result, first_day)` trả `(min(first_day, ngày đặt sớm nhất của đơn chờ hóa đơn), today_vn())`, hoặc `None` khi không có đơn chờ hóa đơn (giữ hành vi ẩn hộp zrsd003).
- Tháng tương lai không gây lỗi: đơn chờ hóa đơn luôn đặt trước hôm nay, nên `start <= today`.

## Implementation Steps

1. Thêm helper trong route, ví dụ `_month_bounds(month: str | None) -> tuple[date, date, str]` trả ngày 1, ngày cuối và chuỗi `YYYY-MM` đã chuẩn hóa; tháng trước tính bằng `today_vn().replace(day=1) - timedelta(days=1)`.
2. Thay `until: date | None` bằng `month: str | None` trong năm route; `back = f"/sales-history?month={month}"`.
3. Sửa `_invoice_range` nhận `first_day`; gọi với ngày 1 của tháng ở trang và ở `read_zrsd003`.
4. Template: `<input type="month" name="month" value="{{ month }}">` với nhãn "Tháng đặt hàng"; câu mô tả đầu trang đổi "đặt tới hết ngày chọn" thành "đặt tới hết tháng chọn"; các link `?until=` và hidden input đổi sang `month`; câu trong hộp `#tax-invoice` giữ hiện khoảng ngày (đã có sẵn).
5. Cập nhật test hiện có dùng `until=` sang `month=`; thêm test cho tiêu chí 1–5 của plan (khóa thời gian bằng monkeypatch `today_vn` như các test hiện có làm, nếu có; nếu chưa có thì patch tại module route).

## Todo

- [x] Helper tháng, mặc định tháng trước, 422 khi sai dạng
- [x] Năm route dùng `month`
- [x] `_invoice_range` bắt đầu ở `min(ngày 1, đơn tồn sớm nhất)`
- [x] Template ô tháng và link
- [x] Test: lọc theo tháng, khoảng 01/10→hôm nay, đơn tồn 25/09, mặc định tháng trước, tháng sai dạng
- [x] `uv run pytest tests/web/test_sales_history_routes.py`, rồi `uv run pytest` và `uv run ruff check`

## Success Criteria

Tiêu chí 1–6 của [plan.md](./plan.md) đạt; test robot (`tests/web/test_robot_web.py`) vẫn qua vì form tay trên trang Robot SAP không đổi.

## Rủi ro và rollback

Chỉ đổi web, không có dữ liệu mới; rollback bằng revert commit.
