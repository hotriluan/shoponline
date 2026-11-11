---
title: "Phase 8: DO, đóng gói, PGI"
status: todo
priority: P1
effort: 6d
dependencies: [7]
---

# Phase 8: DO, đóng gói, PGI

## Overview

Tự động hóa Workflow C của V2 theo đúng thứ tự thực tế: tạo DO, sắp xếp giao hàng và lấy vận đơn, in, kho đóng gói và quét, PGI sau khi kho xác nhận, rồi ghi nhận bàn giao cho shipper.

Ứng với V2 mục 5 (Workflow C) và giai đoạn 2b.

## Key Insights

- PGI ghi giảm tồn kho và sinh bút toán, nên khó đảo hơn SO và DO. PGI chỉ chạy khi có xác nhận của kho.
- Đơn có thể bị hủy bất kỳ lúc nào trước khi shipper nhận. Trước mỗi bước ghi SAP phải kiểm tra lại trạng thái đơn trên sàn.
- Phần in vận đơn và quét đóng gói đã có từ phase 5; phase này nối chúng vào luồng sau DO.

## Requirements

- Tạo DO bằng `VL01N` tham chiếu số SO; kiểm tra DO đã tồn tại cho SO đó trước khi tạo.
- Sắp xếp giao hàng và lấy vận đơn qua API theo thứ tự của từng sàn (theo `Capabilities`).
- Phiếu lấy hàng cho kho có số DO và mã đơn.
- PGI bằng `VL02N` chỉ khi đơn ở `PACKED` (hoặc khi shipper nhận, theo quyết định mục 12 của sổ quyết định).
- Trước DO và trước PGI: lấy lại trạng thái đơn từ sàn; nếu đã hủy thì dừng và chuyển `NEED_REVIEW`.
- `HANDED_OVER` khi sàn báo shipper đã lấy hàng hoặc kho xác nhận bàn giao.
- Đơn sắp quá hạn giao cho shipper được ưu tiên trong hàng đợi và có cảnh báo.
- Chế độ `off`/`live` riêng cho DO và cho PGI, theo từng sàn.

## Architecture

```
saprobot/transactions/create_do.py   VL01N
saprobot/transactions/find_do.py     tra DO theo SO (luồng chứng từ)
saprobot/transactions/post_gi.py     VL02N
sapjobs/handlers/delivery.py         kiểm tra hủy → kiểm tra trùng → tạo DO → đọc số
sapjobs/handlers/goods_issue.py      kiểm tra hủy → kiểm tra đã PGI chưa → PGI → đọc lại trạng thái
```

Luồng trạng thái: `SO_CREATED → DO_CREATED → LABEL_READY → PACKED → PGI_DONE → HANDED_OVER`.

Sau PGI, robot đọc lại trạng thái xuất kho của DO để xác nhận, vì thông báo trên thanh trạng thái của `VL02N` không kèm số chứng từ mới theo cùng cách như `VA01`.

## Related Code Files

- Create: `src/shoponline/saprobot/transactions/create_do.py`, `find_do.py`, `post_gi.py`
- Create: `src/shoponline/sapjobs/handlers/delivery.py`, `goods_issue.py`
- Modify: `src/shoponline/labels/service.py` (tự chạy sau `DO_CREATED`)
- Modify: `src/shoponline/sync/order_sync.py` (phát hiện shipper đã lấy hàng, phát hiện hủy)
- Modify: `src/shoponline/web/routes/` (phiếu lấy hàng, xác nhận bàn giao, danh sách đơn sắp quá hạn)
- Modify: `src/shoponline/reconcile/daily_check.py` (thêm DO và PGI)
- Modify: `config/sap_screens.yaml`, `config/sap_popups.yaml`
- Create: `tests/sapjobs/test_delivery_handler.py`, `tests/sapjobs/test_goods_issue_handler.py`, `tests/sync/test_cancellation.py`

## Implementation Steps

1. Viết `delivery.py` và `goods_issue.py` với lớp thực thi giả; test: DO đã tồn tại, đơn hủy trước DO, đơn hủy giữa DO và PGI, PGI đã thực hiện, mất phiên sau khi bấm PGI.
2. Viết `find_do.py` để tra DO theo SO, dùng cho kiểm tra trùng và cho phục hồi từ `UNKNOWN`.
3. Viết `create_do.py` từ bản ghi recorder `VL01N`: điểm giao hàng, ngày chọn, số SO, lưu, đọc số DO.
4. Nối `labels/service.py`: khi đơn sang `DO_CREATED`, tự sắp xếp giao hàng (nếu sàn yêu cầu), lấy vận đơn, chuyển `LABEL_READY`.
5. Thêm phiếu lấy hàng trên web: danh sách DO của lô, dòng hàng, vị trí kho nếu có.
6. Viết `post_gi.py` từ bản ghi recorder `VL02N`: mở DO, nhập số lượng lấy hàng nếu quy trình yêu cầu, bấm PGI, đọc thanh trạng thái, đọc lại trạng thái xuất kho.
7. Cập nhật `order_sync.py`: sàn báo đã lấy hàng thì `HANDED_OVER`; sàn báo hủy khi đã có chứng từ thì `NEED_REVIEW` kèm danh sách chứng từ cần xử lý.
8. Mở rộng đối chiếu hằng ngày: đơn `PGI_DONE` phải có DO đã xuất kho trong SAP; đơn `HANDED_OVER` phải đã PGI.
9. Chạy trên QA: với các SO đã tạo trên QA ở phase 7, robot tạo DO rồi PGI; chạy lại để chứng minh không tạo trùng; thử ngắt phiên sau khi bấm PGI. Nếu QA thiếu tồn kho thì nhờ người phụ trách nạp tồn thử như đã chốt ở phase 2.
10. Bật `live` cho DO ở TikTok sau cổng G3; chạy một tuần với kho xem lại; rồi bật `live` cho PGI.
11. Lặp lại bước 10 cho Shopee rồi Lazada.
12. Đo lại năng lực với đủ chuỗi thao tác (tìm SO, tạo SO, DO, PGI) trên tải Shopee thật, và thử tải 100 đơn mẫu trên QA trong một ngày. Mục tiêu: 100 đơn/ngày mà không đơn nào quá hạn giao cho shipper. Nếu một phiên không đạt, ghi rõ ngưỡng thực tế và cách làm tay phần vượt vào sổ tay, và báo chủ dự án về lựa chọn thêm phiên SAP.

## Todo

- [ ] Handler DO, PGI và test mọi nhánh
- [ ] Tra DO theo SO
- [ ] `create_do.py`
- [ ] Vận đơn tự chạy sau DO
- [ ] Phiếu lấy hàng
- [ ] `post_gi.py`
- [ ] Phát hiện bàn giao và hủy
- [ ] Đối chiếu hằng ngày có DO và PGI
- [ ] DO và PGI chạy đúng trên QA, chạy lại không trùng
- [ ] Live DO rồi PGI cho TikTok, Shopee, Lazada
- [ ] Thử tải 100 đơn trên QA và đo năng lực với đủ chuỗi thao tác

## Success Criteria

- **Cổng G3 (điều kiện bắt đầu ghi thật):** 30 đơn liên tiếp robot tạo SO thật không trùng, không lệch; đối chiếu hằng ngày bằng 0.
- 30 đơn liên tiếp đi từ `SO_CREATED` tới `HANDED_OVER` không cần nhập tay vào SAP.
- Không có đơn nào PGI khi chưa được kho quét xác nhận.
- Không có đơn hủy nào bị PGI.

## Verification

- `uv run pytest tests/sapjobs tests/sync` thoát mã 0.
- Mỗi ngày trong tuần đầu, kho đối chiếu danh sách PGI của robot với hàng thực xuất.

## Risk Assessment

- **PGI cho đơn đã hủy.** Kiểm tra trạng thái sàn ngay trước PGI; đơn hủy sau PGI sang `NEED_REVIEW` và không tự đảo.
- **Quá hạn giao cho shipper do robot dừng.** Cảnh báo riêng cho đơn sắp quá hạn; sổ tay ghi cách làm tay khi robot dừng.
- **`VL01N` báo thiếu hàng dù đã kiểm tồn.** Xử lý như `STOCK_SHORT`, không cố tạo DO một phần.

## Rollback

Đặt chế độ DO hoặc PGI của sàn về `off`; kho và sales admin làm tay hai bước này trong khi SO vẫn do robot tạo. Chứng từ đã ghi sai được người có quyền xử lý trong SAP.

## Security Considerations

- Chỉ vai trò kho xác nhận đóng gói và bàn giao; mỗi lần quét ghi người và thời điểm.
- User robot cần thêm quyền `VL01N`, `VL02N`; xin đúng các quyền này, không xin rộng hơn.

## Next Steps

Phase 9 lập billing cho đơn `HANDED_OVER`.
