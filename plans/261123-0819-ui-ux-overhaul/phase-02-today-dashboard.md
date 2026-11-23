---
phase: 2
title: "Trang Việc hôm nay"
status: completed
priority: P1
effort: "6h"
dependencies: [1]
---

# Phase 2: Trang Việc hôm nay

## Goal

`/` hiện các việc cần làm hôm nay, mỗi thẻ có một hành động chính. Trang chỉ đọc dữ liệu sẵn có, không thêm bảng hay migration.

## Context

- Hiện `/` chuyển hướng sang `/batches` ([app.py](../../src/shoponline/web/app.py#L241-L243)).
- Nguồn dữ liệu sẵn có: trạng thái `sales_order` và nhãn `states.LABELS` ([domain/states.py](../../src/shoponline/domain/states.py), đã đưa vào template dưới tên `STATUS_LABELS` ở [app.py](../../src/shoponline/web/app.py#L31)), `import_batch.confirmed_at`, `accounting.runs.open_run()` và `due_pairs()` ([accounting/runs.py](../../src/shoponline/accounting/runs.py)), robot state và backup warning có sẵn trong context.
- Có nhiều test gọi `/batches` trực tiếp, nên đổi `/` không ảnh hưởng chúng. Cần tìm test nào đang kiểm tra `/` chuyển hướng hoặc đích của redirect sau đăng nhập (`grep -rn 'get("/"' tests`).

## Files

- Create: `src/shoponline/web/routes/today.py` (route `GET /`)
- Create: `src/shoponline/web/templates/today.html`
- Modify: `src/shoponline/web/app.py` (bỏ redirect `/`, đăng ký router `today`)
- Create: `tests/web/test_today_page.py`

## Thẻ trên trang

| Thẻ | Số liệu | Hành động chính |
|---|---|---|
| Đơn cần xử lý | số đơn `MAPPING_ERROR` và `NEED_REVIEW` | Ánh xạ SAP / mở lô có đơn cần kiểm tra |
| Lô chờ sales admin | lô có đơn `READY` và chưa có `confirmed_at` | Mở lô |
| Lô chờ đối chiếu SO | lô đã xác nhận nhưng còn đơn `READY` chưa có SO | Mở lô |
| Gửi kế toán | đợt `OPEN` (số lượt đang đọc, lỗi), hoặc số cặp sàn × ngày trong `due_pairs()` | Mở đợt / Xuất file gửi kế toán (admin) |
| File Shop Online | đơn `DELIVERED` chưa vào `sales_history_exported`, một câu `COUNT` trên `sales_order` (không gọi `collect_rows`) <!-- Updated: Validation Session 1 - chốt dùng COUNT --> | Mở File Shop Online |
| Hệ thống | trạng thái robot (bật, dừng, chưa xác nhận kết nối) và sao lưu | Robot SAP / Sao lưu |

Thẻ không có việc thì hiện trạng thái "Không có việc" kèm dấu ✓, không ẩn đi, để người dùng biết hệ thống đã kiểm tra. Đầu trang có lời chào kèm ngày hôm nay (`clock.today_vn()`) và nút chính "Tải file sàn".

## Steps

1. Viết hàm thu thập trong `today.py`, mỗi số liệu là một câu `COUNT`/`GROUP BY`. Không gọi `collect_rows` của sales history (nặng). Với viewer, ẩn nút ghi.
2. Template dùng macro `stat`/`card` của phase 1; lưới 3 cột ≥1280px, 2 cột ≥768px, 1 cột dưới đó.
3. Đổi đích chuyển hướng sau đăng nhập tại [login.py](../../src/shoponline/web/routes/login.py#L28) từ `/batches` thành `/` (không có tham số `next` để giữ). Cập nhật test đăng nhập nào đang kỳ vọng `/batches`. <!-- Updated: Validation Session 1 - đăng nhập về / -->
4. Bật mục Việc hôm nay trong `_nav.html`.

## Verification

- `uv run pytest tests/web/test_today_page.py -q`: dựng dữ liệu có 2 đơn `MAPPING_ERROR`, 1 lô chưa xác nhận, 1 đợt `OPEN`; kiểm tra số liệu hiển thị; viewer thấy trang và không thấy nút "Xuất file gửi kế toán"; chưa đăng nhập thì `/` trả 303 sang `/login`.
- `uv run pytest tests/web -q` xanh.

## Risks

- Định nghĩa "lô chờ đối chiếu" có thể lệch với trang lô. Biện pháp: dùng lại đúng hàm hoặc truy vấn mà [batch_detail](../../src/shoponline/web/routes/batches.py) dùng nếu có, không tự định nghĩa lại.
