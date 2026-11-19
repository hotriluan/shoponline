# Validate kế hoạch cột Tiền Vô

Ngày: 2026-11-19 · Kế hoạch: plans/261119-0719-tien-vo-column

Kiểm lại nhanh 14 khẳng định của kế hoạch với code: không có khẳng định sai. Các file quyết toán kind `settlement` không thuộc quy tắc giữ file nào, nên `discard_unused` xóa được ngay sau khi nhập. `.gitignore` vẫn chưa phủ `docs/tienvo/`.

Điều học được:
- Mã đơn trên file mẫu khớp: Shopee 7/8 mã trong `Order.toship`, TikTok 7/7 mã 18 số trong ba file đơn TikTok.
- 21 đơn TikTok tiền vô 0 là đơn hoàn tiền toàn bộ, không phải đơn chưa quyết toán. Đơn -2565 là đơn hoàn tiền toàn bộ cộng phí xử lý.
- Trong `Shop Online 2022-2026_10.xlsx` không có chuỗi 18 số nào, nên mã TikTok ở đó có thể đã bị Excel lưu thành số. Việc này ngoài phạm vi kế hoạch.

Chủ dự án chốt: đơn hoàn tiền xuất với 0 hoặc số âm; giữ khóa dòng Shopee có số tiền và ghi rủi ro ở docs.
