# Red team kế hoạch cột Tiền Vô

Ngày: 2026-11-19 · Kế hoạch: plans/261119-0719-tien-vo-column

Ba reviewer (bảo mật, giả định, lỗi vận hành) đọc kế hoạch và đối chiếu code cùng file mẫu. 15 phát hiện: 14 nhận, 1 bác (formula injection có sẵn trong workbook builder, nên sửa riêng).

Điều học được:
- File mẫu TikTok mở bằng openpyxl read_only chỉ thấy 21/66 cột; cột "ID đơn hàng liên quan" chỉ hiện khi mở thường. Kế hoạch gốc tưởng không có cách nối dòng điều chỉnh với đơn vì thế.
- "ID đơn hàng/điều chỉnh" là ID giao dịch; mã đơn đúng là "ID đơn hàng liên quan".
- Upsert nhiều dòng của Postgres lỗi khi một khóa xuất hiện hai lần; khóa Shopee thêm thứ tự lặp "#n".
- .gitignore chỉ phủ docs/*.xlsx, không phủ docs/tienvo/.

Chủ dự án chốt: đơn chỉ có "Tiền ra" xuất số âm; giữ bỏ qua dòng điều chỉnh TikTok nhưng liệt kê ID; không thêm ngày bắt đầu.
