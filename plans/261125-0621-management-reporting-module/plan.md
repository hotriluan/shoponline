---
title: "Module báo cáo cho quản lý: giữ dữ liệu khách, tiền về Lazada, shop, lịch sử 2022–2026, trang báo cáo"
description: "Quản lý xem xu hướng bán hàng từ 2022 theo tháng, sàn, shop, sản phẩm, tỉnh, với ba đường doanh thu từ 11/2026, ngay trong web hiện có."
status: completed
priority: P1
effort: 44h
branch: main
tags: [feature, backend, database, web, reporting]
blockedBy: []
blocks: []
created: 2026-11-25
---

# Module báo cáo cho quản lý

## Overview

Quản lý mở trang **Báo cáo** để xem doanh số từ 2022 tới nay theo tháng, sàn, shop, sản phẩm và tỉnh. Từ 11/11/2026, trang có thêm ba đường giá trị trên sàn, doanh thu hóa đơn và tiền thực nhận, cùng phí sàn và trả hàng. Mọi bảng tải được ra Excel. Để có đủ dữ liệu, kế hoạch này còn bỏ việc xóa dữ liệu khách, cho nhập tay tiền về Lazada, ghi shop cho từng đơn và nạp file lịch sử của kế toán.

Nguồn quyết định: [brainstorm-261125-1309-management-reporting-module.md](../reports/brainstorm-261125-1309-management-reporting-module.md). Phần **tự nhận shop** trong báo cáo đó đã bị chủ dự án bỏ: admin chọn shop khi tải file.

## Hợp đồng

- **Ràng buộc:** không ghi gì vào SAP; dùng tài khoản admin/viewer hiện có (viewer xem báo cáo, chỉ admin nhập liệu); thư viện biểu đồ chép vào `static/`; sao lưu `db` trước mỗi migration và trước khi nạp lịch sử trên máy chạy thật.
- **Không làm:** tự nhận shop, dự báo, API sàn, báo cáo kho, bảng kê chi phí sàn theo mẫu kế toán, sửa file lịch sử gốc, Power BI.
- **Mốc ranh giới duy nhất `REPORTING_CUTOVER = 2026-11-11 00:00`:** trước mốc lấy từ file lịch sử (kỳ ≤ 10/2026, cộng các dòng kỳ 11/2026 có ngày đặt trước 11/11); từ mốc trở đi lấy từ dữ liệu hệ thống. Đơn sớm nhất trong cả `shoponline` và `shoponline_dev` đặt lúc 2026-11-11 10:32, nên mốc này tương đương với "hệ thống từ 01/11" đã chốt và không có đơn nào bị tính hai lần. <!-- Updated: Validation Session 2 - đã kiểm trên production --> **Đã kiểm trên máy chạy thật ngày 2026-11-25** (truy vấn chỉ đọc qua SSH): 181 đơn (Shopee 131, TikTok 31, Lazada 19), sớm nhất 2026-11-11 10:32, muộn nhất 2026-11-25; không có đơn nào trước mốc.
- **Ba đường doanh thu, cùng tính theo kỳ của ngày đặt đơn:** giá trị trên sàn = (giá − trợ giá) × số lượng; doanh thu hóa đơn = `net_value_vnd + tax_vnd`; tiền thực nhận = tổng `platform_settlement.amount`. Hai chênh lệch suy ra: trợ giá/chênh giá và phí sàn. Lịch sử chỉ có đường thứ nhất.
- **Khác brainstorm:** các view báo cáo nằm trong schema `public` (tên `report_*`), không nằm trong schema `reporting` riêng. Lệnh phục hồi chạy `DROP SCHEMA public CASCADE` ([restore.py:226](../../src/shoponline/backup/restore.py)), nên view ở schema khác sẽ bị xóa theo mà không báo lỗi và không được dump lại.

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Giữ dữ liệu khách vĩnh viễn](./phase-01-keep-customer-data.md) | Completed |
| 2 | [Nhập tay tiền về Lazada](./phase-02-lazada-manual-settlement.md) | Completed |
| 3 | [Danh mục shop, đơn mang shop](./phase-03-shop-catalog.md) | Completed |
| 4 | [Nạp file lịch sử 2022–2026](./phase-04-history-import.md) | Completed (cổng B đã chạy trên database dev) |
| 5 | [View báo cáo và lớp truy vấn](./phase-05-reporting-views.md) | Completed |
| 6 | [Trang báo cáo và xuất Excel](./phase-06-reports-pages.md) | Completed |
| 7 | [Tài liệu và nghiệm thu](./phase-07-docs-and-acceptance.md) | Completed |

**Phụ thuộc:** phase 1, 2 và 3 độc lập với nhau. Phase 4 cần phase 3 (Division quy về shop). Phase 5 cần phase 2, 3 và 4. Phase 6 cần phase 5. Phase 7 làm sau cùng.

**Thứ tự migration:** `0013` tiền về nhập tay → `0014` shop → `0015` lịch sử, quy đổi tỉnh, `customer_info.province` → `0016` view báo cáo.

## Tiến độ và bàn giao cho phiên sau (cập nhật 2026-11-25)

**Cách làm đã chốt với chủ dự án: ba cổng duyệt.** Cổng A = phase 3; cổng B = phase 4 (nạp lịch sử, phải chạy thử trên file thật và đối chiếu tổng theo năm/Division trước khi `--apply`, chạy `--apply` hai lần để chứng minh không trùng); cổng C = phase 5, 6, 7 (chủ dự án xem ảnh chụp từng trang báo cáo). Không dùng subagent (các phase chung `models.py`, `app.py`, `_nav.html`, helper test). Không deploy lên máy chạy thật; các bước deploy ở phase 7 là việc của chủ dự án.

**Đã xong:** phase 1, phase 2 (đã nghiệm thu bằng test), phase 3 và phase 4 (code và test xong; xem "Kết quả" cuối từng file phase).

**Việc còn mở trước khi sang cổng B:**
- Cổng A chờ chủ dự án duyệt. Chưa chạy `alembic upgrade head` trên database dev (cần đọc `.env`, hook bảo mật chặn; chủ dự án tự chạy hoặc đồng ý một lần đọc). Sao lưu trước, rồi `SELECT shop_code, count(*) FROM sales_order GROUP BY shop_code;` (mọi đơn có shop; Shopee đều `SHOPEE_BD`).
- Chạy lại toàn bộ `uv run pytest` một lần cuối (lần chạy đầy đủ gần nhất chỉ lỗi 8 test upload thiếu shop, đã sửa; mới chạy lại riêng `tests/web`: 232 đạt).
- Máy chạy thật sau deploy: chạy lại `register-tasks.ps1` (phase 1).

**Phase kế tiếp:** phase 4 (migration kế tiếp là `0015_history_sales`; head hiện tại là `0014_shop`). Phase 5 dùng `0016_report_views`.

**Lưu ý kỹ thuật rút ra:**
- Không chạy hai lần `pytest` cùng lúc: dùng chung database `*_test`, các test sao lưu/phục hồi `DROP SCHEMA public` nên làm hỏng lần chạy kia. Toàn bộ test mất khoảng 3 đến 5 phút; chạy ở nền, ghi ra file.
- Không chạy `ruff format` trên cả repo (nó sửa cả migration cũ như `0009`). Chỉ format file mới của mình; kiểm bằng `uv run ruff check`.
- Test sao lưu giờ dùng `tests/conftest.py::HEAD_REVISION` thay vì ghi cứng tên migration, nên thêm migration không làm chúng hỏng nữa.
- Mọi chỗ tạo `SalesOrder` trong test phải có `shop_code` (dùng `tests/shop_codes.py::SHOP`, hoặc `sales_history_setup.order`). Test POST `/imports` phải gửi `shop_code`. Phase 4 và 5 sẽ thêm bảng mới: nếu test dùng fixture `committed` (`tests/accounting/conftest.py`) cần thêm bảng đó vào danh sách xóa.
- `.env` bị hook bảo mật chặn đọc; không tìm cách đọc nó qua lệnh khác.
- Trong Bash của Windows, heredoc chứa nhiều dấu nháy hoặc `	` dễ hỏng: tạo file dài bằng công cụ Write, và sửa file có tiếng Việt bằng Python dùng `encoding='utf-8'`.

**Cập nhật 2026-11-25 (cuối):** cả bảy phase xong và nghiệm thu trên database dev (đồng bộ từ máy chạy thật); xem [acceptance-report.md](./reports/acceptance-report.md). Việc còn lại là deploy lên máy chạy thật, theo mục "Báo cáo quản lý: việc một lần khi bật" trong `docs/deployment-guide.md`.

## Success Criteria

- [x] `shoponline retention --apply` không xóa dòng `customer_info` nào; các quy tắc xóa file vẫn như cũ.
- [x] Nhập tiền cho một đơn Lazada thì đơn đó có số ở cột "Tiền Vô" và ở đường tiền thực nhận.
- [x] Mỗi đơn mới mang đúng shop admin đã chọn; file lịch sử Shop Online ghi Division theo shop.
- [x] Nạp lịch sử xong thì tổng `Customer paid` theo năm và theo Division khớp file gốc, trừ đúng các dòng bị loại đã liệt kê; nạp lại cùng file không sinh dòng trùng.
- [x] Ba đường doanh thu của một tháng mẫu khớp truy vấn tay trên `sales_order_item`, `sap_tax_invoice`, `platform_settlement`.
- [x] Trang `/reports` mở được cho viewer; mỗi bảng tải được Excel; tháng 11/2026 ghi rõ thiếu dữ liệu 01–10/11 khi chưa nạp phần đó.
- [x] `uv run pytest` và `uv run ruff check` sạch.

## Rủi ro

- Giữ tên và địa chỉ khách vô thời hạn là thay đổi chính sách dữ liệu cá nhân (Nghị định 13/2023). Đây là quyết định của chủ dự án; phase 1 ghi lý do và ngày chốt vào tài liệu.
- Quy đổi `billingCity` cũ về 34 tỉnh mới không trọn vẹn với tên huyện; các dòng không quy đổi được hiện là "Chưa xác định" cho tới khi admin khai tên.

## Validation Log

### Session 1 — 2026-11-25
**Trigger:** `/ak-plan validate` trước khi cook.
**Questions asked:** 4

#### Questions & Answers

1. **[Architecture]** Hằng `SETTLED_PLATFORMS` dùng cho cả tra tiền lẫn chặn, và `order_progress.py` cũng dùng nó. Xử lý thế nào?
   - Options: Tách hằng làm hai (Recommended) | Lazada cũng bị chặn khi thiếu tiền | Chỉ sửa file lịch sử, order_progress giữ nguyên
   - **Answer:** Tách hằng làm hai
   - **Rationale:** file kế toán không được phụ thuộc việc nhập tay, nhưng chip "tiền về" phải hiện số đã nhập.
2. **[Assumptions]** Các đơn hiện có (62 đơn, sớm nhất 11/11/2026) có đơn nào thuộc shop khác shop đang bán không?
   - Options: Không, tất cả thuộc shop đang bán (Recommended) | Có, phải gán tay một số đơn
   - **Answer:** Không chọn. Chủ dự án chỉ ra rằng các số liệu này đọc từ database dev; phải đọc production.
   - **Custom input:** "hiện tại bạn đang đọc database tại máy phát triển để đưa ra kết luận, bạn hãy đọc database trực tiếp trên production mới có được dữ liệu chính xác nhé"
   - **Rationale:** production nằm ở máy khác, thông tin kết nối ở `.env` không đọc được từ phiên này; các số liệu thành điều kiện kiểm trước khi cook (xem Action Items).
3. **[Risk]** `history-import --apply` chặn khi không có bản sao lưu `db` trong 2 giờ: chặn ở đâu?
   - Options: Chặn mọi máy, có cờ bỏ qua cho dev (Recommended) | Chỉ chặn khi cấu hình đánh dấu máy chạy thật | Không chặn, chỉ in nhắc
   - **Answer:** Chặn mọi máy, có cờ bỏ qua cho dev
4. **[Scope]** `returned_value` tính những phiếu nào?
   - Options: Mọi phiếu ISSUED, cả CANCEL và RETURN (Recommended) | Chỉ ISSUED có reason_kind = RETURN
   - **Answer:** Mọi phiếu ISSUED, cả CANCEL và RETURN

#### Confirmed Decisions
- Hai hằng: `SETTLEMENT_LOOKUP_PLATFORMS` (có Lazada) và `SETTLEMENT_REQUIRED_PLATFORMS` (Shopee, TikTok).
- Cờ `--skip-backup-check` cho `history-import --apply`, ghi vào `event_log`.
- `returned_value` dùng `status = 'ISSUED'`, mọi `reason_kind`.

#### Action Items
- [x] **Trước khi cook phase 1, 3, 4:** chạy chỉ đọc trên production và dán kết quả cho phiên sau:
  - `SELECT platform, count(*), min(ordered_at), max(ordered_at) FROM sales_order GROUP BY platform;`
  - `SELECT count(*) FROM customer_info;`
  - `SELECT count(*) FROM event_log WHERE kind LIKE 'retention%';`
  - Kỳ vọng: `min(ordered_at) ≥ 2026-11-11 00:00`, không có dòng `retention_*`, mọi đơn thuộc shop đang bán. Lệch thì sửa `REPORTING_CUTOVER`, phase 1 hoặc cách backfill ở phase 3.

#### Impact on Phases
- Phase 1: bối cảnh ghi rõ chưa kiểm trên production.
- Phase 2: tách hằng, thêm `order_progress.py` và test vào danh sách file, sửa Risk.
- Phase 3: backfill chưa kiểm trên production, thêm truy vấn kiểm.
- Phase 4: chặn sao lưu ở mọi máy, cờ `--skip-backup-check`.
- Phase 5: `returned_value` theo `ISSUED`.
- Phase 7: bước 0 kiểm production trước deploy.

### Verification Results
- **Tier:** Full (7 phase)
- **Claims checked:** 41
- **Verified:** 36 | **Failed:** 3 | **Unverified:** 2

#### Failures
1. [Contract Verifier] Phase 2: `SETTLED_PLATFORMS` có 8 chỗ dùng trong 2 file (`sales_history_workbook.py` ×5, `order_progress.py` ×3); kế hoạch chỉ nêu file đầu. Đã sửa theo câu 1.
2. [Fact Checker] Phase 5: "status khác hủy" không tồn tại; `sales_return.status` là `ISSUED`/`VOID` ([models.py:484](../../src/shoponline/db/models.py)). Đã sửa theo câu 4.
3. [Fact Checker] Phase 2 Risk: nói `ingest_settlement` "có thể xóa"; thực tế chỉ upsert ([report_ingest.py:167](../../src/shoponline/reconcile/report_ingest.py)). Đã sửa lại thành test giữ điều đó.

#### Unverified
1. Phase 1 và `plan.md`: "62 đơn", "chưa từng xóa dữ liệu khách" và "đơn sớm nhất 2026-11-11 10:32" chỉ kiểm được trên máy phát triển. Cần truy vấn production (Action Items).
2. Phase 3: "mọi đơn hiện có thuộc shop đang bán", cùng nguyên nhân.

Đã kiểm đúng, đáng nói: file lịch sử có 3.006 dòng, 19 cột, 8 cách viết Division và 328 giá trị `billingCity` kể cả ô trống (kế hoạch ghi 327 giá trị); `import_batch.kind` không có CHECK nên `history_sales` thêm được; restore chỉ `DROP SCHEMA public` ([restore.py:226](../../src/shoponline/backup/restore.py)) và giữ `ops`; `SalesOrder` chỉ được tạo ở [order_import.py:161](../../src/shoponline/importers/order_import.py), `import_orders` có 1 nơi gọi trong `src` (`imports.py:59`) và 25 trong test.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01 đến phase-07
- Decision deltas checked: 4
- Reconciled stale references: 3 (phase 2 danh sách file và task, phase 7 bước deploy, phase 5 điều kiện phiếu trả)
- Unresolved contradictions: 0. Còn 2 điều kiện chờ số liệu production, không phải mâu thuẫn trong kế hoạch.

### Session 2 — 2026-11-25
**Trigger:** chủ dự án yêu cầu kiểm chứng trực tiếp trên production qua SSH (`prod-win10`, `C:\shoponline`); chỉ chạy truy vấn đọc (`SET TRANSACTION READ ONLY`), không ghi gì.
**Questions asked:** 0

#### Kết quả
- Database `shoponline`, phiên bản migration `0012_sales_return`, nên `0013` là migration kế tiếp.
- `sales_order`: 181 đơn (Shopee 131, TikTok 31, Lazada 19), sớm nhất 2026-11-11 10:32, muộn nhất 2026-11-25. Trạng thái: DELIVERED 155, READY 24, CANCELLED 2. Mốc `REPORTING_CUTOVER` đúng.
- `customer_info`: 181 dòng, không dòng mồ côi. `event_log` có 7 dòng `retention_files` và không có `retention_purge`: chưa từng xóa dữ liệu khách. Tác vụ retention không có `--apply`.
- **Sai lệch so với kế hoạch:** kế hoạch ghi 62 đơn (số của máy dev); thực tế 181. Phase 1 đã sửa.
- 23 đơn chưa có tên khách (Shopee 16, TikTok 7). Không liên quan đến retention. Ảnh hưởng: file Shop Online chặn các đơn này vì "Thiếu tên khách" cho đến khi admin bổ sung; không đổi kế hoạch.

#### Action Items
- [x] Chủ dự án xác nhận 131 đơn Shopee hiện có đều thuộc `Shopee Bình Dương` (Session 3, 2026-11-25).

### Whole-Plan Consistency Sweep (Session 2)
- Files reread: plan.md, phase-01, phase-03, phase-07
- Decision deltas checked: 1 (số đơn production)
- Reconciled stale references: 2 (phase 1 bối cảnh, plan.md mốc)
- Unresolved contradictions: 0. Còn 1 xác nhận của chủ dự án về shop của đơn Shopee.

### Session 3 — 2026-11-25
**Trigger:** xác nhận câu hỏi còn lại của Session 2.
**Questions asked:** 1

1. **[Assumptions]** 131 đơn Shopee hiện có đều thuộc Shopee Bình Dương phải không?
   - **Answer:** Đúng.
   - **Rationale:** backfill `sales_order.shop_code` ở migration `0014` dùng shop đang bán của sàn.

#### Impact on Phases
- Phase 3: bỏ điều kiện chờ xác nhận, thêm bước đếm đơn theo `shop_code` sau migration.

### Whole-Plan Consistency Sweep (Session 3)
- Decision deltas checked: 1
- Unresolved contradictions: 0. Không còn điều kiện chờ số liệu.
