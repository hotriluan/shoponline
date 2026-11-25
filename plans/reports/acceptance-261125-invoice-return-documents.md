# Nghiệm thu: trả hàng sau hóa đơn (2026-11-25)

Dữ liệu dev: hai đơn mẫu, zrsd003 tháng 11/2026 (`docs/bbdchd/zrsd003.XLSX`), số bắt đầu 080. Dữ liệu nghiệm thu đã xóa khỏi dev sau khi đối chiếu.

| Kiểm tra | Kết quả |
|---|---|
| Đơn Shopee, master rỗng | Bị chặn "thiếu tên trên hóa đơn"; tải `hd_shopee.pdf` ghi master `100001787`; phát hành `080/11.2026` |
| Đơn Lazada, cùng vật tư | Phát hành `081/11.2026` không cần PDF |
| Word so với mẫu (chữ) | Chỉ khác số biên bản, tên hàng `… 2004 VN` / `LON 0.8 LT` (theo PDF hóa đơn), cách viết địa chỉ (theo dữ liệu khách) |
| Định dạng Word và Excel so với baseline | 0 khác biệt (cả hai đơn) |
| PDF in bằng Word/Excel đặt cạnh mẫu | Cùng số trang, cùng bố cục; chỉ khác chữ trường động (đen thay đỏ) và logo Excel (đã bỏ theo yêu cầu) |
| Excel `D14` | `V-09 REDDISH CLAY 2004 VN-0.8L` (tên SAP) |
| Tiền | 111.111 / 8.889 / 120.000, dòng điều chỉnh âm |

Giữ nguyên theo mẫu: tên người mua có nền highlight vàng trong mẫu Word, file sinh ra cũng có.
Chưa kiểm: hóa đơn thật nhiều dòng hoặc số lượng > 1 chia không hết (cần PDF thật để so cách làm tròn của Bkav); luồng web trên máy dev với tài khoản thật (đã có test route).
