---
title: "Phase 9: Billing và hóa đơn BKAV"
status: todo
priority: P1
effort: 5d
dependencies: [8]
---

# Phase 9: Billing và hóa đơn BKAV

## Overview

Robot lập billing document trong SAP cho đơn đã bàn giao, xuất đúng file Excel mà kế toán đang upload lên BKAV, kế toán duyệt rồi phát hành. Số hóa đơn được ghi lại để phục vụ đối soát. Gọi API BKAV chỉ làm khi BKAV xác nhận gói hiện tại có API.

Ứng với V2 mục 6.

## Key Insights

- Hóa đơn đã phát hành rất khó sửa, nên giai đoạn đầu luôn có kế toán duyệt và hệ thống không tự phát hành.
- Số liệu hóa đơn lấy từ billing document của SAP, không lấy từ database trung gian.
- Bảng kê đối soát của kế toán lấy số hóa đơn làm khóa (cột "SỐ HĐBH"), nên việc ghi lại số hóa đơn cho từng đơn là đầu vào bắt buộc của phase 10.
- Địa chỉ người mua trên API sàn bị che một phần; cách xử lý phụ thuộc quyết định mục 8 của sổ quyết định.

## Requirements

- Lập billing bằng `VF01` từ DO, chỉ khi đơn ở `HANDED_OVER`; kiểm tra DO đã có billing chưa trước khi lập.
- Xuất file Excel đúng mẫu hiện tại, số liệu đọc từ billing document.
- Mỗi billing document chỉ nằm trong một lần xuất được duyệt; xuất lại phải có lý do và người duyệt.
- Kế toán duyệt trên web trước khi file được coi là sẵn sàng upload.
- Ghi số hóa đơn BKAV, ngày và trạng thái về `invoice_export`.
- Địa chỉ người mua theo quyết định đã chốt; dữ liệu cá nhân chỉ dùng cho hóa đơn và có thời hạn lưu.

## Architecture

```
saprobot/transactions/create_billing.py   VF01
saprobot/transactions/read_billing.py     đọc billing document (hoặc T-code xuất Excel hiện tại)
sapjobs/handlers/billing.py               kiểm tra trùng → lập → đọc số → đọc số liệu
exports/invoice_excel.py                  billing → file Excel mẫu BKAV
web/routes/invoices.py                    danh sách chờ duyệt, duyệt, tải file, nhập số hóa đơn
```

Bảng `invoice_export`: billing document, đơn, lô xuất, trạng thái (`DRAFT`, `APPROVED`, `ISSUED`, `REJECTED`), người duyệt, số và ngày hóa đơn BKAV. Ràng buộc: một billing document chỉ có một dòng ở trạng thái `APPROVED` hoặc `ISSUED`.

**Phương án A (bắt đầu).** Robot lập billing, hệ thống sinh file Excel, kế toán duyệt, tải file và upload lên BKAV như hiện nay, rồi nhập hoặc tải ngược số hóa đơn vào hệ thống.

**Phương án B (khi BKAV xác nhận có API).** Thêm một lớp gửi hóa đơn sau bước duyệt. Bước duyệt và ràng buộc phát hành một lần giữ nguyên. Phần này được viết thành các bước thực thi cụ thể sau khi có tài liệu API của BKAV; phase 2 đã hỏi BKAV.

## Related Code Files

- Create: `migrations/versions/<rev>_invoice_export.py`
- Create: `src/shoponline/saprobot/transactions/create_billing.py`, `read_billing.py`
- Create: `src/shoponline/sapjobs/handlers/billing.py`
- Create: `src/shoponline/exports/invoice_excel.py`
- Create: `src/shoponline/web/routes/invoices.py`, `web/templates/invoices*.html`
- Create: `src/shoponline/invoicing/buyer_address.py`
- Modify: `config/sap_screens.yaml`, `config/sap_popups.yaml`
- Create: `tests/sapjobs/test_billing_handler.py`, `tests/exports/test_invoice_excel.py`, `tests/web/test_invoice_approval.py`

## Implementation Steps

1. Thêm bảng `invoice_export` với ràng buộc phát hành một lần; test ràng buộc.
2. Viết `billing.py` với lớp thực thi giả; test: đã có billing, đơn chưa `HANDED_OVER`, mất phiên sau khi lưu.
3. Viết `create_billing.py` từ bản ghi recorder `VF01` và `read_billing.py` để đọc dòng hàng, số lượng, giá trước thuế, thuế, tổng.
4. Viết `invoice_excel.py` sinh đúng mẫu Excel BKAV lấy ở phase 2. Test bằng cách so từng ô với một file kế toán đã làm cho cùng billing document.
5. Viết `buyer_address.py` theo quyết định mục 8: dùng địa chỉ từ phường/xã, hoặc lấy từ yêu cầu hóa đơn của người mua trên sàn, hoặc từ dữ liệu vận đơn có cấu trúc. Đọc địa chỉ từ PDF vận đơn chỉ làm nếu ba cách trên đều không được chấp nhận.
6. Viết màn hình hóa đơn: danh sách `DRAFT` theo lô, xem số liệu cạnh dữ liệu đơn, duyệt hoặc từ chối, tải file, ghi số hóa đơn BKAV (nhập tay hoặc tải file kết quả từ BKAV).
7. Chạy trên QA: robot lập billing cho các DO đã PGI trên QA ở phase 8, chạy lại để chứng minh không lập trùng, và sinh file Excel từ các billing đó để kế toán xem bố cục.
8. Chạy song song trên hệ thống thật: robot sinh file, kế toán vẫn tự làm file của mình; so hai file mỗi ngày cho tới cổng G4.
9. Sau cổng G4, kế toán dùng file của hệ thống.
10. Nếu BKAV có API và công ty quyết định dùng: viết lớp gửi theo tài liệu API, chạy ở môi trường thử của BKAV trước, vẫn giữ bước duyệt.

## Todo

- [ ] Bảng `invoice_export` và ràng buộc
- [ ] Handler billing và test
- [ ] `create_billing.py`, `read_billing.py`
- [ ] Xuất Excel đúng mẫu BKAV
- [ ] Xử lý địa chỉ người mua theo quyết định
- [ ] Màn hình duyệt và ghi số hóa đơn
- [ ] Billing chạy đúng trên QA, chạy lại không trùng
- [ ] Chạy song song tới cổng G4
- [ ] Lớp gửi API BKAV (khi được xác nhận)

## Success Criteria (cổng G4)

- File Excel hệ thống sinh khớp từng ô với file kế toán tự làm cho 30 billing document liên tiếp.
- Không billing document nào xuất hiện trong hai lô đã duyệt.
- Mỗi đơn `HANDED_OVER` quá thời hạn đã chốt mà chưa có hóa đơn đều hiện trong danh sách cảnh báo.
- Mọi hóa đơn đã phát hành có số hóa đơn BKAV ghi trong hệ thống.

## Verification

- `uv run pytest tests/sapjobs tests/exports tests/web` thoát mã 0.
- Kế toán ký biên bản so sánh 30 billing document.

## Risk Assessment

- **Phát hành trùng hóa đơn.** Ràng buộc trong database cộng bước duyệt; file đã tải được đánh dấu để không tải lại nhầm.
- **Hóa đơn lệch sổ.** Số liệu chỉ đọc từ billing document; test so từng ô.
- **Chưa chốt được địa chỉ.** Phase này không ra khỏi chạy song song khi mục 8 còn mở.
- **Mẫu Excel BKAV thay đổi.** Test so với file mẫu sẽ báo; mẫu là một file trong repo, đổi mẫu là đổi một chỗ.

## Rollback

Kế toán quay lại tự làm file Excel. Billing robot đã lập vẫn hợp lệ trong SAP. Hóa đơn đã phát hành sai được xử lý theo quy trình điều chỉnh hóa đơn của kế toán, ngoài phạm vi tự động.

## Security Considerations

- Chỉ vai trò kế toán duyệt và tải file hóa đơn.
- Dữ liệu cá nhân người mua mã hóa khi lưu, chỉ giải mã khi sinh file; có thời hạn xóa sau khi hóa đơn phát hành.
- Nhật ký không ghi tên, địa chỉ, mã số thuế người mua.

## Next Steps

Phase 10 dùng số hóa đơn làm khóa của bảng kê.
