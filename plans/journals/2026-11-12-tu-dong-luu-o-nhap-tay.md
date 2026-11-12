---
title: "Tự lưu cho các ô nhập tay trên web"
date: 2026-11-12
summary: Rà soát các ô nhập tay; bảng khách hàng có cùng lỗi mất dữ liệu như bảng ánh xạ; thêm một script tự lưu dùng chung cho dòng khách, dòng ánh xạ thiếu và ngày goods issue
---

# Tự lưu cho các ô nhập tay

## Rà soát
- Ô nhập dạng bảng: dòng ánh xạ còn thiếu (trang Ánh xạ SAP) và tên/địa chỉ khách (trang Khách hàng). Trang Khách hàng có cùng lỗi với bảng ánh xạ trước đây: mỗi dòng một `<form>` đặt trong `<tr>`. Bấm Lưu một dòng thì mất hết những gì đã gõ ở các dòng khác.
- Ô đơn lẻ: ngày goods issue trên màn hình lô.
- Form hành động, cố ý không tự lưu: thêm khách theo mã đơn, thêm/sửa một dòng ánh xạ, lý do hủy đơn, lý do dừng robot, nối SO, đăng nhập, tải file. Tự lưu khi mới gõ dở mã đơn hay mã ánh xạ sẽ tạo bản ghi rác hoặc kích hoạt hành động chưa muốn.

## Cách làm
- `base.html` có một script: phần tử mang `data-autosave="<url>"` (một dòng bảng hoặc một form) gửi mọi ô có tên trong nó tới url đó khi người dùng rời ô vừa sửa, kèm header `X-Autosave: 1` và `keepalive` để chuyển trang vẫn không mất lần gửi. Có thêm `data-autosave-require` (đủ các ô mới lưu) và `data-autosave-reload`.
- Các endpoint sẵn có (`/customers/save`, `/sku-mappings`, `/batches/{id}/gi-date`) trả JSON `{ok, message}` khi có header đó; không có header thì giữ nguyên flash và redirect. Hết phiên đăng nhập trả 401, tài khoản xem trả 403, đều ở dạng JSON.
- Chỉ admin mới được gắn tự lưu. Dòng lưu lỗi hiện chữ đỏ, và trình duyệt hỏi lại trước khi rời trang.

## Kiểm chứng
- Hai test web mới kiểm tra JSON trả về, lưu từng dòng, chặn tài khoản xem và phiên hết hạn. Toàn bộ 121 test đều đạt.
- Đã chạy script trong jsdom, giả lập `fetch`, đi qua 12 tình huống: lưu khi rời ô, không gửi lại dòng không đổi, chờ đủ hai ô ánh xạ, lỗi đỏ kèm cảnh báo rời trang, thử lại thành công, ngày goods issue lưu rồi tải lại trang. Chưa kiểm tra trên trình duyệt thật.
