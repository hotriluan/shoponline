---
title: "Phase 4: Connector ba sàn và đồng bộ đơn"
status: todo
priority: P1
effort: 8d
dependencies: [2, 3]
---

# Phase 4: Connector ba sàn và đồng bộ đơn

## Overview

Viết connector cho Shopee, Lazada, TikTok Shop (xác thực, làm mới token, lấy đơn, chuyển về đơn chung) và tiến trình Order Sync lấy đơn định kỳ vào PostgreSQL. Mở từng sàn một theo thứ tự Shopee (khoảng 20 đơn/ngày, hơn 80% số đơn), TikTok, Lazada.

Ứng với V2 mục 2.1, 3.2 và mục 4.

## Key Insights

- Ba sàn là ba biến thể thật, nên phần chung được tách ra ngay: một giao diện connector, phần ký request và ánh xạ dữ liệu nằm riêng từng sàn.
- Ba sàn khác nhau về khả năng: có sàn bắt buộc bước sắp xếp giao hàng trước khi có mã vận đơn, có sàn trả vận đơn dạng PDF, mức chi tiết đối soát khác nhau. Giao diện connector khai báo khả năng thay vì giả định ba sàn giống nhau.
- Với khoảng 24 đơn/ngày, polling 5 phút là đủ. Webhook chỉ là tín hiệu để lấy sớm, dữ liệu luôn lấy lại qua API.
- Một số sàn cấp refresh token mới sau mỗi lần làm mới. Mất token mới nghĩa là phải cấp quyền lại bằng tay.

## Requirements

- Giao diện connector chung với các thao tác: làm mới token, liệt kê đơn thay đổi từ một mốc, lấy chi tiết đơn, và khai báo khả năng.
- Token mới được ghi vào database trong cùng giao dịch với việc đánh dấu token cũ hết hiệu lực.
- Cảnh báo khi làm mới token thất bại và khi quyền kết nối shop sắp hết hạn.
- Order Sync chạy lại bao nhiêu lần cũng không tạo đơn trùng và không lùi trạng thái đơn.
- Tôn trọng giới hạn tần suất của từng sàn; lỗi tạm thời tự thử lại có giãn cách.
- Thời hạn token và địa chỉ cổng API là cấu hình, không viết cứng.

## Architecture

```
connectors/base.py     Connector (Protocol) + Capabilities
connectors/shopee.py   ký request, gọi API, ánh xạ → đơn chung
connectors/lazada.py
connectors/tiktok.py
connectors/token_store.py   đọc, làm mới, lưu token (mã hóa)
sync/order_sync.py     vòng lặp: mỗi shop → lấy đơn từ sync_cursor → upsert → kiểm tra
```

`Capabilities` gồm các cờ lấy từ kết quả phase 2: cần bước sắp xếp giao hàng, vận đơn có dữ liệu cấu trúc, có webhook, mức chi tiết đối soát.

**Truy vết mở rộng.** Khi thêm một sàn thứ tư, phần phải viết là một file connector và một bộ dữ liệu mẫu; `order_sync.py`, đơn chung, tính giá và máy trạng thái không đổi. Điều này được chứng minh bằng bộ test hợp đồng chạy chung cho cả ba connector.

**Luồng một vòng đồng bộ.** Đọc `sync_cursor` → lấy danh sách đơn thay đổi từ mốc đó trừ một khoảng chồng lấn → lấy chi tiết → chuyển về đơn chung → upsert theo `(shop_id, platform_order_id)` → đơn mới vào `NEW` rồi chạy kiểm tra (ánh xạ SKU, trạng thái hợp lệ) → cập nhật `sync_cursor` trong cùng giao dịch.

Tên API tham khảo, cần đối chiếu tài liệu hiện hành khi viết: Shopee Open API v2 (danh sách đơn, chi tiết đơn), Lazada (`/orders/get`, `/order/items/get`), TikTok Shop Partner API (tìm đơn, chi tiết đơn).

## Related Code Files

- Create: `src/shoponline/connectors/base.py`, `shopee.py`, `lazada.py`, `tiktok.py`, `token_store.py`
- Create: `src/shoponline/sync/order_sync.py`, `src/shoponline/sync/validation.py`
- Create: `src/shoponline/alerts/notifier.py` (kênh cảnh báo đầu tiên)
- Modify: `src/shoponline/cli.py` (lệnh `sync`, `connect-shop`)
- Create: `scripts/windows/register-tasks.ps1` (đăng ký tiến trình `sync` với Task Scheduler)
- Create: `tests/connectors/test_contract.py`, `tests/connectors/test_shopee_mapping.py`, `test_lazada_mapping.py`, `test_tiktok_mapping.py`, `tests/sync/test_order_sync.py`
- Create: `tests/fixtures/api/` (phản hồi API đã ghi lại và ẩn danh)

## Implementation Steps

1. Viết `base.py`: giao diện connector, `Capabilities`, các loại lỗi (tạm thời, hết quyền, giới hạn tần suất, dữ liệu không hợp lệ).
2. Viết `token_store.py`: lấy token còn hạn, làm mới trước khi hết hạn, ghi token mới trong một giao dịch có khóa dòng để hai tiến trình không cùng làm mới.
3. Viết lệnh `shoponline connect-shop <sàn>` dẫn người dùng qua bước cấp quyền OAuth và lưu token đầu tiên.
4. Viết connector sàn đầu tiên: ký request, phân trang, ánh xạ sang đơn chung. Dùng phản hồi đã ghi lại ở phase 2 làm dữ liệu test.
5. Viết `test_contract.py`: cùng một bộ kiểm tra chạy cho mọi connector (đơn chung đủ trường bắt buộc, tiền là số nguyên, mã đơn không rỗng, các khoản voucher tách đúng loại).
6. Viết `order_sync.py` và `validation.py`. Test: chạy hai lần liên tiếp cho cùng dữ liệu không đổi số dòng; đơn đã `SO_CREATED` mà sàn báo hủy thì sang `NEED_REVIEW`.
7. Viết `notifier.py` với một kênh cảnh báo (kênh do công ty chọn trong Zalo, Email, Telegram) và gom tin theo giờ.
8. Viết `register-tasks.ps1` đăng ký `shoponline sync` thành tác vụ Task Scheduler chạy khi máy khởi động, không cần ai đăng nhập, tự khởi động lại khi lỗi, ghi nhật ký ra file có xoay vòng. Chạy với shop thật của sàn đầu tiên ở chế độ chỉ đọc. Kiểm tra trước là chưa có tiến trình `sync` nào đang chạy để không chạy trùng.
9. Lặp lại bước 4 cho sàn thứ hai và thứ ba. Mỗi sàn chỉ bật sau khi sàn trước đã chạy ổn 3 ngày.
10. Nếu sàn có webhook: thêm điểm nhận ở phase 5 (khi có web), chỉ dùng để kích một vòng đồng bộ sớm.

## Todo

- [ ] Giao diện connector và `Capabilities`
- [ ] `token_store.py` và test làm mới đồng thời
- [ ] Lệnh `connect-shop`
- [ ] Connector sàn thứ nhất và test ánh xạ
- [ ] Bộ test hợp đồng chung
- [ ] `order_sync.py`, `validation.py` và test chạy lặp
- [ ] Cảnh báo làm mới token thất bại, quyền sắp hết hạn
- [ ] Tác vụ `sync` trong Task Scheduler
- [ ] Connector sàn thứ hai
- [ ] Connector sàn thứ ba

## Success Criteria

- Trong 5 ngày làm việc, danh sách đơn trong database của mỗi sàn khớp 100% với trang quản lý sàn (số đơn, tổng tiền, trạng thái).
- Tắt tiến trình `sync` một ngày rồi bật lại, không mất đơn và không trùng đơn.
- Token tự làm mới qua ít nhất hai chu kỳ mà không cần can thiệp.

## Verification

- `uv run pytest tests/connectors tests/sync` thoát mã 0.
- Câu truy vấn đếm đơn theo ngày trong database so với số trên trang quản lý sàn, làm mỗi ngày trong 5 ngày.

## Risk Assessment

- **Mất refresh token.** Giảm thiểu bằng giao dịch có khóa dòng và cảnh báo ngay khi làm mới thất bại. Khắc phục bằng lệnh `connect-shop`.
- **Sàn đổi API.** Test hợp đồng trên phản hồi đã ghi lại không bắt được thay đổi phía sàn; thêm kiểm tra khi chạy thật: phản hồi thiếu trường bắt buộc thì dừng đồng bộ sàn đó và cảnh báo, không ghi dữ liệu thiếu.
- **Bỏ sót đơn do lệch đồng hồ.** Mỗi vòng lấy chồng lấn một khoảng trước mốc; upsert làm việc này an toàn.

## Rollback

Tắt đồng bộ của sàn gặp vấn đề bằng cấu hình. Sales admin quay lại xuất Excel tay cho sàn đó. Dữ liệu đã đồng bộ giữ nguyên.

## Security Considerations

- Token mã hóa khi lưu; nhật ký không ghi token, chữ ký hay khóa ứng dụng.
- Nhật ký request chỉ ghi đường dẫn, mã phản hồi và mã đơn.

## Next Steps

Phase 5 dùng đơn đã đồng bộ để xuất Excel và in vận đơn.
