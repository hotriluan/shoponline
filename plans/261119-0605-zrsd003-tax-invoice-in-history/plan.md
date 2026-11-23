---
title: "Thêm Tax Invoice Doc. từ zrsd003 vào file Shop Online 2022-2026"
description: "Robot và upload tay đọc zrsd003, lưu số hóa đơn theo DO của sàn; file lịch sử Shop Online có cột 19 Tax Invoice Doc. và chặn đơn chưa có hóa đơn."
status: in-progress
priority: P2
effort: 2d
branch: main
tags: [feature, backend, database, web, robot]
blockedBy: []
blocks: []
created: 2026-11-19
---

# Thêm Tax Invoice Doc. từ zrsd003 vào file Shop Online 2022-2026

## Overview

> **Cập nhật 2026-11-23** (sửa chữ lệch mã, không đổi hợp đồng gốc): file xuất nay có 20 cột (cột 19 `Tax Invoice Doc.`, cột 20 `Tiền Vô` thêm sau), nên tiêu chí 6 "19 cột" là của lúc viết plan. `docs/robot-runbook.md` đã sửa câu "chưa chạy trên SAP thật". Biên bản chạy thử zrsd003 (phase 5) vẫn chưa viết.

Kế toán cần số hóa đơn (Tax Invoice Doc.) cho mỗi dòng trong file lịch sử Shop Online. SAP báo cáo hóa đơn ở ZRSD003; mỗi DO có đúng một hóa đơn (`OD Doc.` = `Delivery` của zrsd004 = `sales_order.do_number`). Kế hoạch thêm bảng lưu hóa đơn của các sàn, bộ nhập zrsd003 dùng chung cho upload tay và robot, job robot đọc ZRSD003, rồi thêm lý do chặn và cột 19 vào file lịch sử.

Nguồn quyết định: [brainstorm-261119-1208-zrsd003-tax-invoice-in-history.md](../reports/brainstorm-261119-1208-zrsd003-tax-invoice-in-history.md). Bản ghi SAP: `docs/sap-recordings/zrsd003/` (gitignore).

## Hợp đồng

- **Kết quả:** admin bấm "Robot đọc zrsd003" (hoặc tải file zrsd003 lên); trang File Shop Online xuất file có cột 19 `Tax Invoice Doc.` sau `Mã đơn`; đơn đã có DO mà chưa có hóa đơn nằm ở **Đơn bị chặn**.
- **Ràng buộc:** job robot chỉ đọc (`writes=False`), tcode `ZRSD003` thêm vào allowlist của guard; một migration `0008_sap_tax_invoice`, sao lưu DB trước khi chạy trên production; chỉ lưu dòng có Bill-to là khách SAP của sàn; file zrsd003 gốc bị xóa ngay sau khi nhập.
- **Ngoài phạm vi:** cột hóa đơn trong file kế toán zrsd004; sửa lại file lịch sử đã xác nhận; hóa đơn khác `ZBA1` (hủy, điều chỉnh); SO tách nhiều DO.

## Quyết định đã chốt (2026-11-19, chủ dự án)

1. Robot đọc ZRSD003 **và** có ô upload tay dự phòng ở trang Báo cáo SAP.
2. Đơn có DO mà chưa có hóa đơn: chặn đơn. Hóa đơn luôn xuất sau DO nên đây là trạng thái chờ bình thường.
3. Cột 19, sau `Mã đơn`; 17 cột gốc và cột 18 giữ nguyên.
4. ZRSD003 không lọc được Bill-to: đọc cả Sales Org 1000, Sales Office 1401 theo Billing Date; bộ nhập lọc Bill-to. Một job cho mọi sàn, khóa theo khoảng ngày.

## Luồng

```
DO có (zrsd004) ──► (sau đó) SAP xuất hóa đơn
        ▼
Trang File Shop Online: đơn chờ hóa đơn bị chặn ──► nút "Robot đọc zrsd003"
        ▼                                            (từ ngày đặt sớm nhất đang chờ → hôm nay)
Robot: ZRSD003, 1000/1401, Billing Date ──► Excel ──► ingest_zrsd003
        ▲                                                ▼
Upload tay ở Báo cáo SAP ───────────────────────► lọc Bill-to sàn, upsert sap_tax_invoice, xóa file gốc
        ▼
collect_rows tra theo do_number ──► đủ thì xuất, cột 19 = Tax Invoice Doc.
```

## Phases

| # | Phase | Trạng thái | Phụ thuộc |
|---|---|---|---|
| 1 | [Bảng hóa đơn và bộ nhập zrsd003](phase-01-tax-invoice-store.md) | completed | — |
| 2 | [Ô upload tay zrsd003](phase-02-manual-upload.md) | completed | 1 |
| 3 | [Job robot đọc ZRSD003](phase-03-robot-read-zrsd003.md) | completed | 1 |
| 4 | [Chặn đơn chờ hóa đơn, cột 19, nút đọc](phase-04-history-file-column.md) | completed | 1, 3 |
| 5 | [Tài liệu và chạy thử production](phase-05-docs-and-live-check.md) | in-progress (tài liệu xong; chờ deploy và chạy thử production) | 2, 3, 4 |
| 6 | [Tải file với các đơn đã đủ dữ liệu](phase-06-download-ready-orders.md) | completed | 4 |

Phase 2 và 3 sửa file khác nhau, làm song song được sau phase 1. Phase 4 dùng hàm xếp job của phase 3.

## Tiêu chí hoàn thành

1. Nhập `docs/zrsd003.XLSX`: giữ 243 dòng có Bill-to `1200001145` (Shopee, 179), `1200001146` (TikTok, 39), `1200001118` (Lazada, 25), bỏ qua 407 dòng khách khác; nhập lại cùng file không đổi số dòng; DO `1910061168` → `7914`.
2. File thiếu `OD Doc.`, `Tax Invoice Doc.`, `Bill-to` hoặc `Billing Date` bị từ chối, không ghi gì.
3. Upload tay và robot cho cùng kết quả (cùng hàm `ingest_zrsd003`); file gốc không còn trong `uploads/` sau khi nhập.
4. Robot điền đúng `P_VKORG`, `P_VKBUR-LOW`, `P_FKDAT-LOW`, `P_FKDAT-HIGH`, xuất từ cột `TAXSR`; test với fake SAP qua.
5. Trang File Shop Online: đơn `DELIVERED` chưa có hóa đơn bị chặn (từ phase 6, đơn bị chặn chỉ bị để lại; file vẫn tải được với các đơn đã đủ dữ liệu) với lý do "DO … chưa có Tax Invoice Doc."; có nút xếp job zrsd003 với khoảng ngày đúng; viewer không xếp được job.
6. File tải về có 19 cột, cột 19 header `Tax Invoice Doc.`, giá trị dạng text đúng theo DO.
7. `uv run pytest` và `uv run ruff check` thoát mã 0.

## Rủi ro chính

- **Enter sau Sales Org/Sales Office:** bản ghi gửi Enter sau hai ô này (màn hình nạp lại). Robot phải làm theo; phase 3 kiểm helper hiện có và test fake SAP.
- **Câu "không có dữ liệu" của ZRSD003 chưa được chụp.** Nếu khác "no data to display", job FAILED chứ không nhập sai; phase 5 ghi lại nếu gặp.
- **Variant mặc định đổi** (Exist/SD): robot không chạm radio; tài liệu robot ghi rõ điều kiện này.
- **SO tách nhiều DO:** chỉ DO đầu được tra; chưa thấy trên production.

## Red Team Review

### Session — 2026-11-23
**Phương pháp:** plan đã làm nên soi mã đối chiếu plan (4 lens của plan, cộng lens bắt buộc "trùng hoặc sót dữ liệu"); người soi tự phân xử, không có reviewer phụ. Số liệu lấy từ dev DB, 2026-11-23 (production không mở được).
**Findings:** 9 (6 accepted, 3 rejected)
**Severity breakdown:** 1 High, 3 Medium, 2 Low (chấp nhận); 3 bị bác

| # | Finding | Severity | Disposition | Hướng xử lý |
|---|---------|----------|-------------|-------------|
| 1 | Cùng một `OD Doc.` có hai dòng ZBA1 trong một file (hủy rồi xuất lại): `kept = {row.delivery: row ...}` giữ dòng **cuối file**, không cảnh báo; đảo thứ tự file thì giữ số khác (tái hiện: `scratchpad/repro_dup_invoice.py`; `report_ingest.py:81`). Cột 19 của file kế toán có thể mang số hóa đơn đã hủy | High (khả năng xảy ra chưa kiểm chứng: mẫu 650 dòng không có DO trùng, `sap_reports.py:162` chỉ nhận ZBA1) | Accept (chủ dự án duyệt 2026-11-23) | Khi một file có DO trùng: giữ dòng `Billing Date` mới nhất (hòa thì `Billing Doc.` lớn hơn) và ghi cảnh báo vào kết quả nhập; `/ak-fix` |
| 2 | Upsert không điều kiện: file upload tay cũ (xuất trước khi hóa đơn bị hủy/xuất lại) ghi đè số mới (`report_ingest.py:93-101` không có `WHERE` so `billing_date`); robot và upload tay dùng chung hàm nên bên chạy sau thắng | Medium | Accept (chủ dự án duyệt 2026-11-23) | Chỉ ghi đè khi `billing_date` mới >= đang lưu; hoặc chấp nhận rủi ro vì cùng nguồn SAP |
| 3 | Một dòng lỗi của **bất kỳ khách nào** (thiếu `Tax Invoice Doc.`, ngày sai) từ chối cả file, kể cả hóa đơn các sàn (`sap_reports.py:165-166,178-179`; lọc Bill-to chỉ làm sau, `report_ingest.py:81`). Việc robot ra FAILED, không sót âm thầm nhưng hóa đơn sàn không vào được. Chỉ an toàn khi variant giữ mặc định "Exist" (runbook ghi, mã không kiểm) | Medium | Accept (chủ dự án duyệt 2026-11-23) | Lọc Bill-to sàn trước khi kiểm lỗi dòng; dòng lỗi của khách khác bỏ qua |
| 4 | SO tách nhiều DO: `mark_delivered` chỉ giữ DO đầu theo thứ tự dòng file zrsd004 (`so_link.py:306,314`); hóa đơn chỉ tra cho DO đó (`sales_history_workbook.py:228`). DO thứ hai không bao giờ được kiểm hóa đơn, đơn được coi đủ khi DO đầu có hóa đơn. Plan ghi ngoài phạm vi nhưng không có cảnh báo | Medium | Accept (chủ dự án duyệt 2026-11-23) | Chạy SQL #2 trên production; nếu có DO dư thì làm plan riêng, nếu không thì ghi chấp nhận rủi ro |
| 5 | Đơn đã có DO nhưng không bao giờ có hóa đơn (trả hàng, hủy sau DO) giữ khoảng đọc zrsd003 lùi mãi (`sales_history.py:105-112`, `min(first_day, *waiting)`) và nằm vĩnh viễn ở "Đơn bị chặn"; mã không có đường gỡ | Low | Accept (chủ dự án duyệt 2026-11-23) | Theo dõi bằng SQL #1; nếu có đơn tồn quá lâu thì thêm cách đánh dấu bỏ qua |
| 6 | Tài liệu lệch mã: `docs/robot-runbook.md:124` còn ghi "Chưa chạy trên SAP thật" trong khi dev DB có hai việc `read_zrsd003` xong ngày 2026-11-19 (việc 47, 48); không có biên bản `live-check-*zrsd003*` (phase 5 chưa xong); tiêu chí 6 ghi 19 cột trong khi file nay có 20 cột (cột Tiền Vô thêm sau) | Low | Accept (chủ dự án duyệt 2026-11-23) | Cập nhật doc và ghi biên bản khi chủ dự án chạy thử production |
| 7 | Hóa đơn của DO không thuộc app (163/255 dòng dev) cũng được lưu vì lọc theo Bill-to chứ không theo DO | Low | Reject (chủ ý: Bill-to là cách lọc duy nhất khi zrsd003 không lọc khách, quyết định 4 của plan; bảng chỉ có mã số, không có tên/mã số thuế; dev DB 2026-11-23: mọi `bill_to` thuộc `platform_setting`) | — |
| 8 | Khoảng đọc chồng nhau tạo hai việc, đọc lại cùng hóa đơn | Medium | Reject (vô hại: khóa chống trùng chỉ chặn việc đang mở cùng khoảng, `queue.py:89-93`; nhập lại idempotent, `report_ingest.py:93-101`; dev DB: việc 48 chồng việc 47 ngày 17-19 cho 0 mới, 56 cập nhật) | — |
| 9 | DO của sàn nhưng hóa đơn lập cho Bill-to khác thì bị bỏ âm thầm | Medium | Reject (không âm thầm: đơn nằm ở "Đơn bị chặn" với lý do thiếu hóa đơn, `sales_history_workbook.py:228-230`; dev DB: 0 cặp đơn/hóa đơn lệch khách) | — |

Lens: Security Adversary (PII trong zrsd003: không phát hiện; chỉ lưu mã Bill-to và số chứng từ, file gốc xóa sau khi nhập, `report_ingest.py:73-75`), Failure Mode Analyst (#1, #2, #3), Assumption Destroyer (#1, #4, #5), Scope & Complexity Critic (không phát hiện thêm), trùng/sót dữ liệu (#1-#5, #8, #9). Chi tiết ở `plans/reports/data-integrity-audit-261123-1320-tax-invoice.md`.

## Validation Log

### Session — 2026-11-23
**Phương pháp:** kiểm từng tiêu chí hoàn thành với mã, test chạy thật, mẫu `docs/zrsd003.XLSX` (chỉ đọc cột và đếm) và dev DB (2026-11-23). Không hỏi chủ dự án; điểm cần quyết ghi ở cuối.

| # | Tiêu chí | Kết quả | Bằng chứng |
|---|----------|---------|------------|
| 1 | Nhập mẫu: 243 dòng sàn (179/39/25), bỏ 407, nhập lại không đổi, DO `1910061168` -> `7914` | VERIFIED | `read_zrsd003` trên mẫu: 650 dòng, Bill-to `…145`=179, `…146`=39, `…118`=25, DO ra `7914`; `tests/importers/test_zrsd003.py` qua; dev DB: việc 48 nhập lại 56 dòng cho 0 mới |
| 2 | File thiếu cột bắt buộc bị từ chối, không ghi gì | VERIFIED | `sap_reports.py:20-27,178-179`; `test_rejects_a_file_without_a_required_column`, `test_ingest_writes_nothing_when_the_file_is_rejected` qua |
| 3 | Upload tay và robot cùng `ingest_zrsd003`; file gốc xóa sau khi nhập | VERIFIED (bằng mã) | `web/routes/sap_reports.py:95,102`, `saprobot/worker.py:146`; việc xóa file là `retention.discard_unused`, chưa quan sát trên máy thật |
| 4 | Robot điền `P_VKORG`, `P_VKBUR-LOW`, `P_FKDAT-LOW/HIGH`, xuất `TAXSR`; test fake SAP qua | VERIFIED | `read_zrsd003.py:20-30`; `tests/saprobot/test_report_reads.py:179` qua |
| 5 | Đơn DELIVERED chưa hóa đơn bị chặn, có nút xếp job, viewer không xếp được | VERIFIED | `sales_history_workbook.py:228-230`; `test_orders_waiting_for_invoices_offer_a_zrsd003_read`, `test_blocked_order_is_left_out_of_the_download` qua; dev DB: 25 đơn DELIVERED chưa có hóa đơn (đặt 2026-11-18/19) |
| 6 | File tải về cột 19 `Tax Invoice Doc.`, text | VERIFIED (lệch chữ: nay 20 cột) | `sales_history_workbook.py:73,301` (`TEXT_COLUMNS = ("R","S")`); `tests/exports/test_sales_history_workbook.py` qua |
| 7 | `uv run pytest` và `ruff check` mã 0 | xem dòng kết quả cuối bảng | `ruff check`: sạch. Nhóm test liên quan (importers, exports, sapjobs, reconcile, saprobot, web) qua 126 test. Lượt chạy cả bộ đầu tiên có 410 lỗi do DB test dùng chung với các tác tử chạy song song (`test_web_flow.py` chạy riêng qua) |

**Giả định:**
- "Mỗi DO có đúng một hóa đơn": UNVERIFIED. Mẫu 650 dòng không có `OD Doc.` trùng, 100% ZBA1, dev DB 0 DO trùng, nhưng mẫu không có cột trạng thái hủy; chưa có dữ liệu production. Xem phát hiện #1.
- "`Billing Type` ZBA1 là hóa đơn thường của mọi đơn sàn": UNVERIFIED trên production; mẫu chỉ có ZBA1 nên bộ lọc chưa từng loại dòng nào.
- "Hóa đơn xuất sau DO nên khoảng đọc từ ngày đặt sớm nhất tới hôm nay đủ": VERIFIED trên dev (0 hóa đơn có `billing_date` trước ngày đặt).
- Phase 5 (deploy, đọc thật, đối chiếu 3 DO với SAP): UNVERIFIED. Không có biên bản live-check; dev DB có hai việc đọc xong 2026-11-19 nhưng không đủ làm bằng chứng đối chiếu.

**Câu hỏi cho chủ dự án:**
1. Khi SAP hủy hóa đơn rồi xuất lại cho cùng DO, báo cáo ZRSD003 (bộ lọc "Exist") có còn dòng ZBA1 của hóa đơn đã hủy không? Cần xác nhận trên SAP thật để quyết phát hiện #1.
2. Có cho sửa nhập zrsd003 theo #1-#3 (giữ hóa đơn mới nhất, không ghi đè bằng file cũ, bỏ qua dòng lỗi của khách khác) bằng `/ak-fix` không?
3. SO tách nhiều DO có xảy ra trên production không (kết quả SQL #2 của file phát hiện)?

### Cập nhật 2026-11-23: chủ dự án trả lời

- Câu hỏi "SAP có liệt kê hóa đơn ZBA1 đã hủy không" **chưa trả lời được**: chủ dự án báo SAP không có tcode ZBA1, nhưng ZBA1 trong file zrsd003 là **loại chứng từ billing** (cột trong báo cáo), không phải tcode. Việc cần kiểm: trong SAP, hóa đơn đã hủy có xuất hiện trong zrsd003 như một dòng riêng không, và có cột trạng thái hủy không. Phát hiện High (DO có hai dòng hóa đơn, dòng cuối thắng) giữ nguyên cho tới khi biết.
- Chủ dự án xác nhận đã chạy zrsd003 theo tháng. Bằng chứng production: việc đọc zrsd003 id 61, tạo 2026-11-23, khoảng 2026-11-01 đến 2026-11-23, trạng thái DONE. Tiêu chí "đọc theo tháng trên production" của `261119-0854` được xem là VERIFIED.
