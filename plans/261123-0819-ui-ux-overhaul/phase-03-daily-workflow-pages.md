---
phase: 3
title: "Trang việc hằng ngày và thanh bước của lô"
status: completed
priority: P1
effort: "1d"
dependencies: [1]
---

# Phase 3: Trang việc hằng ngày và thanh bước của lô

## Goal

Làm lại các trang của luồng hằng ngày bằng component mới. Trang lô có thanh bước cho biết lô đang ở đâu, và các nút được gom thành một hành động chính cùng các hành động phụ.

## Files (phase này sở hữu)

- Modify: `templates/import_form.html`, `templates/import_result.html`, `templates/batches.html`, `templates/batch_detail.html`, `templates/order_detail.html`, `templates/sap_reports.html`, `templates/customers.html`
- Modify: `src/shoponline/web/routes/batches.py`, chỉ để tính `steps` (chỉ đọc) truyền vào template
- Modify/Create: test trong `tests/web/` cho thanh bước

## Steps

1. **Tải file sàn:** chọn sàn bằng các nút chọn có tên sàn thay cho `<select>` (vẫn là `name="platform"`, dùng radio), vùng thả file có nhãn rõ, phần giải thích quy tắc đặt trong khối "Lưu ý" thu gọn được (`<details>`).
2. **Kết quả nhập:** thẻ tóm tắt số đơn mới / cập nhật / lỗi lên trên, các danh sách cảnh báo đặt bên dưới, kèm nút "Mở lô" và "Ánh xạ SAP" khi có đơn thiếu ánh xạ.
3. **Lô đơn:** giữ bảng `data-server` và macro pager; badge trạng thái dùng `status_badge`; cột sàn có badge theo màu sàn (trung tính, có chữ, không chỉ dựa vào màu).
4. **Trang lô, thanh bước:** các bước Nhập file → Ánh xạ đủ → Gửi sales admin → Xác nhận SO/DO → Đối chiếu SO → Gửi kế toán. Suy ra từ dữ liệu sẵn có: còn đơn `MAPPING_ERROR`/`NEED_REVIEW` thì chưa qua bước Ánh xạ; có `confirmed_at` thì qua bước Xác nhận; đã có báo cáo đối chiếu và `report.clean` thì qua bước Đối chiếu; mọi đơn không hủy đã `DELIVERED` thì qua bước Gửi kế toán. Dùng `<ol>` với `aria-current="step"`. Tính trong route (hàm thuần, có test), template chỉ vẽ.
5. **Trang lô, thanh hành động:** hành động chính theo bước hiện tại (ví dụ trước khi xác nhận là "Tải file ĐƠN HÀNG ONLINE"; sau khi xác nhận là "Xuất file gửi kế toán"); các nút còn lại là nút phụ. Giữ nguyên mọi `form action`, `onsubmit confirm`, điều kiện `user.role` và chữ trên nút. Ô ngày goods issue autosave giữ nguyên thuộc tính `data-autosave*`.
6. **Đối chiếu SO:** mỗi mục trong 6 mục lệch là một card có tiêu đề kèm số đếm và badge mức độ; mục rỗng thì không hiện; khi `report.clean` thì hiện một alert thành công.
7. **Chi tiết đơn, Báo cáo SAP, Khách hàng:** áp `page_header` (tiêu đề, breadcrumb về lô, hành động), bảng dùng style mới, form autosave giữ nguyên.

## Verification

- Unit test cho hàm tính bước: lô mới (bước 2 đang mở), lô đã xác nhận nhưng còn lệch (bước 5), lô đã giao hết (xong).
- `uv run pytest tests/web -q` xanh; các test của `test_web_flow.py` và `test_batch_progress.py` không bị sửa.

## Risks

- Đổi `<select>` sàn sang radio có thể làm vỡ test gửi form. Radio gửi cùng `name`/`value` nên không vỡ, nhưng phải chạy `test_web_flow.py`.
