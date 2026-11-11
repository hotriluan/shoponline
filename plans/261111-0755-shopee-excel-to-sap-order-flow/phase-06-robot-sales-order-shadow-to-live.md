---
title: "Phase 6: Robot tạo SO Shopee, shadow rồi ghi thật"
status: todo
priority: P1
effort: 5d
dependencies: [5]
---

# Phase 6: Robot tạo SO Shopee, shadow rồi ghi thật

## Overview

Robot tạo Sales Order cho đơn Shopee không có trợ giá. Đi qua ba bậc: tạo đúng trên QA; chế độ `shadow` trên hệ thống thật, nơi sales admin vẫn tạo SO và hệ thống so đề xuất với SO thật; rồi chế độ `live` sau cổng G2. Đơn có trợ giá vẫn do người làm cho tới phase 7.

## Key Insights

- Chế độ `shadow` không cần thao tác SAP mới: bước đối chiếu của phase 4 đã so mã vật tư, số lượng và giá trị SO với file sàn. Cổng G2 là kết quả đối chiếu đó trên đủ số đơn.
- Shopee có khoảng 20 đơn mỗi ngày, nên 10 ngày làm việc cho khoảng 200 đơn.
- SO thật có `PO No` là mã đơn sàn, khách hàng `1200001145`, giá 120.000đ gồm thuế do SAP tự định (`docs/zrsd001.XLSX`). Robot không nhập giá.
- Bộ sản phẩm: robot gõ một dòng mã bộ, SAP tự bung thành phần.
- Điểm nguy hiểm nhất là mất phiên ngay sau khi bấm lưu: robot không biết SO đã tạo hay chưa.

## Requirements

- Trước mỗi lượt, robot chạy `zrsd001` theo khách hàng SAP và ngày, cả "Open" lẫn "Complete". Mã đơn nào đã có SO thì chỉ ghi nhận số SO, không tạo lại.
- Tạo SO: loại đơn, tổ chức bán hàng, kênh, văn phòng, khách hàng SAP của sàn, `PO No` là mã đơn, các dòng mã vật tư và số lượng. Các giá trị đầu đơn lấy từ bản ghi recorder và nằm trong cấu hình.
- Đọc số SO từ thanh trạng thái sau khi lưu và ghi ngay vào đơn.
- Kiểm tra chéo sau lượt: chạy `zrsd001`, so tổng giá trị và từng dòng với giá trị mong đợi. Lệch thì đơn sang `NEED_REVIEW` và không được đi tiếp tới DO.
- Vòng đời việc tạo SO:
  1. Lưu thành công, đọc được số SO → `DONE`.
  2. SAP báo lỗi trước khi lưu → `FAILED`.
  3. Mất phiên hoặc không đọc được kết quả sau khi bấm lưu → `UNKNOWN`.
  4. Từ `UNKNOWN` chỉ có một đường: tra `zrsd001` theo `PO No`. Thấy SO thì ghi nhận; không thấy thì về `PENDING`; tra không được thì `NEED_REVIEW`.
- Đơn có trợ giá khác 0 không được xếp việc tạo SO; nó nằm trong danh sách "làm tay" của lô và trong file `ĐƠN HÀNG ONLINE`.
- Thông báo thiếu hàng hoặc popup lạ khi tạo SO: không bấm gì, `NEED_REVIEW`.
- Đổi chế độ của sàn chỉ do `admin`, có ghi `event_log`.

## Architecture

```
saprobot/transactions/create_so.py   tạo SO theo config/sap_screens.yaml
sapjobs/handlers/sales_order.py      kiểm tra trùng → tạo → ghi số SO → kiểm tra chéo
reconcile/shadow_report.py           tổng hợp kết quả đối chiếu của phase 4 theo ngày cho cổng G2
```

Khóa chống trùng của việc tạo SO là `(create_so, platform, platform_order_id)`.

## Related Code Files

- Create: `src/shoponline/saprobot/transactions/create_so.py`
- Create: `src/shoponline/sapjobs/handlers/sales_order.py`, `src/shoponline/reconcile/shadow_report.py`
- Modify: `config/sap_screens.yaml`, `config/sap_popups.yaml`, `web/routes/` (đổi chế độ, báo cáo shadow, danh sách làm tay)
- Create: `tests/sapjobs/test_sales_order_handler.py`, `tests/reconcile/test_shadow_report.py`
- Create: `docs/decisions/go-live-so.md`

## Implementation Steps

1. Viết `sales_order.py` với lớp thực thi giả. Test mọi nhánh: đã có SO, tạo thành công, lỗi trước khi lưu, mất phiên sau khi lưu, kiểm tra chéo lệch, đơn có trợ giá bị từ chối xếp việc. Test chứng minh không có đường nào từ `UNKNOWN` thẳng tới tạo lại.
2. Viết `shadow_report.py`; bật chế độ `shadow` cho Shopee trên hệ thống thật. Mỗi khác biệt được phân loại: sai ánh xạ, sai của người nhập, hoặc sai quy tắc. Sửa và thêm ca test.
3. Chủ dự án ghi recorder tạo SO trên QA: một đơn một dòng, một đơn nhiều dòng, một bộ sản phẩm. Trong lúc ghi, thử thêm `ZDI1` vào tab điều kiện của dòng và ghi lại kết quả cho phase 7.
4. Viết `create_so.py` từ bản ghi recorder; bổ sung popup gặp phải vào cấu hình.
5. Chủ dự án chạy robot trên QA với bộ đơn mẫu. So SO robot tạo với giá trị mong đợi. Chạy lại cùng bộ đơn để chứng minh không tạo trùng. Ngắt phiên ngay sau khi bấm lưu để chứng minh nhánh `UNKNOWN` tìm lại được SO.
6. Lần tạo SO đầu tiên trên hệ thống thật: một đơn do sales admin chỉ định, có sales admin ngồi cùng.
7. Khi đạt cổng G2, lập biên bản `go-live-so.md` rồi đổi Shopee sang `live`. Ở giai đoạn này robot chỉ tạo SO; sales admin vẫn tạo DO.
8. Tuần đầu ở chế độ `live`: sales admin xem lại mọi SO robot tạo trong ngày.

## Todo

- [ ] Handler tạo SO và test mọi nhánh
- [ ] Báo cáo shadow, bật `shadow` cho Shopee
- [ ] Bản ghi recorder tạo SO, kết quả thử `ZDI1` nhập tay
- [ ] `create_so.py`
- [ ] Đơn mẫu tạo đúng trên QA, chạy lại không trùng
- [ ] Thử nhánh `UNKNOWN` trên QA
- [ ] Lần tạo SO đầu tiên trên hệ thống thật có giám sát
- [ ] Biên bản G2 và bật `live`

## Success Criteria (cổng G2)

- Bộ đơn mẫu tạo đúng trên QA; chạy lại không tạo trùng; nhánh `UNKNOWN` đã được thử.
- Ít nhất 100 đơn liên tiếp và 10 ngày làm việc ở chế độ `shadow`, khớp 100%; không còn khác biệt chưa phân loại.
- Sau khi bật `live`: không mã đơn nào có hai SO; kiểm tra chéo hằng ngày không lệch.

## Verification

- `uv run pytest tests/sapjobs tests/reconcile` thoát mã 0.
- Truy vấn đếm SO theo `PO No` trong `sap_so_ref`: không mã nào có hơn một.

## Risk Assessment

- **Tạo trùng SO.** Ba lớp chặn: khóa chống trùng trong hàng đợi, tra `zrsd001` trước lượt, trạng thái `UNKNOWN` buộc tra SAP. Loại lệch "một `PO No` hai SO" của phase 4 là lưới cuối.
- **SAP định giá khác mong đợi.** Kiểm tra chéo chặn đơn ở `NEED_REVIEW`; robot không sửa giá.
- **Bản ghi `ZDI1` khác 0 do người để sót.** SO không giảm giá sẽ lệch giá trị và bị kiểm tra chéo chặn lại; phase 7 thêm bước kiểm tra trước lượt.
- **QA khác hệ thống thật.** Vì vậy vẫn có chế độ `shadow` và lần chạy đầu có người giám sát.

## Rollback

Đổi Shopee về `shadow` hoặc `manual`; sales admin tạo SO từ file hệ thống sinh. SO robot tạo sai không tự hủy: chuyển `NEED_REVIEW` cho người có quyền xử lý trong SAP.

## Security Considerations

- User robot chỉ được tạo loại đơn dành cho kênh sàn.
- Chỉ `admin` đổi được chế độ; mỗi lần đổi ghi người và thời điểm.

## Next Steps

Phase 7 thêm SO có trợ giá. Phase 8 nối tiếp từ đơn đã có số SO.
