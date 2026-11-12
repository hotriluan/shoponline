---
title: "Phase 8: Robot tạo DO và post goods issue"
status: cancelled
priority: P1
effort: 4d
dependencies: [6]
---

# Phase 8: Robot tạo DO và post goods issue

> **Đã bỏ ngày 2026-11-12.** Robot không ghi vào SAP; sales admin tiếp tục tạo SO và DO. Robot chỉ đọc `zrsd001` và `zrsd004` trên Production (phase 5). Lý do: [báo cáo brainstorm thu hẹp robot](../reports/brainstorm-261112-0915-robot-read-only-production-scope.md). Nội dung bên dưới giữ lại để tham khảo nếu sau này mở lại thành dự án riêng.

## Overview

Robot tạo DO cho SO Shopee đã qua kiểm tra chéo, đặt ngày goods issue theo quy tắc của lô, rồi post. Sau phase này đơn Shopee không có trợ giá đi từ file sàn tới DO đã post mà không ai gõ tay vào SAP.

## Key Insights

- DO được tạo và post ngay trong ngày D; chỉ ngày goods issue là lùi sang ngày làm việc kế tiếp. `docs/zrsd004.XLSX` cho thấy `Delivery Date` 10/11, `Actual GI Date` 11/11, trạng thái `C`.
- Ngày cuối tháng thì ngày goods issue là chính ngày D, không sang tháng khác.
- Post goods issue khó đảo ngược hơn tạo SO: hủy phải đảo goods issue rồi xóa DO. Việc hủy do người làm.
- Mỗi SO ra một DO; DO của bộ sản phẩm có nhiều dòng (`Line Item` 10, 20, 30).
- Các bước màn hình giữa tạo DO và post (ví dụ nhập số lượng picking) chưa biết; lấy từ bản ghi recorder.

## Requirements

- Chỉ tạo DO cho đơn có số SO và đã qua kiểm tra chéo giá trị. Đơn `NEED_REVIEW` hoặc `CANCELLED` không được xếp việc.
- Trước lượt, robot chạy `zrsd004` cho các SO của lô; SO nào đã có DO thì chỉ ghi nhận số DO.
- Ngày goods issue lấy từ lô (đề xuất của `gi_date.py`, admin có thể đã sửa). Robot không tự tính lại.
- Sau khi post, đọc số DO và ghi vào đơn. Sau lượt, chạy `zrsd004` và xác nhận từng DO có đúng `Actual GI Date` và trạng thái đã post; khác thì `NEED_REVIEW`.
- Vòng đời việc giống phase 6: mất phiên sau khi bấm lưu hoặc post thì `UNKNOWN`, và từ đó chỉ đi tiếp sau khi tra `zrsd004` theo số SO.
- DO đã tạo nhưng chưa post được: không tạo lại; việc post là một việc riêng, có khóa chống trùng riêng theo số DO.
- SAP từ chối ngày goods issue (kỳ chưa mở) hoặc thiếu tồn: không thử ngày khác, `NEED_REVIEW` và cảnh báo.
- Admin chọn được từng lô: robot làm tới SO rồi dừng, hoặc làm cả DO.

## Architecture

```
saprobot/transactions/create_delivery.py   tạo DO từ SO
saprobot/transactions/post_goods_issue.py  đặt ngày goods issue, post
sapjobs/handlers/delivery.py               kiểm tra trùng → tạo → post → xác nhận bằng zrsd004
```

Khóa chống trùng: `(create_delivery, so_number)` và `(post_goods_issue, delivery_number)`.

## Related Code Files

- Create: `src/shoponline/saprobot/transactions/create_delivery.py`, `post_goods_issue.py`
- Create: `src/shoponline/sapjobs/handlers/delivery.py`
- Modify: `config/sap_screens.yaml`, `config/sap_popups.yaml`, `web/routes/batches.py`
- Create: `tests/sapjobs/test_delivery_handler.py`
- Create: `docs/decisions/go-live-do.md`

## Implementation Steps

1. Chủ dự án ghi recorder trên QA: tạo DO từ SO, đặt ngày goods issue là ngày làm việc kế tiếp, post; thêm một lần với bộ sản phẩm.
2. Viết `delivery.py` với lớp thực thi giả. Test: SO chưa qua kiểm tra chéo bị từ chối; đã có DO thì không tạo lại; tạo được nhưng post lỗi thì chỉ việc post được làm lại; mất phiên sau khi post dẫn tới `UNKNOWN` rồi tra `zrsd004`.
3. Viết `create_delivery.py` và `post_goods_issue.py` từ bản ghi recorder.
4. Chủ dự án chạy trên QA: bộ đơn mẫu; chạy lại để chứng minh không tạo trùng DO; một lô có ngày D là ngày làm việc cuối tháng (ngày goods issue bằng D); một lô ngày thứ Sáu (ngày goods issue là thứ Hai).
5. Trên QA, thử ngắt phiên giữa tạo DO và post, và ngay sau khi post.
6. Đo thời gian trung bình mỗi đơn cho cả chuỗi SO, DO, post; tính số đơn một phiên làm được trong một ngày và so với ngày cao điểm 100 đơn. Ghi vào `docs/robot-runbook.md`.
7. Lần chạy đầu trên hệ thống thật: một lô nhỏ, có sales admin ngồi cùng. Lập biên bản `go-live-do.md` khi đạt cổng G3.
8. Tuần đầu: sales admin xem lại mọi DO robot tạo trong ngày.

## Todo

- [ ] Bản ghi recorder tạo DO và post
- [ ] Handler và test mọi nhánh
- [ ] Thao tác tạo DO và post
- [ ] Bộ đơn mẫu trên QA, chạy lại không trùng
- [ ] Ca cuối tháng và ca thứ Sáu trên QA
- [ ] Thử ngắt phiên trên QA
- [ ] Đo năng lực một phiên
- [ ] Lần chạy đầu trên hệ thống thật có giám sát, biên bản G3

## Success Criteria (cổng G3)

- 30 SO liên tiếp robot tạo thật không trùng, không lệch giá trị, trước khi bật DO.
- Trên QA: DO post đúng ngày goods issue cho ngày thường, thứ Sáu và cuối tháng; chạy lại không tạo trùng.
- Sau khi bật: mọi DO robot tạo xuất hiện trong `zrsd004` với đúng ngày goods issue.

## Verification

- `uv run pytest tests/sapjobs/test_delivery_handler.py` thoát mã 0.
- So `zrsd004` của ngày goods issue với danh sách đơn `live` của lô: không thiếu, không thừa.

## Risk Assessment

- **Tạo trùng DO.** Khóa chống trùng, tra `zrsd004` trước lượt, và trạng thái `UNKNOWN`. SAP cũng từ chối tạo DO cho SO đã giao đủ.
- **Post nhầm ngày.** Ngày lấy từ lô, hiện trên màn hình lô trước khi robot chạy, và được xác nhận lại bằng `zrsd004`.
- **Một phiên không kịp ngày cao điểm.** Con số đo ở bước 6 quyết định; phần vượt do sales admin làm từ file hệ thống sinh bằng cách để lô ở chế độ làm tới SO.
- **Đơn hủy sau khi robot đã post.** Người xử lý trong SAP như hiện nay; admin đánh dấu đơn `CANCELLED` trên web.

## Rollback

Đặt lô về "robot làm tới SO rồi dừng"; sales admin tạo DO như trước. DO sai không tự đảo.

## Security Considerations

- User robot chỉ có quyền tạo và post loại DO của kênh sàn.
- Chỉ `admin` bật được việc robot tạo DO.

## Next Steps

Phase 9 hoàn thiện vận hành và bàn giao.
