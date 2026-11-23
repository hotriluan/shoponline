# Kiểm tra trực quan: đại tu giao diện

Ngày: 2026-11-23. Kết quả: đạt, sau khi sửa ba lỗi cuộn ngang tìm thấy ở 390px.

## Cách kiểm tra

- Web chạy trên cổng 8765 với một database `*_test` riêng, có dữ liệu mẫu (5 đơn đủ các trạng thái Đã có DO, Sẵn sàng, Thiếu ánh xạ, Cần kiểm tra và một đợt kế toán `OPEN`). Không dùng database dev thật vì tệp `.env` cần người dùng duyệt trước khi đọc. Tiến trình web đã dừng, cổng đã giải phóng.
- Trình duyệt: `agent-browser` (Chrome 158), tài khoản `admin` và `viewer` tạo riêng cho lần kiểm tra này trong database `*_test`.
- 16 trang × 2 cỡ màn hình (1366×768, 390×844) × 2 vai trò. Mỗi lượt đo: cuộn ngang cấp trang, số mục `aria-current="page"`, tiêu đề; ảnh chụp lưu ở `C:\Users\luanh\AppData\Local\Temp\visual-shots` (64 ảnh).
- Trang có nhiều template con (backup list, drive, đang phục hồi) được tính cùng trang cha; `/backup/restoring/*` cần một yêu cầu phục hồi thật nên chỉ kiểm qua test.

## Kết quả

| Tiêu chí | Kết quả |
|---|---|
| Không cuộn ngang cấp trang, 1366px | Đạt, 16/16 |
| Không cuộn ngang cấp trang, 390px | Đạt, 16/16 sau sửa lỗi (xem dưới) |
| Sidebar có đúng một `aria-current="page"` | Đạt, 16/16 sau sửa lỗi |
| Ngăn kéo menu dưới 1024px | Mở bằng ☰ (`aria-expanded=true`), đóng bằng Esc |
| `:focus-visible` | Viền liền 2px khi dùng Tab |
| Vùng bấm | Không có nút, liên kết hay ô nào dưới 32px ở 1366px, dưới 44px ở 390px |
| Tương phản WCAG AA | 26 cặp màu token đều từ 4.75:1 trở lên |
| `prefers-reduced-motion` | Có trong `app.css` |
| Không còn `style="` | Đạt, có test chặn quay lại |

Lỗi tìm thấy và đã sửa:

1. `/customers`, `/sku-mappings`, `/backup` tràn ngang 92px, 12px và 172px ở 390px do ô nhập có thuộc tính `size` và thẻ `min-width: 240px`. Sửa trong `app.css` (hàng form co được, ô nhập rộng 100% trên màn hẹp).
2. `/sku-mappings` có hai mục `aria-current="page"` vì nút chọn sàn cũng dùng thuộc tính này. Nút chọn sàn đổi sang `aria-pressed`.

## Chưa kiểm được

- Đợt kế toán đang đọc, robot đang chạy hoặc lỗi, trạng thái phục hồi, danh sách bản sao lưu có dữ liệu: database mẫu không có các trạng thái này. Test tự động của từng trang bao phủ chúng.
- Chưa duyệt từng ảnh chụp bằng mắt; mới xem trang Việc hôm nay (1366px) và trang lô (1366px, 390px), đều đúng bố cục.
- Bước chạy `design_system.py` của skill giao diện đã bỏ qua; token do tự chọn.

## Câu hỏi còn mở

Không có.
