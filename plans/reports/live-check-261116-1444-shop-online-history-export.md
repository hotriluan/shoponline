# Chạy thử production: xuất dòng file Shop Online (2026-11-16)

Plan: [plan.md](../261116-1354-shop-online-history-export/plan.md), phase 5.

## Đã kiểm (máy AlkanaDuongPC, chỉ đọc)

- Deploy run `43825940053` xanh cho commit `abb07fa`. Script deploy sao lưu trước: `shoponline-shoponline-20261116-144543.7z`, đã chép tới `C:\shoponline-backup`.
- `alembic current` ra `0007_sales_history (head)`.
- Web chạy (`http://192.168.18.123:8750`); `/sales-history` và `/report-names` chuyển về trang đăng nhập (303), đường dẫn lạ ra 404.
- Tách tỉnh/thành: 62 địa chỉ, 62 tách được, 0 không tách được; 21 tỉnh/thành khác nhau. 24 đơn "Đã có DO".
- Retention chế độ liệt kê: 0 đơn sẽ xóa, 0 đơn giữ lại, 0 file (dữ liệu sớm nhất từ 11/2026, chưa có gì quá 90 ngày; điều kiện giữ tên mới chỉ thấy được trên production từ khoảng 02/2027, đã có test).

## Còn lại (admin làm trên web)

1. **Tên báo cáo**: duyệt gợi ý của khoảng 75 mã, lưu.
2. Bổ sung tên khách còn thiếu cho đơn "Đã có DO".
3. **File Shop Online**: tải file, kiểm số đơn bằng số đơn "Đã có DO" lúc kiểm và header trùng dòng 1 của sheet1; dán thử vào một bản sao file lịch sử, kiểm hai cột công thức; bấm **Xác nhận đã dán**; mở lại trang thấy không còn đơn chờ.
