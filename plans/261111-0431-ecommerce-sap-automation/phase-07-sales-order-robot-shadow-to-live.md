---
title: "Phase 7: Robot tạo SO, shadow rồi ghi thật"
status: todo
priority: P1
effort: 6d
dependencies: [5, 6]
---

# Phase 7: Robot tạo SO, shadow rồi ghi thật

## Overview

Tự động hóa Workflow A của V2: kiểm tra trùng, kiểm tồn, tạo Sales Order bằng `VA01`, đọc kết quả, kiểm tra chéo. Có ba bậc: robot tạo SO cho toàn bộ đơn mẫu trên hệ thống QA; rồi chạy shadow trên hệ thống thật (không lưu gì, chỉ so đề xuất với SO sales admin tạo tay); rồi mới ghi thật từng sàn sau khi qua cổng G2.

Ứng với V2 mục 5 (Workflow A, shadow mode).

## Key Insights

- QA chứng minh thao tác `VA01` của robot chạy đúng. Shadow chứng minh quy tắc giá và ánh xạ SKU đúng trên đơn thật. Hai việc này bổ sung cho nhau, không thay thế nhau.
- Sau phase 5, sales admin đã nhập mã đơn sàn vào trường tham chiếu SO. Nhờ đó shadow tìm đúng SO người tạo và so từng dòng.
- Shopee có khoảng 20 đơn/ngày nên hai tuần shadow cho khoảng 200 đơn; TikTok và Lazada mỗi sàn khoảng 15–20 đơn trong hai tuần, nên với hai sàn này điều kiện 30 đơn sẽ kéo dài hơn hai tuần.
- Ghi thật mở theo thứ tự TikTok, Shopee, Lazada: sàn ít đơn đi trước để sai sót đầu tiên, nếu có, ảnh hưởng ít chứng từ.
- Kiểm tra chéo sau khi lưu là lưới an toàn cuối: SAP tự định giá theo `ZPR1`, nên tổng SO lệch với giá trị mong đợi nghĩa là quy tắc giá hoặc dữ liệu chủ sai.

## Requirements

- Trước khi tạo: tìm SO theo mã đơn sàn; nếu đã có thì chỉ ghi lại số SO.
- Trước khi tạo: kiểm tồn khả dụng từng dòng; thiếu thì `STOCK_SHORT` và xử lý theo quyết định mục 9 của sổ quyết định.
- Tạo SO với loại đơn, tổ chức bán hàng, mã khách hàng của sàn, mã đơn sàn ở trường tham chiếu, các dòng, số lượng, điều kiện giảm giá nhập tay theo sổ quyết định.
- Đọc số SO từ thanh trạng thái sau khi lưu.
- Kiểm tra chéo: đọc lại SO, so tổng giá trị và từng dòng với giá trị mong đợi; lệch quá ngưỡng thì `NEED_REVIEW` và không đi tiếp.
- Chế độ chạy theo từng sàn: `off`, `shadow`, `live`, đổi bằng cấu hình và có ghi `event_log`.
- Đối chiếu hằng ngày ba phía: sàn, database, SAP.

## Architecture

```
saprobot/transactions/create_so.py   VA01 theo config/sap_screens.yaml
sapjobs/handlers/sales_order.py      kiểm tra trùng → kiểm tồn → tạo → đọc → kiểm tra chéo
reconcile/shadow_compare.py          đề xuất của robot ↔ SO người tạo, sinh báo cáo lệch
reconcile/daily_check.py             số đơn và tổng tiền sàn ↔ database ↔ SAP
```

**Shadow.** Với mỗi đơn `READY_FOR_SO`, hệ thống lưu đề xuất (dòng, số lượng, giá, giảm giá, tổng). Khi sales admin tạo SO tay, robot tìm SO theo mã đơn sàn, đọc bằng `VA03` và so với đề xuất. Kết quả là khớp hoặc danh sách khác biệt theo trường. Robot không mở `VA01` ở chế độ này.

**Live.** Việc tạo SO chạy theo vòng đời của phase 6. Sau `DONE`, đơn sang `SO_CREATED` chỉ khi kiểm tra chéo đạt.

## Related Code Files

- Create: `src/shoponline/saprobot/transactions/create_so.py`
- Create: `src/shoponline/sapjobs/handlers/sales_order.py`
- Create: `src/shoponline/reconcile/shadow_compare.py`, `reconcile/daily_check.py`
- Modify: `config/sap_screens.yaml`, `config/sap_popups.yaml` (màn hình và popup của `VA01`)
- Modify: `src/shoponline/web/routes/` (báo cáo shadow, báo cáo đối chiếu hằng ngày, đổi chế độ theo sàn)
- Create: `tests/sapjobs/test_sales_order_handler.py`, `tests/reconcile/test_shadow_compare.py`, `tests/reconcile/test_daily_check.py`
- Create: `docs/decisions/go-live-so.md` (biên bản cổng G2 từng sàn)

## Implementation Steps

1. Viết `sales_order.py` với lớp thực thi giả; test các nhánh: đã có SO, thiếu hàng, tạo thành công, lỗi trước khi lưu, mất phiên sau khi lưu, kiểm tra chéo lệch.
2. Viết `shadow_compare.py` và test bằng cặp đề xuất và SO mẫu, gồm trường hợp khác thứ tự dòng và combo bị bung.
3. Viết `daily_check.py`: mỗi ngày so số đơn và tổng tiền theo sàn giữa trang sàn, database và SAP (đếm SO theo mã khách hàng sàn và ngày); lệch thì cảnh báo.
4. Bật chế độ `shadow` trên hệ thống thật cho Shopee trước, rồi các sàn còn lại khi connector sẵn sàng. Xem báo cáo lệch mỗi ngày; mỗi khác biệt được phân loại: sai quy tắc giá, sai ánh xạ SKU, sai của người nhập, hoặc khác biệt chấp nhận được. Ba loại đầu phải sửa và thêm đơn mẫu vào test.
5. Viết `create_so.py` từ bản ghi recorder `VA01`: nhập đầu đơn, trường tham chiếu, dòng hàng, điều kiện giảm giá, lưu, đọc thanh trạng thái. Bổ sung popup gặp phải vào cấu hình.
6. Chạy trên QA: chủ dự án chạy robot với toàn bộ đơn mẫu của ba sàn nhắm vào QA. Với mỗi đơn, so SO robot tạo với giá trị mong đợi và với một SO sales admin tạo tay trên QA cho cùng đơn. Chạy lại cùng bộ đơn lần hai để chứng minh không tạo trùng. Thử ngắt phiên ngay sau khi bấm lưu để chứng minh nhánh `UNKNOWN` tìm lại được SO.
7. Lần chạy `VA01` đầu tiên trên hệ thống thật: một đơn TikTok do sales admin chỉ định, có sales admin ngồi cùng.
8. Khi TikTok đạt cổng G2, lập biên bản `go-live-so.md` có chữ ký sales admin và kế toán, rồi đổi chế độ sang `live`.
9. Tuần đầu ở chế độ `live`: sales admin xem lại mọi SO robot tạo trong ngày.
10. Lặp lại bước 8, 9 cho Shopee rồi Lazada. Với Shopee, theo dõi thêm độ dài hàng đợi trong ngày vì đây là lúc tải thật lên robot tăng gấp nhiều lần.

## Todo

- [ ] Handler tạo SO và test mọi nhánh
- [ ] So sánh shadow và báo cáo lệch
- [ ] Đối chiếu hằng ngày ba phía
- [ ] Shadow Shopee, TikTok, Lazada
- [ ] `create_so.py` từ recorder
- [ ] Toàn bộ đơn mẫu tạo đúng trên QA, chạy lại không trùng
- [ ] Thử nhánh `UNKNOWN` trên QA
- [ ] Lần chạy `VA01` đầu tiên trên hệ thống thật có giám sát
- [ ] Biên bản G2 và bật live TikTok
- [ ] Biên bản G2 và bật live Shopee
- [ ] Biên bản G2 và bật live Lazada

## Success Criteria (cổng G2, theo từng sàn)

- Toàn bộ đơn mẫu của sàn tạo đúng trên QA; chạy lại không tạo trùng; nhánh `UNKNOWN` đã được thử.
- Ít nhất 30 đơn liên tiếp và tối thiểu 2 tuần ở chế độ shadow, đề xuất khớp 100% với SO sales admin tạo.
- Không còn khác biệt nào chưa phân loại.
- Sau khi bật live: không có mã đơn sàn nào ứng với hai SO; đối chiếu hằng ngày bằng 0.

## Verification

- `uv run pytest tests/sapjobs tests/reconcile` thoát mã 0.
- Truy vấn kiểm tra trùng: đếm SO theo mã đơn sàn, không mã nào có hơn một.
- Báo cáo shadow và biên bản G2 lưu trong `docs/decisions/go-live-so.md`.

## Risk Assessment

- **Tạo trùng SO.** Ba lớp chặn: khóa chống trùng trong hàng đợi, tìm SO trước khi tạo, và trạng thái `UNKNOWN` buộc tra SAP. Truy vấn kiểm tra trùng chạy trong đối chiếu hằng ngày.
- **SAP định giá khác mong đợi.** Kiểm tra chéo chặn đơn lại ở `NEED_REVIEW`; không tự sửa giá.
- **Sales admin không nhập mã đơn sàn trong giai đoạn shadow.** Khi đó không so được; báo cáo shadow liệt kê đơn chưa tìm thấy SO để nhắc.
- **Số đơn ít ở TikTok và Lazada làm cổng G2 kéo dài.** Chấp nhận; không hạ ngưỡng để kịp tiến độ.
- **QA khác hệ thống thật** (giá, dữ liệu chủ, bố cục màn hình). Vì vậy QA không thay cho shadow và lần chạy đầu trên hệ thống thật vẫn có người giám sát.
- **Chứng từ thử lẫn vào dữ liệu thật.** Việc nhắm vào QA chỉ nằm trong database `shoponline_dev`; robot kiểm tra hệ thống đích trước mỗi việc (phase 6).

## Rollback

Đổi chế độ của sàn về `shadow` hoặc `off`; sales admin tạo SO tay từ file Excel như ở phase 5. SO robot đã tạo sai không tự đảo: chuyển `NEED_REVIEW` cho người có quyền xử lý trong SAP.

## Security Considerations

- Chỉ vai trò quản trị đổi được chế độ `shadow`/`live`, và mỗi lần đổi có ghi người, thời điểm.
- User robot chỉ được tạo loại đơn dành cho kênh sàn.

## Next Steps

Phase 8 nối tiếp từ `SO_CREATED`.
