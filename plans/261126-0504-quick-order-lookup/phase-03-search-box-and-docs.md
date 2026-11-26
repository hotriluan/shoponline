---
phase: 3
title: "Ô tra cứu trên mọi trang và tài liệu"
status: pending
priority: P1
effort: "1.5h"
dependencies: [2]
---

# Phase 3: Ô tra cứu trên mọi trang và tài liệu

## Goal

Khi đã đăng nhập, người dùng thấy ô tra cứu ở mọi trang (sidebar trên desktop, topbar trên mobile) và nhấn `/` là con trỏ vào ô. Tài liệu vận hành có hướng dẫn dùng ô này.

## Files to Create / Modify

- Modify: `src/shoponline/web/templates/base.html`
- Modify: `src/shoponline/web/static/app.js`
- Modify: `src/shoponline/web/static/app.css`
- Modify: `docs/daily-operations.md`
- Modify: `tests/web/test_order_search.py` (thêm test hiển thị ô tìm)

## Tasks & Steps

- [ ] `base.html`: dưới `.brand-row` trong sidebar, thêm `<form class="quick-search" role="search" method="get" action="/search">` gồm `<input type="search" name="q" data-quick-search placeholder="Mã đơn, hóa đơn, SO, DO, phiếu trả" aria-label="Tra cứu đơn hàng" autocomplete="off">`. Ô điền sẵn `request.query_params.q` khi đang ở `/search`.
- [ ] Mobile: `.topbar` đang ẩn ở desktop và sidebar là drawer, nên thêm form tương tự trong `.topbar` cạnh chữ "Shop online". Tách form thành macro trong `_macros.html` để không lặp code.
- [ ] `app.js`: thêm khối IIFE. Khi nhấn `/` mà con trỏ không ở trong `input`, `textarea`, `select` hay `[contenteditable]` và không có phím bổ trợ thì `preventDefault()` và focus ô `[data-quick-search]` đang hiển thị (ô đầu tiên có `offsetParent !== null`).
- [ ] `app.css`: style `.quick-search` theo biến màu sidebar có sẵn (`--sidebar-*`), rộng 100%. Ô trong topbar mobile dùng được khi sidebar là drawer. <!-- Updated: Validation Session 1 - ô tra cứu phải còn dùng được khi desktop thu gọn sidebar --> Khi desktop thu gọn sidebar (`html.nav-collapsed`, ≥ 1024px) sidebar và topbar đều `display: none`, nên thêm một ô tra cứu cố định cạnh nút mở sidebar `.nav-expand` (dùng macro chung), chỉ hiện trong trạng thái thu gọn và chừa chỗ cho `main` (đang `padding-top: 56px`).
- [ ] Test: GET một trang bất kỳ (ví dụ `/batches`) khi đã đăng nhập thì HTML có `action="/search"`; trang `/login` thì không có.
- [ ] `docs/daily-operations.md`: thêm một mục ngắn "Tra cứu nhanh đơn hàng" gồm: dán được những loại mã nào, số 0 ở đầu hóa đơn không bắt buộc, phím `/`, cách đọc trang nhiều kết quả. Cập nhật câu ở dòng 105 ("Các danh sách lịch sử … được tìm … trên máy chủ") để nhắc rằng tìm theo mã đơn thì dùng ô tra cứu.

## Verification

- `uv run pytest tests/web -q`, sau đó toàn bộ `uv run pytest -q`.
- Chạy web dev (`uv run shoponline web`; kiểm tra cổng đã có process cũ chưa trước khi chạy, xong thì tắt) và thử tay: desktop, sidebar thu gọn (ô cạnh nút mở vẫn dùng được, phím `/` vào đúng ô đang hiện), cửa sổ hẹp dưới 1024px, phím `/` trong và ngoài ô nhập.

## Risk

Ô thứ ba (cạnh `.nav-expand`) cùng sidebar và topbar có thể cùng tồn tại trong DOM; phím `/` chỉ focus ô đang hiển thị (`offsetParent !== null`). Phím `/` có thể chặn việc gõ `/` ở chỗ khác. Đã loại trừ input, textarea, select và contenteditable, và bỏ qua khi có phím bổ trợ.
