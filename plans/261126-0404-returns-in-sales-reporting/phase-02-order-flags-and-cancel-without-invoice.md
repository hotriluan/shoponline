---
phase: 2
title: "Nhãn đơn và hủy đơn chưa có hóa đơn"
status: completed
priority: P1
effort: "0.5d"
dependencies: [1]
---

# Phase 2: Nhãn đơn và hủy đơn chưa có hóa đơn

## Goal

Có một hàm dùng chung cho biết đơn đã hủy hoặc trả và theo phiếu nào. Đơn có DO bị hủy trước khi xuất hóa đơn đánh dấu hủy được.

## Files to Create / Modify

- Create: `src/shoponline/returns/flags.py`
- Modify: `src/shoponline/domain/states.py` (`DELIVERED → CANCELLED`)
- Create: hàm `cancel_order` (đặt ở `src/shoponline/domain/states.py` hoặc module order hiện có, theo chỗ gần nhất)
- Modify: `src/shoponline/web/routes/orders.py` (route hủy gọi `cancel_order`; `can_cancel` theo quy tắc mới)
- Modify: `src/shoponline/web/templates/order_detail.html` (nhãn, nút hủy cho đơn đã có DO, cảnh báo)
- Create: `tests/returns/test_flags.py`; Modify: test route đơn trong `tests/web/`

## Tasks & Steps

1. `flags.of(session, order_ids) -> dict[int, ReturnFlag]` với `ReturnFlag(label, doc_no, reason_kind, full_return, return_id)`. Một truy vấn cho cả danh sách, chỉ phiếu `ISSUED`. Nhãn:
   - `CANCEL` và trả cả đơn: "Hủy sau HĐ";
   - `RETURN` và trả cả đơn: "Trả hàng";
   - trả một phần (cả hai lý do): "Trả một phần".
   Đơn `CANCELLED` không có phiếu thì dùng nhãn trạng thái sẵn có, hàm này không xử lý.
2. Máy trạng thái: thêm `CANCELLED` vào `ALLOWED[DELIVERED]`.
3. `cancel_order(session, order, actor, reason)`:
   - lý do bắt buộc;
   - nếu đơn `DELIVERED` mà DO đã có trong `sap_tax_invoice` thì từ chối: "Đơn đã có hóa đơn: lập phiếu trả hàng";
   - nếu DO nằm trong `accounting_sent_delivery` thì vẫn hủy, nhưng trả về cảnh báo "DO đã gửi kế toán ở đợt đã chốt: báo kế toán bằng tay";
   - gọi `transition` (ghi event như cũ).
4. Route `/orders/{id}/cancel` gọi `cancel_order`, hiện cảnh báo nếu có. `can_cancel` tính theo `cancel_order` (đơn mở, `SO_LINKED`, hoặc `DELIVERED` chưa có hóa đơn).
5. Trang chi tiết đơn: nhãn phiếu trả cạnh trạng thái; với đơn `DELIVERED` chưa có hóa đơn, nút hủy có dòng giải thích "chỉ dùng khi DO đã hủy trong SAP".
6. Rà mọi chỗ gọi `transition(..., CANCELLED, ...)`; hiện chỉ có route đơn. Thêm test để chỗ gọi mới phải qua `cancel_order`.

## Verification

- `uv run pytest tests/returns/test_flags.py tests/web -q -k "order or flag or cancel"`
- Test: đơn `DELIVERED` có hóa đơn bị từ chối; chưa có hóa đơn thì hủy được; DO đã gửi kế toán thì hủy được kèm cảnh báo; hủy xong thì đơn rời `pending_orders` của file Shop Online và `_pending_orders` của kế toán.
- Test nhãn: ba nhãn; phiếu `VOID` không ra nhãn.

## Risks

- Đơn đã dán vào file Shop Online rồi mới hủy: không xảy ra, vì đơn chưa có hóa đơn thì bị chặn ở file Shop Online (chờ hóa đơn). Thêm test khẳng định điều này.
