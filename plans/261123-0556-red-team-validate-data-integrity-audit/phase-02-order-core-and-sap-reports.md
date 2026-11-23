---
phase: 2
title: "Phase 2: Đơn hàng, SO/DO và báo cáo SAP (261111-0755)"
status: completed
priority: P1
effort: 6h
dependencies: [1]
---

# Phase 2: Đơn hàng, SO/DO và báo cáo SAP

## Overview

Red team (đủ 4 lens, vì plan có 9 phase) và validate plan lõi `261111-0755-shopee-excel-to-sap-order-flow` bằng cách soi mã. Phase này phụ trách luồng 1 (đơn hàng) và luồng 2 (SO/DO, báo cáo SAP), cùng phần file kế toán gốc trong phase 4 của plan đó.

## Files

- Đọc plan: `plans/261111-0755-shopee-excel-to-sap-order-flow/plan.md` và mọi `phase-*.md`; các journal ngày 2026-11-11 đến 2026-11-13
- Đọc mã: `src/shoponline/importers/{order_import,shopee_orders,tiktok_orders,lazada_orders,excel_table,sap_reports,sku_mapping_file}.py`, `src/shoponline/domain/{order,states,sku_mapping,expected_value,gi_date}.py`, `src/shoponline/reconcile/{report_ingest,so_link,order_progress}.py`, `src/shoponline/sapjobs/{queue,report_requests}.py`, `src/shoponline/saprobot/transactions/{read_zrsd001,read_zrsd004}.py`, `src/shoponline/exports/{order_workbook,accounting_workbook}.py`, `src/shoponline/web/routes/{imports,batches,orders,sap_reports}.py`, `src/shoponline/db/models.py`
- Đọc test: `tests/importers/test_order_import.py`, `tests/importers/test_platform_readers.py`, `tests/reconcile/test_so_link.py`, `tests/sapjobs/test_queue.py`, `tests/saprobot/test_report_reads.py`, `tests/db/test_constraints.py`, `tests/web/test_web_flow.py`, `tests/web/test_batch_progress.py`
- Sửa: `plans/261111-0755-shopee-excel-to-sap-order-flow/plan.md` (thêm `## Red Team Review`, `## Validation Log`)
- Tạo: `plans/reports/data-integrity-audit-261123-<HHmm>-orders-sap.md`

## Câu hỏi trùng/sót phải trả lời bằng bằng chứng

1. Nhập lại cùng một file, hoặc hai file có ngày chồng nhau: đơn có bị tạo hai lần, bị ghi đè dữ liệu cũ, hay bị bỏ qua mà không báo? Đơn đã đổi trạng thái hoặc bị hủy trên sàn sau lần nhập đầu thì sao?
2. Khóa `order_batch (platform, processing_date)`: một đơn có thể thuộc hai lô không? Đơn nhập ngày D nhưng giao ngày D+1 nằm ở lô nào?
3. Đơn nhiều sản phẩm (dòng sau để trống cột đơn, xem `aad031b`): có dòng nào bị bỏ hoặc bị gộp sai không?
4. SKU chưa có ánh xạ: đơn bị chặn, bị bỏ, hay xuất với mã trống?
5. Một đơn có nhiều SO hoặc nhiều DO; SO tạo tay; zrsd001/zrsd004 trả "No data"; đọc lại cùng khoảng ngày: `sap_so_ref` và liên kết đơn có bị trùng, bị ghi đè, hay bỏ sót DO thứ hai?
6. Hàng đợi `sap_job`: hai việc đọc cùng khoảng chạy song song, hoặc việc chết giữa chừng rồi chạy lại, có ghi kết quả hai lần không?

## Implementation Steps

1. Đọc plan, journal và mã theo danh sách. Lập bảng "tiêu chí hoàn thành ↔ bằng chứng" (mã, test, hoặc trạng thái production).
2. Red team: tạo 4 reviewer `code-reviewer` theo `red-team-personas.md`, cộng lens trùng/sót trong [plan.md](./plan.md). Đưa cho mỗi reviewer đường dẫn plan, danh sách file mã và test ở trên, và 6 câu hỏi trên. Mỗi phát hiện phải có trích `file:dòng` trong mã.
3. Gom phát hiện, bỏ trùng, tối đa 15, rồi phân xử Accept hoặc Reject có lý do. Phát hiện nào cần chứng minh thì viết test tái hiện trong scratchpad hoặc nhánh tạm, chạy `uv run pytest <file>`, và ghi kết quả. Không commit test đó.
4. Với giả thuyết cần dữ liệu thật, viết câu SQL chỉ đọc và chuyển cho phase 7 (ghi vào file phát hiện, mục "SQL cần chạy"). Nếu phase 1 đã xong, chạy luôn và ghi số đếm.
5. Hỏi chủ dự án qua cổng red team (Áp dụng hết / Xem từng cái / Bác hết), sau đó ghi `## Red Team Review` vào plan gốc.
6. Validate: với mỗi tiêu chí hoàn thành và mỗi "Giả định đang dùng" trong plan gốc, ghi VERIFIED, FAILED hoặc UNVERIFIED kèm bằng chứng. Chỉ hỏi chủ dự án về FAILED và quyết định còn mở (tối đa 8 câu, mỗi lượt 4 câu). Ghi `## Validation Log`.
7. Ghi file phát hiện: bảng phát hiện (mức độ, luồng, bằng chứng, đề xuất), danh sách SQL, kết quả test tái hiện.

## Todo

- [x] Bảng tiêu chí ↔ bằng chứng
- [x] Red team 4 lens + lens trùng/sót, phân xử
- [x] Test tái hiện cho phát hiện High trở lên (nếu tái hiện được)
- [x] Cổng duyệt red team với chủ dự án, ghi vào plan gốc
- [x] Validate và ghi Validation Log
- [x] File phát hiện

## Success Criteria

- Plan gốc có hai mục mới. Mọi phát hiện Accept có trích `file:dòng`.
- 6 câu hỏi trùng/sót đều có câu trả lời: "an toàn vì …", "lỗi …", hoặc "cần dữ liệu, xem SQL #n".
- `git status` không có thay đổi trong `src/`, `tests/`, `migrations/`.
