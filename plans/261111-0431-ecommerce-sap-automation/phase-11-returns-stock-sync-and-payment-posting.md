---
title: "Phase 11: Hàng hoàn, tồn kho, ghi nhận thanh toán"
status: todo
priority: P2
effort: 8d
dependencies: [8, 10]
---

# Phase 11: Hàng hoàn, tồn kho, ghi nhận thanh toán

## Overview

Ba phần độc lập, làm theo thứ tự: (A) hàng hoàn và thất lạc, (B) đồng bộ tồn kho từ SAP lên sàn có rào chắn, (C) ghi nhận thanh toán và bù trừ công nợ tự động có kế toán duyệt. Phần C chỉ bắt đầu sau cổng G6.

Ứng với V2 mục 8 và phần cuối mục 7.

## Key Insights

- Phần B là tính năng mới, không thuộc nỗi đau hiện tại, và đẩy sai có thể gây hết hàng oan hoặc bán vượt. Nó được làm sau cùng trong ba phần ghi lên sàn và luôn qua giai đoạn chạy thử không đẩy thật.
- Phần C là phần nhạy cảm nhất của kế toán. Tài khoản và quy tắc hạch toán do kế toán trưởng xác nhận; phí sàn có hóa đơn VAT riêng nên bút toán phải có thuế GTGT đầu vào.
- Hàng hoàn chạm cả kho, kế toán và CSKH, nên phần lớn giá trị nằm ở việc theo dõi và nhắc hạn chứ không ở thao tác SAP.

## Requirements

**A. Hàng hoàn và thất lạc**
- Phát hiện trạng thái hoàn hoặc thất lạc từ API, đưa vào bảng theo dõi.
- Kho quét hàng hoàn và chọn tình trạng: nguyên vẹn, hư hỏng hoặc đổi hàng, không nhận được.
- Hàng nguyên vẹn: nhập lại kho trong SAP qua hàng đợi, theo quy trình chứng từ kế toán chốt.
- Hàng hư hỏng: gắn cờ, đếm thời hạn khiếu nại cho CSKH.
- Thất lạc: theo dõi quá hạn (ngưỡng cấu hình, ví dụ 15 ngày) và nhắc nộp yêu cầu bồi thường.
- Khoản bị trừ do hoàn hàng hiện trong đối soát.

**B. Đồng bộ tồn kho lên sàn**
- Đọc tồn từ SAP theo lịch, lúc ít việc, có lưu đệm.
- Chế độ `dry-run` ghi lại số định đẩy mà không gọi API cập nhật.
- Không bao giờ đẩy số 0 khi không đọc được SAP.
- Giới hạn mức thay đổi tối đa mỗi lần; vượt thì dừng và cảnh báo.
- Tồn đệm theo từng SKU.
- Đồng bộ toàn bộ định kỳ, không chỉ khi có SO.

**C. Ghi nhận thanh toán**
- Hệ thống lập đề xuất bút toán cho từng đợt thanh toán từ `settlement_line`.
- Kế toán duyệt từng đợt trước khi robot ghi.
- Mỗi đợt thanh toán chỉ ghi một lần.

## Architecture

```
returns/tracker.py                 trạng thái hoàn/thất lạc, hạn khiếu nại, nhắc việc
saprobot/transactions/post_return.py   nhập lại kho (T-code theo quy trình kế toán chốt)
sapjobs/handlers/returns.py
stock/sync.py                      đọc tồn → áp tồn đệm → kiểm rào chắn → dry-run hoặc đẩy
connectors/*.py                    thêm thao tác cập nhật tồn kho
payments/proposal.py               settlement_line → đề xuất bút toán theo quy tắc kế toán trưởng
saprobot/transactions/post_payment.py
sapjobs/handlers/payment.py
```

Quy tắc hạch toán (tài khoản, khóa hạch toán, mã thuế) nằm trong một file cấu hình do kế toán trưởng duyệt, không viết trong mã.

## Related Code Files

- Create: `migrations/versions/<rev>_returns_and_stock.py`
- Create: `src/shoponline/returns/tracker.py`, `src/shoponline/sapjobs/handlers/returns.py`, `src/shoponline/saprobot/transactions/post_return.py`
- Create: `src/shoponline/stock/sync.py`
- Create: `src/shoponline/payments/proposal.py`, `src/shoponline/sapjobs/handlers/payment.py`, `src/shoponline/saprobot/transactions/post_payment.py`
- Create: `config/posting-rules.yaml`
- Modify: `src/shoponline/connectors/*.py`, `src/shoponline/web/routes/`, `config/sap_screens.yaml`, `config/sap_popups.yaml`
- Create: `tests/returns/`, `tests/stock/test_sync_guards.py`, `tests/payments/test_proposal.py`
- Create: `docs/decisions/go-live-payment-posting.md`

## Implementation Steps

**A. Hàng hoàn**
1. Chốt với kế toán quy trình chứng từ nhập lại kho (loại đơn trả hàng, giao nhận trả, hay bút toán kho) và ghi recorder thao tác đó.
2. Viết `tracker.py` và bảng theo dõi; test hạn khiếu nại và hạn thất lạc.
3. Viết màn hình quét hàng hoàn cho kho và danh sách việc cho CSKH.
4. Viết `post_return.py` và handler theo vòng đời của phase 6; kiểm tra đã nhập lại chưa trước khi làm. Chạy trên QA trước khi bật trên hệ thống thật.
5. Nối khoản trừ do hoàn hàng vào sheet bất thường của bảng kê.

**B. Tồn kho**
6. Viết `stock/sync.py` với các rào chắn; test từng rào chắn: SAP không đọc được thì không đẩy, thay đổi vượt ngưỡng thì dừng, tồn đệm không cho số âm.
7. Thêm thao tác cập nhật tồn kho vào connector.
8. Chạy `dry-run` ít nhất 2 tuần; mỗi ngày so số định đẩy với tồn đang hiển thị trên sàn và giải thích mọi khác biệt.
9. Bật đẩy thật cho một nhóm nhỏ SKU của một sàn, theo dõi một tuần, rồi mở rộng.

**C. Ghi nhận thanh toán (sau cổng G6)**
10. Kế toán trưởng duyệt `config/posting-rules.yaml` và ký `go-live-payment-posting.md`.
11. Viết `proposal.py`; test bằng các đợt thanh toán của ba kỳ đã khớp, so đề xuất với bút toán kế toán đã ghi tay.
12. Chạy shadow: hệ thống lập đề xuất, kế toán vẫn ghi tay, so từng đợt trong một kỳ.
13. Viết `post_payment.py` từ bản ghi recorder thao tác kế toán đang làm; thêm màn hình duyệt. Chạy trên QA với các đợt thanh toán mẫu và để kế toán kiểm tra bút toán ở đó.
14. Bật ghi thật cho một sàn; kế toán xem lại mọi bút toán trong kỳ đầu.

## Todo

- [ ] Quy trình và recorder nhập lại kho
- [ ] Theo dõi hoàn, thất lạc và nhắc hạn
- [ ] Màn hình quét hàng hoàn, danh sách CSKH
- [ ] Robot nhập lại kho
- [ ] Rào chắn đồng bộ tồn kho và test
- [ ] Dry-run tồn kho 2 tuần
- [ ] Đẩy tồn thật theo nhóm SKU
- [ ] Quy tắc hạch toán được kế toán trưởng duyệt
- [ ] Đề xuất bút toán và shadow một kỳ
- [ ] Robot ghi nhận thanh toán có duyệt

## Success Criteria

- Mọi đơn hoàn hoặc thất lạc trên sàn có một dòng theo dõi với hạn xử lý; không có khiếu nại nào quá hạn mà không được nhắc.
- Hàng hoàn nguyên vẹn được nhập lại kho đúng một lần.
- Trong giai đoạn `dry-run`, không có lần nào hệ thống định đẩy số 0 do lỗi đọc.
- **Cổng G6:** bảng kê khớp ba kỳ liên tiếp và kế toán trưởng ký duyệt quy tắc hạch toán.
- Đề xuất bút toán khớp bút toán ghi tay cho mọi đợt của một kỳ trước khi bật ghi thật.

## Verification

- `uv run pytest tests/returns tests/stock tests/payments` thoát mã 0.
- Báo cáo `dry-run` tồn kho và biên bản so đề xuất bút toán lưu trong `docs/decisions/`.

## Risk Assessment

- **Đẩy tồn sai gây bán vượt hoặc hết hàng oan.** Các rào chắn, tồn đệm, `dry-run` và mở theo nhóm SKU; có nút tắt đồng bộ tồn riêng.
- **Bút toán sai.** Shadow một kỳ, duyệt từng đợt, ghi một lần mỗi đợt; bút toán sai được kế toán đảo tay.
- **Kho còn thay đổi từ kênh khác.** Vì vậy đồng bộ toàn bộ theo lịch thay vì chỉ theo SO.

## Rollback

Mỗi phần có công tắc riêng. Tắt đồng bộ tồn thì sàn giữ số tồn hiện có và người quản lý cập nhật tay. Tắt ghi nhận thanh toán thì kế toán ghi tay từ bảng kê.

## Security Considerations

- Chỉ kế toán duyệt đề xuất bút toán; chỉ quản trị bật được đẩy tồn thật.
- User robot cần thêm quyền cho các T-code mới; xin đúng phạm vi.

## Next Steps

Phase 12 hoàn tất vận hành và bàn giao.
