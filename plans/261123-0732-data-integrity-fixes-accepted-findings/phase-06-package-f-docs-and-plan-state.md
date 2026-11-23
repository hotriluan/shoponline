---
title: "Phase 6: Gói F — tài liệu, rủi ro chấp nhận và trạng thái plan"
status: completed
priority: P3
effort: 0.5d
dependencies: [1, 2, 3, 4, 5]
---

# Phase 6: Gói F — tài liệu, rủi ro chấp nhận và trạng thái plan

## Overview

Đóng các phát hiện không đáng sửa mã bằng cách ghi rõ vào tài liệu, sửa chỗ plan hoặc tài liệu lệch mã, và hoàn thiện bảng theo dõi. Làm cuối để ghi trạng thái thật của năm gói trước.

## Việc trong gói

| Nhóm | Mục | Việc |
|---|---|---|
| Lệch mã | D8 (sao lưu giữ 15 bản, không phải 14; `SHOPONLINE_BACKUP_KEEP_DAYS` không còn tác dụng) | Ghi vào plan `261116-1520` rằng quyết định đã được plan `261123-0312` thay thế; kiểm `docs/deployment-guide.md:64` |
| Lệch mã | H6 (plan `261116-1354`: 17 cột so với mã 20, ô "đến ngày" mặc định tháng trước, lý do chặn thêm) | Cập nhật chữ trong plan |
| Lệch mã | tax-6 (`docs/robot-runbook.md:124` còn ghi chưa chạy SAP thật; "19 cột" nay là 20) | Sửa runbook theo bằng chứng đã có (đã đọc zrsd003 theo tháng trên production 2026-11-23, việc #61); sửa tiêu chí "19 cột" |
| Lệch mã | robot-5, 6, 7 (plan `261113-1142`: văn bản "ngày không có dữ liệu thành Lỗi" chỉ đúng với zrsd001; dùng `date.today()` so với `today_vn()`; thiếu zrsd003) | Sửa chữ plan: zrsd003 thêm bởi plan `261119-0854` |
| Trạng thái plan | `261113-1230`, `261113-1142` đã sửa; kiểm các plan còn lại | Đổi trạng thái đúng với mã và biên bản chạy thử; plan nào chỉ còn chờ chạy thử production giữ `in-progress` |
| Rủi ro chấp nhận | orders-sap 8, 9, 10, 12; H4, H5, H7, D2 (nháp); D6 nếu không làm; robot-3 | Một mục "Rủi ro đã chấp nhận" trong `docs/` vận hành, mỗi dòng ghi điều kiện và cách xử lý khi gặp |
| Theo dõi | Toàn bộ phát hiện Accept | Thêm cột "Trạng thái" (chưa làm / đang làm / đã sửa / chấp nhận rủi ro / loại vì không tái hiện) vào bảng phát hiện trong [báo cáo tổng hợp](../reports/data-integrity-audit-261123-1410-final.md) |

## Files

- Sửa: plan.md của `261116-1520`, `261116-1354`, `261113-1142`, `261119-0605`; `docs/robot-runbook.md`; `docs/deployment-guide.md`; tài liệu vận hành chứa mục rủi ro chấp nhận; báo cáo tổng hợp
- Đọc trước khi sửa: từng tài liệu và plan (quy tắc quản lý tài liệu của dự án)

## Implementation Steps

1. Đọc từng file đích; kiểm lệch so với mã hiện tại trước khi sửa.
2. Sửa chữ theo bảng; không viết lại phần đúng.
3. Tạo mục "Rủi ro đã chấp nhận" ở nơi tài liệu vận hành sẵn có; không tạo cấu trúc tài liệu mới nếu đã có chỗ phù hợp.
4. Điền cột "Trạng thái" cho mọi phát hiện theo kết quả năm gói trước.
5. Kiểm liên kết và các tuyên bố so với mã và test. Commit.

## Todo

- [x] Sửa các chỗ lệch mã và plan
- [x] Ghi rủi ro chấp nhận vào tài liệu vận hành
- [x] Rà trạng thái các plan
- [x] Điền cột "Trạng thái" cho toàn bộ phát hiện
- [x] Kiểm liên kết, commit

## Success Criteria

- Mọi phát hiện Accept có trạng thái cuối trong bảng theo dõi; không còn dòng "chưa làm" ngoài các mục ngoài phạm vi (đơn nhiều DO, chặn cứng DO đơn hủy).
- Tài liệu chỉ đổi ở chỗ hành vi hoặc sự thật đổi; liên kết không gãy.

## Risk

- **Ghi sai hiện trạng:** đối chiếu từng tuyên bố với mã, test hoặc biên bản trước khi viết.

## Rollback

Revert commit; chỉ là tài liệu.
