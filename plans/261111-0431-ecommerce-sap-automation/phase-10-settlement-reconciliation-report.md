---
title: "Phase 10: Bảng kê đối soát"
status: todo
priority: P2
effort: 6d
dependencies: [4, 9]
---

# Phase 10: Bảng kê đối soát

## Overview

Sinh tự động "Bảng kê chi phí bán hàng sàn giao dịch điện tử" hằng tháng cho từng sàn, đúng mẫu kế toán đang làm tay, kèm danh sách chênh lệch cần xem. Phase này chỉ báo cáo; chưa ghi bút toán nào.

Ứng với V2 mục 7 (bước đầu).

## Key Insights

Mẫu đích đã có trong `docs/` (bảng kê Lazada và TikTok tháng 10/2026):

- Mỗi dòng là một hóa đơn bán hàng: số hóa đơn, ngày, tổng tiền, ngày nhận tiền, số tiền nhận trong kỳ, chênh lệch, số và ngày hóa đơn phí của sàn, ghi chú.
- Hai khối: "Hóa đơn kỳ trước chuyển sang" và "Hóa đơn trong kỳ"; cuối bảng có "Số tiền nhận và chênh lệch trong kỳ" và "Hóa đơn chuyển sang kỳ sau" (bằng tổng hai khối trừ số đã nhận và chênh lệch).
- Hóa đơn chưa nhận tiền trong kỳ để trống cột nhận và chuyển sang kỳ sau.
- Tiền về theo tuần. Bảng kê Lazada có số hóa đơn phí của sàn theo từng đợt; bảng kê TikTok để trống cột này.
- Chênh lệch là phí sàn giữ lại: khoảng 29–30% với Lazada, 18% với TikTok trên đơn 120.000đ.

Phase 2 đã kết luận phần nào của dữ liệu thanh toán có trên API và phần nào phải nhập từ báo cáo của sàn.

## Requirements

- Lấy dữ liệu thanh toán theo đơn từ API sàn; phần không có trên API thì nhập từ file báo cáo tải ở trang quản lý sàn.
- Mỗi dòng thanh toán gắn với một đơn, qua đó gắn với hóa đơn.
- Sinh file Excel đúng mẫu, gồm công thức tổng như bảng kê tay.
- Số chuyển kỳ của tháng này là số đầu kỳ của tháng sau.
- Tách các khoản phí theo loại (hoa hồng, phí giao dịch, phí dịch vụ, vận chuyển, voucher, điều chỉnh) trong một sheet chi tiết, để kế toán tính thuế GTGT đầu vào theo hóa đơn phí của sàn.
- Đơn COD được đánh dấu riêng.
- Liệt kê bất thường: đơn có tiền về nhưng không có hóa đơn, hóa đơn quá hạn chưa có tiền, tỷ lệ phí lệch xa mức thường, khoản không gắn được với đơn (phí quảng cáo, điều chỉnh sau kỳ).
- Đối chiếu tổng tiền nhận với số tiền về ngân hàng do kế toán nhập.

## Architecture

```
connectors/*.py                 thêm thao tác lấy dữ liệu thanh toán (theo Capabilities)
reconcile/settlement_import.py  API hoặc file báo cáo sàn → settlement_line
reconcile/settlement_match.py   settlement_line ↔ đơn ↔ hóa đơn
exports/settlement_report.py    sinh bảng kê theo mẫu + sheet chi tiết phí + sheet bất thường
web/routes/settlement.py        chọn sàn và kỳ, nhập file, nhập số ngân hàng, tải bảng kê
```

Bảng `settlement_line`: shop, đơn, đợt thanh toán, ngày nhận, loại khoản, số tiền, số và ngày hóa đơn phí của sàn, nguồn (API hoặc file), khóa chống nhập trùng.

## Related Code Files

- Create: `migrations/versions/<rev>_settlement_line.py`
- Modify: `src/shoponline/connectors/base.py`, `shopee.py`, `lazada.py`, `tiktok.py`
- Create: `src/shoponline/reconcile/settlement_import.py`, `settlement_match.py`
- Create: `src/shoponline/exports/settlement_report.py`, `src/shoponline/exports/templates/settlement-report.xlsx`
- Create: `src/shoponline/web/routes/settlement.py`
- Create: `tests/reconcile/test_settlement_match.py`, `tests/exports/test_settlement_report.py`
- Create: `tests/fixtures/settlement/` (bảng kê tay tháng 10/2026 làm chuẩn so sánh)

## Implementation Steps

1. Thêm bảng `settlement_line` với khóa chống nhập trùng.
2. Viết bộ nhập từ file báo cáo của từng sàn trước, vì cách này luôn làm được; test bằng file báo cáo thật đã ẩn danh.
3. Thêm thao tác lấy dữ liệu thanh toán qua API cho sàn nào phase 2 kết luận là đủ; test nhập hai lần không tạo dòng trùng.
4. Viết `settlement_match.py` gắn dòng thanh toán với đơn và hóa đơn; khoản không gắn được vào danh sách bất thường.
5. Nhập dữ liệu lịch sử: hóa đơn và đơn từ tháng 9/2026 để có số đầu kỳ cho tháng 10. Với giai đoạn trước khi hệ thống ghi số hóa đơn, cho phép nhập bảng ánh xạ đơn ↔ số hóa đơn từ file của kế toán.
6. Viết `settlement_report.py` sinh file theo mẫu: hai khối, công thức tổng, dòng chuyển kỳ, ô ký duyệt.
7. Test chuẩn: sinh bảng kê Lazada và TikTok tháng 10/2026 rồi so từng dòng với hai file trong `docs/` (số hóa đơn, ngày, tổng tiền, ngày nhận, số nhận, chênh lệch, số hóa đơn phí của sàn).
8. Thêm sheet chi tiết phí theo loại và sheet bất thường.
9. Viết màn hình: chọn sàn và kỳ, tải file báo cáo, nhập số tiền về ngân hàng theo đợt, xem chênh lệch, tải bảng kê.
10. Làm bảng kê Shopee theo mẫu kế toán cung cấp ở phase 2.
11. Chạy song song hai kỳ kế tiếp: kế toán vẫn làm tay, so với bản tự động.

## Todo

- [ ] Bảng `settlement_line`
- [ ] Nhập từ file báo cáo của ba sàn
- [ ] Nhập từ API cho sàn đủ dữ liệu
- [ ] Gắn thanh toán với đơn và hóa đơn
- [ ] Nhập dữ liệu lịch sử cho số đầu kỳ
- [ ] Sinh bảng kê đúng mẫu
- [ ] Test khớp bảng kê tay tháng 10/2026
- [ ] Sheet chi tiết phí và bất thường
- [ ] Màn hình đối soát
- [ ] Bảng kê Shopee
- [ ] Chạy song song hai kỳ

## Success Criteria (cổng G5)

- Bảng kê tự động khớp từng dòng với bảng kê tay tháng 10/2026 của Lazada và TikTok.
- Khớp tiếp hai kỳ kế tiếp cho cả ba sàn, hoặc mỗi khác biệt được kế toán xác nhận là lỗi của bản tay.
- Tổng tiền nhận trong bảng kê bằng tổng tiền về ngân hàng theo từng đợt; khoản lệch có tên trong sheet bất thường.

## Verification

- `uv run pytest tests/reconcile tests/exports` thoát mã 0, gồm test so với bảng kê tay.
- Kế toán ký xác nhận bản tự động của từng kỳ chạy song song.

## Risk Assessment

- **API không đủ chi tiết.** Đường nhập từ file báo cáo luôn có sẵn và được làm trước.
- **Sàn đổi mẫu báo cáo.** Bộ nhập kiểm tra tiêu đề cột và từ chối file lạ thay vì nhập sai.
- **Khoản phí không theo đơn.** Đưa vào sheet bất thường, không phân bổ tự động.
- **Thiếu số hóa đơn của giai đoạn trước.** Dùng bảng ánh xạ nhập từ file của kế toán.

## Rollback

Kế toán tiếp tục làm bảng kê tay. Phase này không ghi gì vào SAP.

## Security Considerations

- Chỉ vai trò kế toán xem và tải dữ liệu đối soát.
- File báo cáo sàn tải lên được lưu trong thư mục giới hạn quyền.

## Next Steps

Ba kỳ khớp liên tiếp là điều kiện cho phần ghi nhận thanh toán tự động ở phase 11.
