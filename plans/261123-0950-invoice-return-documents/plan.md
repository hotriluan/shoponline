---
title: "Trả hàng sau hóa đơn: tự lập Biên bản điều chỉnh hóa đơn và REQUEST to RETURN GOODS"
description: "Lập phiếu trả hàng cho đơn đã có hóa đơn, cấp số biên bản, sinh file Word và Excel từ database, zrsd003 và master tên trên hóa đơn (nạp từ PDF Bkav)."
status: completed
priority: P1
effort: 3d
branch: main
tags: [feature, backend, database, frontend]
blockedBy: []
blocks: []
created: 2026-11-23
---

# Trả hàng sau hóa đơn

## Overview

Lập phiếu trả hàng cho đơn đã có hóa đơn, cấp số biên bản, sinh file Word và Excel từ database, zrsd003 và master tên trên hóa đơn (nạp từ PDF Bkav). Khi khách hủy hoặc trả một đơn `DELIVERED` đã có hóa đơn, admin lập phiếu trả hàng trên web. Hệ thống cấp số `NNN/MM.YYYY`, chụp lại dữ liệu hóa đơn và người mua, rồi sinh Biên bản điều chỉnh hóa đơn (`.docx`) và REQUEST to RETURN GOODS (`.xlsx`) để in. Tên hàng, ĐVT trên hóa đơn lấy từ master; vật tư chưa có thì yêu cầu tải PDF hóa đơn của đơn để đọc và ghi vào master.

Thiết kế, bằng chứng và các quyết định của người dùng: [brainstorm report](../reports/brainstorm-261123-1630-invoice-return-documents.md). Mẫu gốc: `docs/bbdchd/` (chứa dữ liệu khách thật, không commit).

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Mẫu biểu và thư viện](./phase-01-start.md) | Completed |
| 2 | [Dữ liệu và tiền zrsd003](./phase-02-data-model-and-zrsd003-amounts.md) | Completed |
| 3 | [Đọc PDF hóa đơn và master tên trên hóa đơn](./phase-03-invoice-pdf-reader-and-master.md) | Completed |
| 4 | [Tính tiền, cấp số, phát hành và sinh file](./phase-04-return-calculation-and-documents.md) | Completed |
| 5 | [Luồng web lập phiếu trả hàng](./phase-05-web-return-flow.md) | Completed |
| 6 | [Tài liệu và nghiệm thu](./phase-06-docs-and-acceptance.md) | Completed |

Thứ tự: 1 → 2 → 3 → 4 → 5 → 6. Phase 3 dùng hàm tính tiền dòng của phase 4 (`returns/amounts.py`), nên hàm đó được viết ngay ở đầu phase 3.

## Quyết định đã chốt

- Số `NNN/MM.YYYY ALK-KH.STMĐT`: `NNN` reset mỗi năm, chỉ hệ thống cấp, số bắt đầu nhập một lần bằng lệnh CLI khi triển khai; số đã cấp không dùng lại.
- Trả cả đơn hoặc một phần; mỗi đơn tối đa một phiếu chưa hủy.
- Lý do: "hủy đơn hàng" hoặc "trả lại hàng".
- Bản chụp người mua và file phiếu giữ lâu dài, ngoài quy tắc 90 ngày.
- Word: ngày, tháng ở dòng "Hôm nay" để trống; Excel: `No`, `Date` để trống.
- Biên bản Word: tên hàng, ĐVT trên hóa đơn từ master `invoice_item_text` (nạp từ PDF hóa đơn).
- REQUEST to RETURN GOODS: ô `D14` (và các dòng hàng sau) dùng **tên SAP** (`sales_order_item.sap_name`, ví dụ `V-09 REDDISH CLAY 2004 VN-0.8L`), không dùng master.
- Hai file xuất ra giống mẫu trong `docs/bbdchd/` về bố cục và định dạng (font, cỡ chữ, in đậm, căn lề, viền, gộp ô, độ rộng cột, chiều cao dòng, khổ giấy, lề in). Chỉ khác: nội dung trường động, chữ trường động màu đen, Excel là `.xlsx` chỉ có sheet `RRG ENGLISH` và không có logo (người dùng xác nhận không cần).

- Chỉ đơn `DELIVERED` có DO và hóa đơn mới lập được phiếu; đơn hủy trước khi có DO thì không có hóa đơn (người dùng xác nhận), nên không thuộc phạm vi.
- Đơn kit: Bkav in dòng cha, nên chỉ dòng chính (`is_main_line`) tham gia ghép PDF, chia tiền và hai file; dòng con bị bỏ qua.
- File phiếu (chứa tên, địa chỉ người mua) chỉ admin tải được.
- Ký hiệu hóa đơn suy ra từ mẫu cấu hình `SHOPONLINE_INVOICE_SYMBOL_PATTERN` (mặc định `1C{yy}TAL`) và `billing_date`.
- PDF không ghi đè tên master đã có khi khác tên, trừ khi admin xác nhận.

## Ngoài phạm vi

Hóa đơn điều chỉnh trên Bkav, chứng từ trong SAP, xuất PDF hay in tự động, sửa file kế toán hoặc file lịch sử Shop Online, đổi trạng thái đơn, nạp master hàng loạt, lưu PDF hóa đơn tải lên, logo và các sheet khác của file Excel mẫu, đơn đã hủy trước khi có DO.

## Success Criteria

- [x] Hai đơn mẫu (`261115BUCPCSEN`, `534218339824472`) sinh file khớp mọi trường đỏ của mẫu; Word khớp PDF hóa đơn (tên `SƠN V-09 REDDISH CLAY 2004 VN`, ĐVT `LON 0.8 LT`, số `00008038`/`00008020`, `1C26TAL`, `17/11/2026`, 111.111 / 8.889 / 120.000, dòng điều chỉnh âm); Excel `D14` là `V-09 REDDISH CLAY 2004 VN-0.8L`.
- [x] Kiểm tra định dạng tự động: file sinh ra và mẫu có cùng định dạng ở mọi đoạn, ô, dòng, cột, vùng gộp, và thiết lập trang (Excel không có hình); chỉ khác văn bản và màu chữ của trường động. Xem trước bản in đặt cạnh mẫu, không thấy khác biệt.
- [x] Master rỗng thì chặn tới khi tải PDF; PDF sai đơn bị từ chối; đơn sau cùng vật tư không cần PDF.
- [x] Trả cả đơn khớp đúng `Net Value (VND)`, `Tax (VND)` của zrsd003; trả một phần chỉ có dòng trả.
- [x] Đơn nhiều dòng có đủ dòng ở cả hai file.
- [x] Một phiếu chưa hủy mỗi đơn; số không trùng khi phát hành đồng thời; đầu năm về `001`; chặn khi chưa nhập số bắt đầu.
- [x] Retention không xóa phiếu và file phiếu (kể cả khi mã bị revert); sao lưu `db` hằng ngày chứa file phiếu; viewer không tải được file phiếu.
- [x] Mẫu đưa vào repo công khai không chứa dữ liệu khách ở bất kỳ phần nào của file zip; `.gitignore` commit trước mẫu.
- [x] Tên và địa chỉ người mua chứa `& < >` hoặc `=` không làm hỏng hay chèn nội dung vào file sinh ra.
- [x] Đơn kit có dòng con chỉ lập trên dòng cha, khớp hóa đơn.
- [x] `uv run pytest` và `uv run ruff check` đạt.

## Validation Log

### Session 1 — 2026-11-23

Kiểm chứng trên mã: `save_generated` có ở `web/uploads.py`; `parse_money` ở `importers/excel_table.py`; `read_table` chỉ hỗ trợ cột bắt buộc (phase 2 đã ghi cách kiểm `table.columns`); `accounting/runs.py` xóa file khi chốt lỗi (mẫu cho phase 4); `ak plan validate` đạt. Failed: 0.

| Câu hỏi | Trả lời | Ảnh hưởng |
|---|---|---|
| Màu trường động trong file sinh ra | Chữ đen | Phase 1 bước 3 (đã có) |
| Excel `.xlsx` thay `.xls` | Đồng ý | Phase 1 bước 4 (đã có) |
| Câu chữ lý do trả hàng | Theo đề xuất | Phase 1 bước 3 (đã ghi câu chữ) |
| Trả một phần: "trước điều chỉnh" | Toàn bộ hóa đơn | Phase 4 bước 5 (đã có) |

### Session 2 — 2026-11-23 (người dùng sửa yêu cầu)

| Thay đổi | Quyết định | Ảnh hưởng |
|---|---|---|
| Ô `D14` Excel | Dùng tên SAP; Word vẫn dùng master | Phase 2 (cột `sap_name` ở dòng phiếu), phase 4 bước 6, phase 6 |
| File xuất giống 100% mẫu | Giống bố cục và định dạng; vẫn `.xlsx`, vẫn chữ đen | Phase 1 (dựng mẫu bằng cách sửa tại chỗ, kiểm tra định dạng tự động), phase 4 (test định dạng), phase 6 |

Đã cân nhắc và không chọn: điền chính file `.xls` bằng Excel COM (giống tuyệt đối nhưng buộc máy chạy web cài Excel, chạy nền dễ treo).

## Red Team Review

### Session — 2026-11-25

**Findings:** 15 (14 accepted and applied, 1 rejected by user decision: finding 12)
**Severity breakdown:** 2 Critical, 12 High, 1 Medium

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | Mẫu từ hồ sơ khách thật vào repo công khai; kiểm tra yếu | Critical | Accept | Phase 1, 6 |
| 2 | Dòng con kit làm sai ghép dòng, tiền, tên SAP | Critical | Accept (người dùng: Bkav in dòng cha, chỉ dùng dòng chính) | Phase 3, 4, plan.md |
| 3 | Độ bền: revert/downgrade xóa phiếu, sao lưu `db` thiếu file, khôi phục làm lùi bộ đếm | High | Accept | Phase 2, 5, 6 |
| 4 | Ký hiệu hóa đơn không có nguồn | High | Accept | Phase 2, 3, 4 |
| 5 | `save_generated` không lưu được `.docx` | High | Accept | Phase 4 |
| 6 | Bộ đếm đua nhau đầu năm, lỗi bị báo nhầm, chưa dùng giờ VN | High | Accept | Phase 2, 4 |
| 7 | zrsd003 ghi `NULL` đè tiền; đường đọc lại không chạy cho đơn đã có hóa đơn | High | Accept | Phase 2, 5 |
| 8 | `issue` không đối chiếu bản xem trước đã duyệt | High | Accept | Phase 4, 5 |
| 9 | `docxtpl` không escape; ô Excel thành công thức | High | Accept | Phase 4 |
| 10 | Đọc PDF không giới hạn; CVE `pdfminer.six`; câu "không lưu đĩa" sai | High | Accept | Phase 1, 3, 5, 6 |
| 11 | PDF ghi đè master (kể cả `manual`); hai thứ thêm ngoài yêu cầu | High | Accept | Phase 3, 4, 5 |
| 12 | Đơn hủy trên sàn nhưng SAP vẫn xuất hóa đơn không lập được phiếu | High | Reject (người dùng: đơn hủy trước DO không có hóa đơn) | Không áp dụng |
| 13 | Làm tròn nửa chẵn bằng `round()`; đơn giá × SL không khớp dòng | High | Accept | Phase 3, 4 |
| 14 | Kiểm tra định dạng Excel dùng cùng thư viện; `insert_rows` không dời chiều cao, vùng in; test tự so sánh vô nghĩa (phần hình bỏ vì không còn logo) | High | Accept | Phase 1, 4 |
| 15 | Tên và địa chỉ người mua tải được bởi mọi viewer | Medium | Accept (người dùng: chỉ admin) | Phase 5, 6 |

Quyết định của người dùng sau review (2026-11-25): Bkav in dòng cha (kit); file Excel chỉ cần sheet `RRG ENGLISH`, bỏ logo và các sheet khác; giữ mã đơn và số hóa đơn mẫu như hiện tại; đơn hủy trước khi có DO thì không có hóa đơn nên finding 12 không áp dụng và phạm vi quay về chỉ đơn `DELIVERED`.

Câu hỏi mở: không còn.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01 … phase-06 (tìm lại các từ cũ: `CANCELLED`, đơn kit bị chặn, logo/hình/neo hình, DO từ PDF, `delivery` ẩn)
- Decision deltas checked: 4 (kit dòng cha, bỏ logo, giữ mã mẫu, bỏ phạm vi đơn hủy)
- Reconciled stale references: 14 (phase 1: yêu cầu định dạng, bước 4 và 5, kiểm tra, rủi ro; phase 2; phase 3: kit, DO, test; phase 4: lý do chặn, test, rủi ro; phase 5; phase 6; plan.md)
- Unresolved contradictions: 0 (cột `delivery` của `sales_return` vẫn lưu DO của đơn, lấy từ `order.do_number`)

## Rủi ro chính

- Mẫu Excel mất thiết lập in khi chuyển `.xls` → `.xlsx` (thử ngay ở phase 1; hỏng thì dừng và chọn lại cách).
- Tách run trong mẫu Word làm `docxtpl` không thay được chỗ giữ chỗ (test đọc lại văn bản).
- Làm tròn đơn giá khác Bkav ở đơn nhiều dòng (kiểm mỗi khi có PDF, phase 3).
