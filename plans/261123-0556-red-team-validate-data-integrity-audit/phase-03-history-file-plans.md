---
phase: 3
title: "Phase 3: File lịch sử và file nháp (261116-1354, 261119-0828)"
status: completed
priority: P1
effort: 4h
dependencies: [1]
---

# Phase 3: File lịch sử và file nháp

## Overview

Red team hai plan về file `Shop Online 2022-2026` bằng cách soi mã: `261116-1354-shop-online-history-export` (5 phase, 3 lens; đã có validation log nên chỉ cần red team) và `261119-0828-draft-history-file` (2 phase, 2 lens; cần cả validate). Phase này phụ trách luồng 4 (file lịch sử).

## Files

- Đọc plan: hai thư mục plan trên; `plans/reports/brainstorm-261116-1319-shop-online-history-export.md`, `brainstorm-261119-1340-history-export-ready-orders.md`, `live-check-261116-1444-shop-online-history-export.md`; các journal ngày 2026-11-16 và 2026-11-19 về file Shop Online
- Đọc mã: `src/shoponline/exports/sales_history_workbook.py`, `src/shoponline/web/routes/sales_history.py`, `src/shoponline/domain/report_names.py`, `src/shoponline/web/templates/sales_history.html`, các model `SalesHistoryFileOrder`, `SalesHistoryExported`, `GeneratedFile` trong `src/shoponline/db/models.py`, `migrations/versions/0007_sales_history.py`
- Đọc test: `tests/exports/test_sales_history_workbook.py`, `tests/web/test_sales_history_routes.py`, `tests/sales_history_setup.py`, `tests/domain/test_report_names.py`
- Sửa: `plan.md` của hai plan (thêm `## Red Team Review`; `261119-0828` thêm cả `## Validation Log`)
- Tạo: `plans/reports/data-integrity-audit-261123-<HHmm>-history-file.md`

## Câu hỏi trùng/sót phải trả lời bằng bằng chứng

1. Một đơn được đánh dấu đã xuất (`sales_history_exported`) ở thời điểm nào: lúc tải file hay lúc xác nhận? Nếu tải file mà không xác nhận, rồi tải lại, thì đơn có xuất hiện ở hai file không? Nếu xác nhận nhầm file cũ thì sao?
2. Xóa file đã tải (`59c361a`): các đơn trong file đó có trở lại hàng chờ không, hay bị coi là đã xuất mãi mãi?
3. Đơn có nhiều DO hoặc nhiều dòng sản phẩm: số dòng xuất ra có khớp với số dòng sản phẩm, không thừa và không thiếu?
4. Đơn bị chặn (chờ hóa đơn, chờ tiền vô, thiếu tên báo cáo, thiếu tỉnh): có điều kiện nào làm đơn bị chặn mãi mà không ai thấy không? Đơn tồn từ tháng trước có được gom vào tháng sau không?
5. File nháp (`261119-0828`): tải file nháp có vô tình đánh dấu đơn đã xuất không? Dòng nháp có bị dán nhầm thành dòng thật không (có dấu phân biệt không)?
6. Ranh giới tháng và múi giờ: đơn đặt 23:30 ngày cuối tháng (giờ Việt Nam) rơi vào tháng nào? Sắp xếp theo `createTime` có làm mất dòng nào không?

## Implementation Steps

1. Đọc plan, báo cáo, journal và mã; lập bảng tiêu chí ↔ bằng chứng cho cả hai plan.
2. Red team `261116-1354` với 3 lens (Security, Assumption, Failure) cộng lens trùng/sót; red team `261119-0828` với 2 lens cộng lens trùng/sót. Có thể dùng chung một lượt reviewer cho cả hai plan vì chúng cùng mã, nhưng phát hiện phải ghi rõ thuộc plan nào.
3. Phân xử, viết test tái hiện cho phát hiện High trở lên (scratchpad hoặc nhánh tạm), và viết SQL cho câu hỏi cần dữ liệu thật. Ví dụ: đơn có trong hai `generated_file` đã xác nhận; đơn trạng thái "Đã có DO" mà quá 60 ngày vẫn chưa xuất.
4. Cổng duyệt red team với chủ dự án, ghi `## Red Team Review` vào từng plan.
5. Validate `261119-0828`: đối chiếu tiêu chí với mã và test, chỉ hỏi FAILED hoặc quyết định còn mở; ghi `## Validation Log`. Với `261116-1354`, chỉ kiểm lại các tiêu chí mà validation log cũ đánh dấu chưa xác minh.
6. Ghi file phát hiện.

## Todo

- [x] Bảng tiêu chí ↔ bằng chứng (2 plan)
- [x] Red team và phân xử
- [x] Test tái hiện và SQL
- [x] Cổng duyệt, ghi Red Team Review
- [x] Validate `261119-0828`
- [x] File phát hiện

## Success Criteria

- 6 câu hỏi đều có câu trả lời kèm bằng chứng.
- Hai plan có các mục mới; không có thay đổi mã.
