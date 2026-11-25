---
phase: 3
title: "Ghi kết quả vào customer_info"
status: done
priority: P1
effort: "3h"
dependencies: [1, 2]
---

# Phase 3: Ghi kết quả vào customer_info

## Goal

Một hàm dịch vụ áp quy tắc ghi tên và địa chỉ cho danh sách nhãn, trả về kết quả đếm được và danh sách chờ xác
nhận; không commit, không ghi log có tên/địa chỉ.

## Files

- Create: `src/shoponline/importers/customer_labels.py`
- Create: `tests/importers/test_customer_labels.py`

## Thiết kế

`apply_labels(session, labels, *, confirmed: set[tuple[str, str]] = frozenset()) -> LabelApplyResult`

Với mỗi nhãn (bỏ qua nhãn có platform không có trong `platform_setting`):

| Trường | Hiện có | Hành động |
|---|---|---|
| Tên | trống | ghi |
| Tên | giống (so sau khi gộp khoảng trắng) | giữ |
| Tên | khác | chờ xác nhận |
| Địa chỉ | trống | ghi, nguồn `label` |
| Địa chỉ | giống | giữ |
| Địa chỉ | khác, nguồn `file` hoặc `label` | ghi, nguồn `label` |
| Địa chỉ | khác, nguồn `admin` hoặc NULL | chờ xác nhận |

- Nhãn bị phase 2 đánh dấu `conflicting` luôn vào nhóm chờ xác nhận.
- Đơn có `(platform, order_id)` nằm trong `confirmed` thì ghi đè cả tên và địa chỉ, nguồn `label`.
- Chưa có dòng `customer_info` thì tạo mới (giống `save_customer`, cho phép trước khi nhập Excel).
- Mỗi lần ghi địa chỉ tính lại `province = province_of(...)`, `place_key = place_key(...)`; dùng lại helper
  này, không viết logic tỉnh mới.
- Một đơn có cả phần ghi được và phần phải hỏi (ví dụ tên trống, địa chỉ do admin sửa): ghi phần ghi được, đưa
  phần còn lại vào chờ xác nhận.
- `LabelApplyResult`: `written`, `unchanged`, `pending: list[PendingLabel]` (mã đơn, giá trị hiện có, giá trị trên
  nhãn cho từng trường khác nhau), `without_order` (số đơn chưa có `sales_order`).

## Todo

- [ ] `apply_labels` + kiểu kết quả
- [ ] Test từng dòng của bảng quy tắc
- [ ] Test liên phase: đọc nhãn trước rồi nhập Excel (`_ensure_customer`) thì tên, địa chỉ nhãn giữ nguyên

## Verification

- `uv run pytest tests/importers/test_customer_labels.py tests/importers/test_order_import.py -q`.
- Test bảo đảm không có chỗ nào gọi `log_event` hay logger với tên/địa chỉ (đọc code + test chỉ kiểm số đếm).
