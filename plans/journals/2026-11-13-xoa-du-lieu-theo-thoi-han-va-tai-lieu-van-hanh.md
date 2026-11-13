---
title: "Xóa dữ liệu khách theo thời hạn và tài liệu vận hành"
date: 2026-11-13
summary: Bắt đầu phase 9. Lệnh retention 90 ngày, giữ đơn, chỉ xóa tên, địa chỉ và file; tác vụ hằng đêm mặc định chỉ liệt kê. Thêm sổ tay sự cố, tài liệu kiến trúc và bảo mật.
---

# Xóa dữ liệu theo thời hạn và tài liệu vận hành

## Quyết định của chủ dự án
- Thời hạn lưu là **90 ngày** (`SHOPONLINE_RETENTION_DAYS`).
- Khi hết hạn: **giữ đơn** (mã đơn, dòng hàng, số SO, số DO) và chỉ xóa `customer_info` cùng các file. Đơn không chứa dữ liệu cá nhân, và cần giữ để nhập lại file cũ không tạo đơn trùng.

## Cách làm
- Không xóa tên, địa chỉ của đơn chưa xong. "Đã có file gửi kế toán" được hiểu là đơn đã ở `DELIVERED`, vì file kế toán dựng từ `zrsd004` và việc nhập `zrsd004` chuyển đơn sang trạng thái này. Đơn `CANCELLED` cũng được xóa. Dòng Lazada không có `sales_order` nên xóa theo tuổi.
- Xóa file theo thời điểm sửa trong `uploads`, `exports`, `robot-work`. `store_file` đặt tên file theo SHA-256 và trước đây không ghi lại khi file đã có, nên tải lại đúng file cũ sẽ bị xóa ngay. Nay nó `touch()` file để tính lại thời hạn.
- Xóa file sau khi transaction xóa dòng đã commit. Chỉ xóa thư mục `robot-work/job-*` từng chứa file quá hạn, để không xóa mất thư mục rỗng robot vừa tạo cho việc đang chạy.
- Tải file kế toán từ một `zrsd004` đã bị xóa thì web trả 404 kèm lý do, thay vì lỗi 500.
- Tác vụ `shoponline-retention` mặc định chỉ liệt kê vào `logs/retention.log`. Đăng ký lại với `-RetentionApply` sau một tuần có người xem log.

## Lưu ý
- Bản sao lưu giữ 30 ngày, nên dữ liệu đã xóa còn trong bản sao lưu thêm tối đa 30 ngày. Đã ghi trong `docs/security-and-data-retention.md`.
- Khi sửa file bằng Python heredoc qua Bash tool, `\\` bị gộp thành `\`, nên `\r` trong `logs\retention.log` thành ký tự CR. Với văn bản có dấu gạch ngược, dùng Edit.

## Kiểm chứng
- `tests/maintenance/test_retention.py` có 3 test. Test luồng web kiểm tra 404 khi file `zrsd004` đã bị xóa. Toàn bộ 148 test đạt; ruff sạch. `shoponline retention` chạy trên database dev ở chế độ liệt kê: 0 đơn, 0 file.

## Còn lại của phase 9
- Chuyển sang máy riêng và diễn tập dựng lại máy.
- Kế hoạch khi máy hỏng (chủ dự án điền).
- Rà soát quyền trên máy thật.
- Diễn tập ba sự cố.
- Đào tạo.
