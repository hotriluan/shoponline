---
title: "Phase 5: Xuất Excel, vận đơn, Web UI"
status: todo
priority: P1
effort: 6d
dependencies: [4]
---

# Phase 5: Xuất Excel, vận đơn, Web UI

## Overview

Hoàn tất Giai đoạn 1 của V2: sales admin nhận file Excel chuẩn hóa thay cho việc xuất tay từ ba sàn, kho in vận đơn hàng loạt và quét xác nhận đóng gói, mọi người xem trạng thái và đơn lỗi trên web. Đây là lần đầu hệ thống được dùng thật, nên sao lưu và cảnh báo cũng bắt đầu từ đây.

Ứng với V2 mục 4 và cổng G1.

## Key Insights

- Phase này không chạm SAP nên có lợi ngay và ít rủi ro.
- File Excel cho sales admin cần có mã đơn sàn ở đúng cột mà họ sẽ nhập vào trường tham chiếu SO. Việc này tạo sẵn khóa để phase 7 so sánh shadow.
- Web UI chỉ có vài màn hình nội bộ, render phía máy chủ là đủ.

## Requirements

- File Excel chuẩn hóa: đã ánh xạ SKU sang mã vật tư SAP, đúng mã khách hàng theo sàn, có mã đơn sàn, số lượng, giá và giảm giá theo `pricing.py`.
- Lấy vận đơn qua API từng sàn, gom thành một file in theo lô, sắp thứ tự ổn định.
- Kho quét mã đơn hoặc mã vận đơn để xác nhận đóng gói.
- Web UI có đăng nhập và vai trò: kho, sales admin, kế toán, quản trị.
- Màn hình: danh sách đơn có lọc, chi tiết đơn kèm lịch sử sự kiện, đơn lỗi (`MAPPING_ERROR`, `NEED_REVIEW`), quản lý ánh xạ SKU, in vận đơn, quét đóng gói.
- Sao lưu database hằng ngày và cảnh báo khi đồng bộ dừng.

## Architecture

```
exports/order_excel.py   đơn → file Excel cho sales admin
labels/service.py        gọi connector lấy vận đơn → lưu file → gom lô
web/app.py               FastAPI, phiên đăng nhập, phân quyền theo vai trò
web/routes/              orders, errors, sku_mapping, labels, packing, webhooks
web/templates/           Jinja2; tương tác nhỏ bằng HTMX
```

Connector được mở rộng thêm thao tác vận đơn: sắp xếp giao hàng (nếu `Capabilities` yêu cầu) và lấy tài liệu vận đơn. Ở phase này bước sắp xếp giao hàng do người bấm trên web; phase 8 nối nó vào luồng sau khi có DO.

Trạng thái đơn ở giai đoạn này: `NEW → VALIDATING → READY_FOR_SO`, rồi `LABEL_READY → PACKED → HANDED_OVER` do thao tác kho. Các trạng thái SAP ở giữa được sales admin làm tay và chưa do hệ thống ghi.

## Related Code Files

- Create: `src/shoponline/exports/order_excel.py`
- Create: `src/shoponline/labels/service.py`
- Modify: `src/shoponline/connectors/base.py`, `shopee.py`, `lazada.py`, `tiktok.py` (thao tác vận đơn)
- Create: `src/shoponline/web/app.py`, `web/auth.py`, `web/routes/*.py`, `web/templates/*.html`
- Create: `scripts/windows/backup-db.ps1`
- Modify: `scripts/windows/register-tasks.ps1` (tác vụ `web` và tác vụ sao lưu), `src/shoponline/cli.py` (lệnh `web`, `create-user`)
- Create: `tests/exports/test_order_excel.py`, `tests/labels/test_service.py`, `tests/web/test_auth.py`, `tests/web/test_packing.py`

## Implementation Steps

1. Lấy từ sales admin mẫu file Excel họ đang dùng để nhập SAP; viết `order_excel.py` sinh đúng bố cục đó, thêm cột mã đơn sàn.
2. Test xuất Excel: với đơn mẫu, mở lại file và so từng ô với giá trị `pricing.py` tính.
3. Thêm thao tác vận đơn vào từng connector theo kết quả phase 2; lưu file vận đơn ngoài database, lưu đường dẫn và tracking vào `shipment`.
4. Viết `labels/service.py`: chọn đơn theo lô, lấy vận đơn, gom thành một file, đánh dấu thời điểm in. In lại được nhưng có ghi `event_log`.
5. Viết `web/auth.py`: đăng nhập bằng mật khẩu băm, phiên bằng cookie, kiểm tra vai trò ở từng route.
6. Viết các màn hình theo thứ tự: danh sách và chi tiết đơn, đơn lỗi, ánh xạ SKU (thêm, sửa, nhập từ Excel), in vận đơn, quét đóng gói.
7. Màn hình quét: ô nhập nhận mã từ máy quét, tìm đơn, chuyển `PACKED`; quét đơn đã hủy thì báo đỏ và không chuyển.
8. Thêm điểm nhận webhook nếu sàn hỗ trợ: xác minh chữ ký, chỉ đưa tín hiệu đồng bộ sớm.
9. Viết `backup-db.ps1` chạy `pg_dump` hằng ngày, mã hóa file bằng khóa lưu trong kho bí mật, rồi chép ra hai nơi: ổ mạng công ty và thư mục đồng bộ Google Drive. Giữ theo số ngày đã chốt; cảnh báo khi sao lưu lỗi hoặc khi một trong hai nơi không ghi được. File chưa mã hóa không bao giờ rời máy, vì Google Drive là dịch vụ bên ngoài và bản sao lưu có dữ liệu người mua. Khóa mã hóa có một bản lưu ở nơi khác với cả hai nơi sao lưu. Vì mọi thứ nằm trên một máy, bản sao lưu chỉ nằm trên chính máy đó không được tính là sao lưu.
10. Thêm cảnh báo khi một sàn không đồng bộ thành công quá 30 phút.
11. Hướng dẫn sales admin và kho dùng thử; chạy song song với cách cũ một tuần rồi mới bỏ cách cũ.

## Todo

- [ ] Xuất Excel đúng mẫu sales admin
- [ ] Thao tác vận đơn cho ba connector
- [ ] In vận đơn theo lô
- [ ] Đăng nhập và phân quyền
- [ ] Màn hình đơn, đơn lỗi, ánh xạ SKU
- [ ] Màn hình quét đóng gói
- [ ] Webhook (nếu có)
- [ ] Sao lưu hằng ngày và cảnh báo sao lưu
- [ ] Cảnh báo đồng bộ dừng
- [ ] Hướng dẫn người dùng

## Success Criteria (cổng G1)

- 10 ngày làm việc liên tiếp, số đơn trong database khớp 100% với trang quản lý từng sàn.
- Sales admin nhập SAP hoàn toàn từ file Excel của hệ thống, không còn xuất tay từ sàn.
- Kho in vận đơn theo lô và quét xác nhận đóng gói cho mọi đơn.
- Một bản sao lưu được khôi phục thử vào database khác và đọc được đơn.

## Verification

- `uv run pytest tests/exports tests/labels tests/web` thoát mã 0.
- Sales admin đối chiếu 20 dòng Excel với dữ liệu trên sàn và ký xác nhận.
- Người dùng vai trò kho không mở được màn hình ánh xạ SKU (test tự động).

## Risk Assessment

- **Mẫu vận đơn hoặc quy trình sắp xếp giao hàng khác giữa các sàn.** Đã được ghi nhận ở phase 2 và thể hiện qua `Capabilities`.
- **In trùng vận đơn dẫn tới đóng gói hai lần.** Quét đóng gói lần hai cho cùng đơn báo cảnh báo rõ.
- **Web bị truy cập từ ngoài.** Web chạy trên máy robot, nghe trên một cổng cố định; tường lửa Windows chỉ mở cổng đó cho mạng nội bộ. Nếu cần truy cập từ xa thì qua VPN của công ty.
- **Người dùng web làm chậm robot.** Web và robot chung một máy; với vài người dùng nội bộ thì không đáng kể, nhưng việc xuất file lớn chạy ngoài giờ robot bận.

## Rollback

Tắt tác vụ `web`. Sales admin và kho quay lại cách cũ ngay vì chưa có gì trong SAP phụ thuộc hệ thống.

## Security Considerations

- Mật khẩu người dùng được băm; phiên hết hạn; có chống CSRF cho form.
- Địa chỉ người mua chỉ hiện cho vai trò cần (kho thấy trên vận đơn, không cần trên web).
- File vận đơn chứa dữ liệu cá nhân, lưu trong thư mục có giới hạn quyền và có thời hạn xóa.

## Next Steps

Phase 7 dùng mã đơn sàn mà sales admin nhập vào SO để so sánh shadow.
