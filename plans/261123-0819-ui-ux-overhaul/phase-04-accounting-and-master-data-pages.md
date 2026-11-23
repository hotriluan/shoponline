---
phase: 4
title: "Trang kế toán và dữ liệu gốc"
status: completed
priority: P2
effort: "6h"
dependencies: [1]
---

# Phase 4: Trang kế toán và dữ liệu gốc

## Goal

Làm lại các trang Gửi kế toán, File Shop Online và ba trang dữ liệu gốc bằng component mới, tách rõ phần tiến độ, phần đối chiếu và phần hành động cuối.

## Files (phase này sở hữu)

- Modify: `templates/accounting.html`, `templates/accounting_run.html`, `templates/accounting_preview.html`, `templates/sales_history.html`, `templates/sku_mappings.html`, `templates/report_names.html`

## Steps

1. **Gửi kế toán (danh sách):** card đợt đang mở nổi lên đầu, có hành động chính; lịch sử các đợt bên dưới, giữ phân trang máy chủ.
2. **Trang đợt:** ba vùng theo thứ tự Tiến độ đọc → Đối chiếu → Chốt. Tiến độ: bảng lượt đọc có badge trạng thái và nút Đọc lại; giữ cơ chế tự làm mới 10 giây. Đối chiếu: dòng tóm tắt thành `stat`, hai khung "Chưa thấy DO" và "DO không thuộc đơn nào" thành card cảnh báo. Chốt: card riêng chứa hai ô tích bắt buộc và nút "Chốt và ghi sổ" (biến thể chính); "Hủy đợt" là nút `danger` tách xa nút chốt. Gỡ 4 `style=""` nội tuyến.
3. **File Shop Online:** hàng đầu gồm bộ chọn tháng và hai nút Tải file / Tải file nháp; các hộp Đơn bị chặn, Chờ hóa đơn (có nút Robot đọc zrsd003), Đơn chờ tiền vô (có ô tải file quyết toán) thành card có số đếm; bảng File đã tải dùng badge "Đã xác nhận" / "Chưa xác nhận".
4. **Ánh xạ SAP và Tên báo cáo:** dòng chưa có dữ liệu được tô nền cảnh báo nhẹ; trạng thái autosave của dòng hiện thành badge nhỏ cạnh dòng; khu "Nhập từ Excel" và "tải danh sách ra Excel" gom vào một thanh công cụ trên bảng; nút "Lưu tất cả" dính ở cuối vùng nhìn khi bảng dài (`position: sticky`).

## Verification

- `uv run pytest tests/web/test_accounting_routes.py tests/web -q` xanh, không sửa chữ mà test kiểm tra.
- Không còn `style="` trong các file của phase.

## Risks

- Tự làm mới 10 giây của trang đợt là thẻ `<meta http-equiv="refresh">` đặt trong `{% block head %}` ([accounting_run.html](../../src/shoponline/web/templates/accounting_run.html#L3)), không phải script. Khung `base.html` mới phải giữ `{% block head %}` trong `<head>`. <!-- Updated: Validation Session 1 - sửa mô tả cơ chế làm mới -->
