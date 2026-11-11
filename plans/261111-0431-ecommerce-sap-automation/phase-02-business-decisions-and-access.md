---
title: "Phase 2: Chốt nghiệp vụ và quyền truy cập"
status: todo
priority: P1
effort: 5d
dependencies: []
---

# Phase 2: Chốt nghiệp vụ và quyền truy cập

## Overview

Biến 13 mục [Xác nhận] của V2 thành quyết định có người ký tên, lấy đủ quyền truy cập (API ba sàn, user SAP cho robot, máy robot), ghi lại thao tác SAP thật bằng recorder, và kiểm tra dữ liệu đối soát có đủ trên API không. Phase này ít mã nhưng chặn mọi phase ghi chứng từ.

Ứng với V2 mục 3 (Giai đoạn 0), mục 7 (cách kiểm tra mức đủ dữ liệu) và mục 12.

## Key Insights

- `docs/vk11pdf.pdf` cho thấy `ZPR1 = PriceList IncludeTax`. Câu hỏi "giá ZPR1 có gồm VAT không" đổi thành "xác nhận ZPR1 gồm VAT và đây là điều kiện giá dùng cho kênh sàn".
- Danh sách điều kiện có `ZDI3`–`ZDI8` (Discount Promo 1/2, Regular, Extra, có biến thể `(S)`). Trang PDF bị cắt nên chưa thấy `ZDI1`/`ZDI2` mà V2 nhắc; cần hỏi kế toán điều kiện nào dùng cho voucher shop.
- Lazada giữ lại 29–30% mỗi đơn, TikTok 18%. Phần chênh lệch này gồm những khoản gì là câu hỏi đầu tiên của việc kiểm tra dữ liệu đối soát.
- Bảng kê Lazada có cột số hóa đơn phí của sàn theo đợt thanh toán tuần; bảng kê TikTok để trống cột này. Cần hỏi kế toán vì sao.
- Chưa có bảng kê Shopee trong `docs/`.

## Requirements

- Mỗi quyết định có: câu hỏi, câu trả lời, người quyết định, ngày, và ví dụ số cụ thể trên một đơn thật.
- Có thông tin đăng nhập API của cả ba sàn ở môi trường thật, lưu trong kho bí mật.
- Có user SAP riêng cho robot, biết chính sách đổi mật khẩu.
- Có máy Windows cho robot đã cấu hình theo V2 mục 2.2.
- Có bản ghi recorder cho từng T-code, lấy trên đúng máy robot và đúng ngôn ngữ đăng nhập.
- Có kết luận bằng văn bản về mức đủ dữ liệu đối soát cho từng sàn.

## Related Code Files

- Create: `docs/decisions/business-rules.md` (sổ quyết định nghiệp vụ)
- Create: `docs/decisions/settlement-data-check.md` (kết quả so 20 đơn mỗi sàn)
- Create: `docs/sap-recordings/` (script recorder `.vbs` cho từng T-code, đã gỡ dữ liệu khách)
- Create: `docs/robot-machine-setup.md` (danh sách cấu hình máy robot)
- Create: `tests/fixtures/orders/` (đơn mẫu đã ẩn danh từ ba sàn)

## Implementation Steps

1. **Sổ quyết định.** Tạo `business-rules.md` với một mục cho từng câu sau, kèm ví dụ số:
   1. Hệ thống SAP QA (đã xác nhận là có): tên hệ thống và client của QA và của hệ thống thật, user robot trên cả hai, dữ liệu chủ trên QA (vật tư, giá `ZPR1`, khách hàng sàn, tồn kho) có đủ mới để tạo SO, DO, PGI, billing cho đơn mẫu không, và ai nạp tồn kho thử khi cần.
   2. Trường nào trên SO lưu mã đơn sàn. Ứng viên đầu tiên là trường PO number của khách hàng, vì tìm lại được bằng `VA05`.
   3. Giá niêm yết trên sàn gồm VAT không; xác nhận `ZPR1` gồm VAT; thuế suất từng nhóm hàng.
   4. Voucher shop: điều kiện nào (`ZDI…`), dấu âm hay dương, theo dòng hay theo đơn.
   5. Voucher cấp theo đơn: quy tắc phân bổ xuống dòng và làm tròn.
   6. Trợ giá và voucher của sàn: xử lý thế nào trên SO và hóa đơn.
   7. Phí vận chuyển có vào SO không.
   8. Địa chỉ trên hóa đơn cần đầy đủ hay đến phường/xã.
   9. Đơn thiếu hàng: chờ, hủy hay tách.
   10. Đơn hủy sau khi có SO/DO: ai quyết định, đảo thế nào.
   11. Loại đơn, tổ chức bán hàng, kênh, ngành hàng, mã khách hàng SAP của từng sàn, nhà máy, kho, điểm giao hàng.
   12. Thời điểm PGI: khi kho quét đóng gói hay khi shipper nhận.
   13. Ngưỡng lệch cho phép khi kiểm tra chéo tổng giá trị SO.
2. **Chấp thuận nội bộ.** Xin đồng ý bằng văn bản của cấp trên và IT về việc robot tạo chứng từ SAP; hỏi về điều khoản giấy phép truy cập gián tiếp.
3. **API sàn.** Đăng ký app trên Shopee Open Platform, Lazada Open Platform, TikTok Shop Partner Center theo V2 mục 3.2. Ghi lại cho từng sàn: thời hạn token hiện hành, giới hạn tần suất, có webhook không, có bước sắp xếp giao hàng trước khi lấy vận đơn không, API vận đơn trả dữ liệu cấu trúc hay PDF. Với TikTok, xác nhận cổng khu vực cho shop Việt Nam trước khi tạo tài khoản.
4. **Đơn mẫu.** Gọi API lấy 20 đơn thật mỗi sàn (đơn thường, có voucher shop, có voucher sàn, combo, hủy, hoàn). Chủ dự án chạy script ẩn danh cục bộ (`scripts/anonymize-fixtures.py`, do Claude Code viết) rồi mới lưu vào `tests/fixtures/orders/`; dữ liệu gốc chưa ẩn danh không vào repo và không dán vào hội thoại.
5. **Kiểm tra dữ liệu đối soát** (V2 mục 7): tải bảng đối soát một kỳ từ trang quản lý từng sàn, so với dữ liệu API của cùng 20 đơn và với bảng kê tay tháng 10/2026. Ghi rõ phần nào có trên API, phần nào phải nhập từ báo cáo của sàn, và phần chênh 29–30% của Lazada, 18% của TikTok gồm những khoản nào.
6. **Bảng kê Shopee.** Xin kế toán bảng kê Shopee cùng kỳ và mẫu file Excel đang upload lên BKAV. Shopee có khoảng 20 đơn/ngày nên đây là chuẩn so sánh lớn nhất. Ngày cao điểm cao nhất đã biết là 100 đơn/ngày; hỏi thêm hạn giao cho shipper của từng sàn trong đợt sale, vì đó là giới hạn thời gian robot phải kịp.
7. **Máy robot.** Máy chạy thật là một máy riêng, chạy cả PostgreSQL, đồng bộ đơn, web và robot, bật liên tục. Chuẩn bị máy, cài Windows, SAP GUI, PostgreSQL, Python, ứng dụng Google Drive, và nối ổ mạng công ty. Trên máy này SAP Logon chỉ khai báo hệ thống thật; trên máy phát triển robot chỉ làm việc với QA. Cấu hình theo V2 mục 2.2 và ghi vào `robot-machine-setup.md`: độ phân giải cố định, tắt khóa màn hình và ngủ, tự đăng nhập Windows bằng tài khoản robot sau khi khởi động lại, bỏ hai ô thông báo script, ngôn ngữ đăng nhập SAP cố định, cách giữ phiên khi ngắt RDP, địa chỉ IP cố định trong mạng nội bộ, nguồn dự phòng, và nơi lưu bản sao lưu ngoài máy.
8. **Recorder.** Trên máy phát triển, với cùng độ phân giải, ngôn ngữ và phiên bản SAP GUI như máy chạy thật, đăng nhập hệ thống QA bằng user robot và ghi thao tác cho `VA01`, `VA03`, `VA05`, `VL01N`, `VL02N`, `VF01`, `MMBE` (hoặc báo cáo tồn kho đang dùng) và T-code xuất Excel hóa đơn hiện tại. Mỗi bản ghi kèm ảnh chụp các màn hình và popup gặp phải. So màn hình QA với hệ thống thật cho từng T-code và ghi lại khác biệt nếu có.
9. **BKAV.** Hỏi gói hiện tại có API không và chi phí.

## Todo

- [ ] `business-rules.md` đủ 13 mục, mỗi mục có người quyết định và ví dụ số
- [ ] Văn bản chấp thuận cho robot thao tác SAP
- [ ] Thông tin API Shopee trong kho bí mật
- [ ] Thông tin API Lazada trong kho bí mật
- [ ] Thông tin API TikTok Shop trong kho bí mật
- [ ] 20 đơn mẫu ẩn danh mỗi sàn
- [ ] `settlement-data-check.md` cho cả ba sàn
- [ ] Bảng kê Shopee và mẫu Excel BKAV
- [ ] Máy robot cấu hình xong, user SAP robot đăng nhập được
- [ ] Bản ghi recorder cho mọi T-code
- [ ] Câu trả lời của BKAV về API

## Success Criteria

- Không còn mục [Xác nhận] nào của V2 mục 12 ở trạng thái mở, hoặc mục còn mở có ghi rõ nó chặn phase nào.
- Lập trình viên tính tay được giá trị SO mong đợi của 20 đơn mẫu chỉ từ `business-rules.md`, và kế toán xác nhận các con số đó.
- Gọi được API lấy đơn thật của cả ba sàn.

## Verification

- Kế toán và sales admin ký vào `business-rules.md` (ghi tên và ngày trong file).
- Chạy lại một bản ghi recorder `VA03` trên máy robot bằng user robot, mở đúng một SO có thật.

## Risk Assessment

- **Người trả lời chậm.** Phase này chạy song song với phase 1, 3, 4. Chỉ các mục 2–7, 11, 13 chặn phase 7; mục 8 chặn phase 9; mục 9–10 chặn phase 7 và 8.
- **Dữ liệu chủ trên QA cũ hoặc thiếu.** Khi đó robot lỗi trên QA vì dữ liệu chứ không vì mã. Kiểm tra bằng cách sales admin tạo tay một SO cho đơn mẫu trên QA trước khi robot thử.
- **Sàn từ chối hoặc chậm duyệt app.** Đăng ký ngay trong tuần đầu vì thời gian duyệt nằm ngoài tầm kiểm soát.

## Rollback

Không thay đổi hệ thống nào. Quyết định sai được sửa bằng một mục mới trong sổ quyết định, giữ lại mục cũ để truy vết.

## Security Considerations

- Đơn mẫu phải ẩn danh tên, điện thoại, địa chỉ người mua trước khi vào repo.
- Bản ghi recorder không chứa mật khẩu; gỡ tên khách hàng thật nếu có.
- Thông tin API và mật khẩu user robot chỉ nằm trong kho bí mật.

## Next Steps

Kết quả phase này là đầu vào của phase 3 (quy tắc giá), phase 4 (thông tin API), phase 6 (bản ghi recorder) và phase 10 (mức đủ dữ liệu đối soát).
