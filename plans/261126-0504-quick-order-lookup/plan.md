---
title: "Tra cứu nhanh đơn hàng"
description: "Một ô tra cứu trên mọi trang: dán mã đơn sàn, số hóa đơn VAT, SO, DO hoặc số phiếu trả hàng là tới thẳng trang đơn."
status: pending
priority: P1
effort: 5h
branch: main
tags: [feature, frontend, backend, database]
blockedBy: []
blocks: []
created: 2026-11-26
---

# Tra cứu nhanh đơn hàng

## Overview

Một ô tra cứu trên mọi trang: dán mã đơn sàn, số hóa đơn VAT, SO, DO hoặc số phiếu trả hàng là tới thẳng trang đơn. Hiện tại người dùng phải mở từng lô ở `/batches` để tìm.

Nguồn quyết định: [brainstorm-261126-1200-quick-order-lookup.md](../reports/brainstorm-261126-1200-quick-order-lookup.md) (đã chốt hướng A, có SO/DO/phiếu trả, "số hóa đơn" là `tax_invoice_doc`).

Scope Challenge: HOLD SCOPE. Tái dùng `/orders/{id}`, `search_filter` trong `web/pagination.py` và layout `base.html`. Khoảng 9 file, 1 module route mới, không thêm service hay lớp mới.

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Index cho các cột tra cứu](./phase-01-lookup-indexes.md) | Pending |
| 2 | [Route /search và trang kết quả](./phase-02-search-route.md) | Pending |
| 3 | [Ô tra cứu trên mọi trang và tài liệu](./phase-03-search-box-and-docs.md) | Pending |

Phase 2 dùng được ngay cả khi chưa có phase 1, vì index chỉ giúp tăng tốc. Phase 3 cần phase 2.

## Non-goals

Tìm theo tên khách, số điện thoại hay sản phẩm; tìm trong `history_sale_line`; tìm theo số billing SAP (`billing_doc`); typeahead.

## Success Criteria

- [ ] Dán mã đơn sàn đầy đủ (có khoảng trắng hoặc tab, khác chữ hoa/thường) thì nhận 303 sang `/orders/{id}`.
- [ ] Số hóa đơn VAT có hoặc không có số 0 ở đầu đều ra cùng một đơn.
- [ ] Số SO, số DO đúng thì ra đơn tương ứng.
- [ ] Số phiếu trả, đầy đủ hoặc chỉ phần đầu `NNN/MM.YYYY`, thì ra đơn, kể cả phiếu đã hủy (VOID, có nhãn).
- [ ] Nhiều kết quả thì hiện danh sách có cột "Khớp theo", sàn, shop, lô (link), trạng thái, ngày đặt.
- [ ] Không khớp chính xác và từ khóa có từ 4 ký tự thì thử khớp một phần (≤ 50 dòng). Không có thì báo "Không tìm thấy" và giữ lại từ khóa.
- [ ] Ô tra cứu hiện trên mọi trang khi đã đăng nhập (desktop kể cả khi thu gọn sidebar, và mobile); phím `/` đưa con trỏ vào ô.
- [ ] `uv run pytest tests/web/test_order_search.py` và toàn bộ `uv run pytest` đều xanh; `uv run ruff check` sạch.

<!-- slug: quick-order-lookup -->

## Validation Log

### Session 1 — 2026-11-26
**Trigger:** `/ak-plan validate`
**Questions asked:** 3

#### Verification Results
- **Tier:** Standard
- **Claims checked:** 26
- **Verified:** 25 | **Failed:** 1 | **Unverified:** 0

#### Failures
1. [Flow Tracer] Phase 3 nói ô tra cứu "ẩn theo sidebar" khi thu gọn, nhưng `app.css:102-103` ẩn sidebar ở ≥ 1024px và `.topbar` chỉ hiện dưới 1024px (`app.css:124,132`), nên khi thu gọn không còn ô nào và phím `/` vô tác dụng, trái tiêu chí "mọi trang trên desktop".

Ghi chú: `search_words(request)` nhận `Request`, không phải chuỗi; route dùng được vì có `request`.

#### Questions & Answers

1. **[Risks]** Desktop thu gọn sidebar thì ô tra cứu và phím `/` không còn chỗ dùng. Xử lý thế nào?
   - Options: Hiện ô nhỏ cạnh nút mở sidebar (Recommended) | Chấp nhận ẩn | Phím / tự mở sidebar
   - **Answer:** Hiện ô nhỏ cạnh nút mở sidebar
   - **Rationale:** Giữ đúng tiêu chí "mọi trang" ở mọi trạng thái.
2. **[Scope]** Khớp một phần có quét thêm số hóa đơn VAT và số phiếu trả không?
   - Options: Chỉ 3 cột như plan (Recommended) | Thêm số hóa đơn VAT | Thêm cả hóa đơn và phiếu trả
   - **Answer:** Chỉ 3 cột như plan
   - **Rationale:** Hóa đơn và phiếu trả đã có khớp chính xác; tránh thêm join và index trigram.
3. **[Tradeoffs]** Khớp chính xác đúng 1 đơn thì chuyển thẳng 303?
   - Options: Giữ chuyển thẳng (Recommended) | Luôn hiện danh sách
   - **Answer:** Giữ chuyển thẳng
   - **Rationale:** Đúng mục tiêu "tới thẳng trang đơn".

#### Confirmed Decisions
- Khớp một phần: chỉ `platform_order_id`, `so_number`, `do_number`.
- Một khớp chính xác: 303 sang `/orders/{id}`.
- Ô tra cứu: sidebar (desktop), topbar (mobile), và ô cố định cạnh `.nav-expand` khi thu gọn.

#### Action Items
- [x] Phase 3: thêm ô tra cứu cho trạng thái thu gọn sidebar.

#### Impact on Phases
- Phase 3: đã cập nhật CSS/HTML cho trạng thái thu gọn và bước thử tay.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01-lookup-indexes.md, phase-02-search-route.md, phase-03-search-box-and-docs.md
- Decision deltas checked: 3
- Reconciled stale references: 1 (tiêu chí "desktop và mobile" trong plan.md)
- Unresolved contradictions: 0
