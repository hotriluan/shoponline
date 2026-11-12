---
title: "Phase 7: Robot tạo SO có giảm giá ZDI1"
status: cancelled
priority: P2
effort: 3d
dependencies: [6]
---

# Phase 7: Robot tạo SO có giảm giá ZDI1

> **Đã bỏ ngày 2026-11-12.** Robot không ghi vào SAP; sales admin tiếp tục tạo SO và DO. Robot chỉ đọc `zrsd001` và `zrsd004` trên Production (phase 5). Lý do: [báo cáo brainstorm thu hẹp robot](../reports/brainstorm-261112-0915-robot-read-only-production-scope.md). Nội dung bên dưới giữ lại để tham khảo nếu sau này mở lại thành dự án riêng.

## Overview

Robot tạo SO cho đơn Shopee có trợ giá. Trợ giá đi vào SO bằng điều kiện `ZDI1`, số tiền cho một đơn vị sản phẩm, đã gồm VAT. Trước phase này các đơn đó do sales admin làm tay.

## Key Insights

- Hiện nay `ZDI1` được nhập bằng `VK11` dưới dạng bản ghi theo cặp khách hàng SAP và mã vật tư. Mọi đơn Shopee dùng chung khách hàng `1200001145`, nên bản ghi có hiệu lực cho mọi SO Shopee của mã vật tư đó cho tới khi được đưa về 0.
- Vì vậy thứ tự hiện nay là: tạo hết SO không giảm giá, rồi với từng đơn có giảm giá thì nhập bản ghi, tạo SO, đưa bản ghi về 0.
- Billing lấy giá từ SO, nên đưa bản ghi về 0 sau khi tạo SO không làm lệch hóa đơn.
- Chưa biết `ZDI1` có nhập tay được trên tab điều kiện của dòng SO không. Kết quả thử nằm trong bản ghi recorder của phase 6.
- Chưa có SO mẫu nào có giảm giá; cột `Discount` của `zrsd001` trống ở mọi dòng mẫu.

## Requirements

**Chọn cách làm theo kết quả thử ở phase 6:**

- **Cách A, nếu SAP cho nhập tay trên dòng SO:** robot thêm `ZDI1` với số tiền một đơn vị vào từng dòng được giảm. Không đụng bản ghi dùng chung, không ràng buộc thứ tự.
- **Cách B, mặc định:** robot làm như hiện nay bằng bản ghi điều kiện, với bốn chốt chặn:
  1. Trước lượt SO không giảm giá, đọc bản ghi `ZDI1` của khách hàng SAP của sàn; có bản ghi khác 0 thì dừng cả lượt và cảnh báo.
  2. Với từng đơn có giảm giá: nhập số tiền cho mọi mã vật tư được giảm của đơn đó, tạo SO, đọc lại giá trị SO và so với giá trị mong đợi, đưa các bản ghi về 0, đọc lại để chắc đã về 0.
  3. Bất kỳ bước nào ở mục 2 lỗi hoặc không rõ kết quả thì robot dừng hẳn, không làm đơn kế tiếp. Trước khi dừng, robot cố đưa bản ghi về 0; không làm được thì cảnh báo nêu rõ mã vật tư còn bản ghi khác 0.
  4. Trong lượt giảm giá, không ai gõ tay SO Shopee. Màn hình lô hiện rõ "robot đang làm lượt giảm giá".

**Chung cho cả hai cách:**

- Lượt giảm giá luôn chạy sau lượt không giảm giá của cùng lô.
- Kiểm tra chéo: tổng giá trị SO bằng Σ (giá gốc − trợ giá) × số lượng; lệch thì `NEED_REVIEW`.
- Một dòng có trợ giá mà hệ thống không tính ra số nguyên đồng cho một đơn vị thì đơn ở lại danh sách làm tay.

## Architecture

```
saprobot/transactions/condition_record.py   đọc, đặt, đưa về 0 bản ghi ZDI1 (cách B)
saprobot/transactions/create_so.py          thêm bước nhập ZDI1 trên dòng (cách A)
sapjobs/handlers/discounted_sales_order.py  trình tự và chốt chặn
```

Mã điều kiện `ZDI1` và T-code đọc, sửa bản ghi nằm trong cấu hình.

## Related Code Files

- Create: `src/shoponline/sapjobs/handlers/discounted_sales_order.py`
- Create (cách B): `src/shoponline/saprobot/transactions/condition_record.py`
- Modify: `src/shoponline/saprobot/transactions/create_so.py`, `config/sap_screens.yaml`, `config/sap_popups.yaml`
- Modify: `web/routes/batches.py` (trạng thái lượt giảm giá)
- Create: `tests/sapjobs/test_discounted_sales_order.py`
- Modify: `docs/robot-runbook.md` (xử lý khi bản ghi `ZDI1` còn sót)

## Implementation Steps

1. Đọc kết quả thử nhập tay `ZDI1` trong bản ghi recorder của phase 6 và chốt cách A hoặc B; ghi quyết định vào `docs/decisions/go-live-so.md`.
2. Với cách B, chủ dự án ghi recorder trên QA: xem bản ghi `ZDI1`, đặt số tiền, đưa về 0.
3. Viết `discounted_sales_order.py` với lớp thực thi giả. Test: lượt giảm giá không chạy khi lượt không giảm giá chưa xong; lỗi giữa chừng làm robot dừng và có bước đưa về 0; bản ghi khác 0 có sẵn chặn lượt không giảm giá; hai đơn cùng mã vật tư khác số tiền được làm tuần tự.
4. Viết thao tác SAP theo cách đã chọn.
5. Chủ dự án chạy trên QA: đơn một dòng có giảm giá, đơn nhiều dòng chỉ một dòng giảm giá, hai đơn cùng mã vật tư khác số tiền. Sau mỗi lượt kiểm tra bản ghi `ZDI1` đã về 0 và tạo một SO không giảm giá để chứng minh giá về bình thường.
6. Ngắt phiên giữa lúc bản ghi đang khác 0 trên QA; xác nhận robot dừng và cảnh báo nêu đúng mã vật tư.
7. Lần chạy đầu trên hệ thống thật có sales admin ngồi cùng; tuần đầu sales admin xem lại mọi SO có giảm giá.

## Todo

- [ ] Chốt cách A hoặc B từ kết quả thử trên QA
- [ ] Bản ghi recorder cho bản ghi điều kiện (cách B)
- [ ] Handler và test các chốt chặn
- [ ] Thao tác SAP
- [ ] Ba ca trên QA và kiểm tra bản ghi về 0
- [ ] Thử ngắt phiên giữa chừng
- [ ] Lần chạy đầu trên hệ thống thật có giám sát

## Success Criteria

- Trên QA, mọi SO có giảm giá có giá trị đúng bằng giá trị mong đợi.
- Sau mỗi lượt, không còn bản ghi `ZDI1` khác 0 cho khách hàng SAP của sàn (cách B).
- SO không giảm giá tạo ngay sau lượt giảm giá có giá bình thường.

## Verification

- `uv run pytest tests/sapjobs/test_discounted_sales_order.py` thoát mã 0.
- Biên bản chạy QA ghi trong `docs/decisions/go-live-so.md`.

## Risk Assessment

- **Bản ghi `ZDI1` còn sót làm SO sau bị giảm giá sai.** Chốt chặn 1–3; kiểm tra chéo giá trị SO là lưới cuối; sổ tay có mục xử lý tay.
- **Người khác sửa bản ghi `ZDI1` cùng lúc.** Chốt chặn 4 và bước đọc lại sau khi đặt.
- **Chưa có ví dụ thật.** Chỉ bật trên hệ thống thật sau khi cả ba ca QA đúng và sales admin xác nhận cách nhập giống cách họ làm.

## Rollback

Tắt lượt giảm giá bằng cấu hình; đơn có trợ giá quay lại danh sách làm tay. Kiểm tra bản ghi `ZDI1` đã về 0 trước khi tắt.

## Security Considerations

- User robot cần quyền sửa bản ghi điều kiện `ZDI1` ở cách B; giới hạn quyền đó cho đúng loại điều kiện và khách hàng sàn nếu SAP cho phép.

## Next Steps

Không có phase nào phụ thuộc phase này.
