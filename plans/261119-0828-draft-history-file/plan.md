---
title: "File nháp Shop Online gồm cả đơn chờ hóa đơn và chờ tiền vô"
description: "Thêm nút Tải file nháp ở trang File Shop Online: file gồm đơn đủ dữ liệu và đơn chỉ còn chờ Tax Invoice Doc. hoặc tiền vô, thêm cột Trạng thái, không lưu và không xác nhận được."
status: completed
priority: P2
effort: 3h
branch: main
tags: [feature, backend, web]
blockedBy: []
blocks: []
created: 2026-11-19
---

# File nháp Shop Online

## Overview

File thật (`/sales-history/file`) chỉ chứa đơn đủ dữ liệu. Đơn còn chờ hóa đơn (DO chưa có Tax Invoice Doc. trong `zrsd003`) hoặc chờ tiền vô (Shopee/TikTok chưa có dòng quyết toán) không có trong file, nên kế toán không xem trước được các đơn đó. Kế hoạch này thêm một file nháp chỉ để kiểm tra. File nháp gồm các đơn đủ dữ liệu cộng với các đơn chỉ còn hai lý do chặn đó. Ô còn thiếu để trống, và cột 21 `Trạng thái` ghi đơn đang chờ gì.

Nguồn quyết định: brainstorm trong phiên 2026-11-19 (chủ dự án đã chọn phạm vi và cột Trạng thái).

## Hợp đồng

- **Kết quả:** trang File Shop Online có nút **Tải file nháp** (`NHÁP SHOP ONLINE LỊCH SỬ ddmmyy.xlsx`). File gồm đơn đủ dữ liệu và đơn mà mọi lý do chặn chỉ là "chờ hóa đơn" và/hoặc "chờ tiền vô". Ô `Tax Invoice Doc.` và `Tiền Vô` còn thiếu để trống. Cột 21 `Trạng thái` ghi `Chờ hóa đơn`, `Chờ tiền vô` hoặc cả hai, và để trống với đơn đủ.
- **Ràng buộc:**
  - File nháp không ghi gì vào DB hay đĩa: không có `GeneratedFile`, không có `SalesHistoryFileOrder`, không vào bảng **File đã tải**, không xác nhận được.
  - Dùng chung bộ lọc "Đến ngày đặt hàng" và quyền với file thật; tài khoản xem cũng tải được.
  - File thật giữ nguyên hành vi và 20 cột.
  - Không thêm migration.
- **Ngoài phạm vi:**
  - Đơn bị chặn vì Division, tên khách, tỉnh/thành, mã vật tư hoặc tên báo cáo không vào nháp.
  - Không đổi cách lấy hóa đơn hay tiền vô.
  - Không lưu lịch sử các lần tải nháp.

## Phases

| # | Phase | Trạng thái | Phụ thuộc |
|---|---|---|---|
| 1 | [Dựng dòng nháp, route và nút tải](phase-01-start.md) | completed | — |
| 2 | [Tài liệu](phase-02-docs.md) | completed | 1 |

## Tiêu chí hoàn thành

1. Có bốn đơn: một đủ, một chờ hóa đơn, một chờ tiền vô và một thiếu tên báo cáo. File nháp có đúng ba đơn đầu. Cột 21 lần lượt là trống, `Chờ hóa đơn`, `Chờ tiền vô`. Ô S của đơn chờ hóa đơn và ô T của đơn chờ tiền vô để trống.
2. Đơn vừa chờ hóa đơn vừa chờ tiền vô có trong nháp với `Chờ hóa đơn; Chờ tiền vô`.
3. Tải nháp không đổi số dòng `generated_file` và `sales_history_file_order`, và không để lại file trong thư mục file sinh ra. Tải file thật sau đó ra đúng như trước.
4. Khi chỉ có đơn chờ hóa đơn hoặc tiền vô, nháp vẫn tải được, còn file thật vẫn báo "Chưa có đơn nào sẵn sàng xuất". Khi không có đơn nào để nháp, route báo lỗi và quay lại trang.
5. Tên file trong `Content-Disposition` giải mã ra `NHÁP SHOP ONLINE LỊCH SỬ ddmmyy.xlsx`. Tài khoản xem tải được.
6. `uv run pytest` và `uv run ruff check` thoát mã 0.

## Rủi ro chính

- **Dán nhầm file nháp vào file lịch sử:** tên file có chữ `NHÁP`, có thêm cột 21, và trang ghi rõ nháp không dùng để dán. Không có nút xác nhận nên đơn không bị đánh dấu đã dán.
- **Tên file có dấu khi trả từ bộ nhớ:** `FileResponse` tự mã hóa tên file, còn `Response` thì không. Phase 1 mã hóa theo RFC 5987 (`filename*=utf-8''...`) giống Starlette và có test giải mã lại.
- **Làm lệch file thật:** `collect_rows` và `build_history_workbook` dùng chung cho cả hai file. Cờ `draft` mặc định `False`, và test hiện có của file thật phải chạy qua không sửa.

## Red Team Review

### Session — 2026-11-23 (rà soát đối chiếu mã, plan đã được làm)

**Phương pháp:** hai lens (giả định, thất bại) cộng lens trùng/sót dữ liệu do một người thực hiện trên mã hiện có; không có reviewer riêng. Chi tiết: [báo cáo](../reports/data-integrity-audit-261123-1320-history-file.md). Số liệu lấy từ dev DB, 2026-11-23.
**Findings:** 2 accepted (đề xuất), 5 bác có nguồn kiểm chứng. **Severity:** 2 Low.

| # | Finding | Severity | Disposition | Applied To |
|---|---|---|---|---|
| 1 | Nháp và file thật giống hệt ở 20 cột đầu và cùng tên sheet `sheet1` (`sales_history_workbook.py:277`); chỉ có tên file, cột 21 và dòng chữ trên trang để phân biệt (`sales_history.html:18-20`). Dán nhầm nháp vào file lịch sử: dòng thiếu `Tax Invoice Doc.` hoặc `Tiền Vô`, và đơn vẫn chưa xác nhận nên lần tải thật sau đó xuất lại, file lịch sử bị lặp dòng | Low | Accept (chủ dự án duyệt 2026-11-23) | Rủi ro chính; đề xuất đặt tên sheet nháp khác `sheet1` |
| 2 | Số `Tiền Vô` trong nháp là tổng một phần giao dịch đang có, giống mục 2 của plan `261116-1354`; nháp cho kế toán thấy con số có thể đổi | Low | Accept (chủ dự án duyệt 2026-11-23) | Ghi chú cột Trạng thái; theo mục 2 của `261116-1354` |
| 3 | Tải nháp vô tình đánh dấu đơn đã xuất hoặc lưu file | n/a | Reject: route chỉ gọi `collect_rows` (chỉ `SELECT`) rồi trả `Response` từ bộ nhớ, không `save_generated`, không `add`, không `commit` (`sales_history.py:242-265`); test `test_sales_history_routes.py:478-502` | — |
| 4 | Đơn đã xác nhận xuất hiện lại trong nháp | n/a | Reject: nháp dùng chung `pending_orders` loại đơn đã có trong `sales_history_exported` (`sales_history_workbook.py:141-157`) | — |
| 5 | Đơn bị chặn vì lý do khác lọt vào nháp | n/a | Reject: `is_draftable` yêu cầu mọi lý do thuộc hai loại chờ (`sales_history_workbook.py:136-138,233-239`); test `test_sales_history_workbook.py:278-301` | — |
| 6 | Tên file nháp có dấu hỏng khi tải | n/a | Reject: mã hóa RFC 5987 (`sales_history.py:260-264`); test giải mã lại `test_sales_history_routes.py:487-489` | — |
| 7 | Thêm cột 21 làm lệch file thật | n/a | Reject: cờ `draft` mặc định `False`; `test_sales_history_workbook.py:313-323` khẳng định file thật 20 cột | — |

Quyết định thuộc chủ dự án: có đổi tên sheet của nháp hay không (mục 1). Không sửa mã hay phase file trong đợt này.

## Validation Log

### Session 1 — 2026-11-23 (đối chiếu mã, không hỏi trực tiếp)

| # | Tiêu chí hoàn thành | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | Bốn đơn (đủ, chờ hóa đơn, chờ tiền vô, thiếu tên báo cáo): nháp có ba đơn đầu, cột 21 và ô S/T đúng | VERIFIED | `test_sales_history_workbook.py:278-301,313-323`; `test_sales_history_routes.py:478-502` (đơn bị chặn trong test là thiếu tên khách, cùng nhóm "lý do khác" với thiếu tên báo cáo, `sales_history_workbook.py:136-138`) |
| 2 | Đơn vừa chờ hóa đơn vừa chờ tiền vô có `Chờ hóa đơn; Chờ tiền vô` | VERIFIED | `test_sales_history_workbook.py:304-310` |
| 3 | Tải nháp không đổi `generated_file`, `sales_history_file_order`, không để lại file; file thật sau đó như cũ | VERIFIED | `sales_history.py:258-265` (bộ đệm, không ghi đĩa); `test_sales_history_routes.py:496-502` kiểm bảng DB; thư mục file sinh ra không có test riêng, chỉ có mã |
| 4 | Chỉ có đơn chờ: nháp tải được, file thật báo "Chưa có đơn nào sẵn sàng xuất"; không có đơn nào: báo lỗi | VERIFIED | `test_sales_history_routes.py:505-526`; `sales_history.py:218-224,255-257` |
| 5 | Tên file `Content-Disposition` giải mã ra `NHÁP SHOP ONLINE LỊCH SỬ ddmmyy.xlsx`; viewer tải được | VERIFIED | `test_sales_history_routes.py:487-489,505-516` (viewer); `current_user` ở `sales_history.py:246` |
| 6 | `pytest` và `ruff check` thoát 0 | VERIFIED một phần | ba file test liên quan (route, workbook, tên báo cáo) 72 passed, `ruff check` sạch (2026-11-23); chạy toàn bộ bộ test ra 464 passed và 1 lỗi setup `DeadlockDetected` ở `tests/web/test_backup_list.py`, không thuộc plan này, nhiều phiên cùng dùng DB test; chưa chạy lại riêng |

**Giả định đã kiểm:** nháp không ghi DB (VERIFIED, `sales_history.py:242-265`); ranh giới tháng dùng chung `until` với file thật (VERIFIED, `:253`); `COLUMNS + (STATUS_COLUMN,) if draft else COLUMNS` ra 21 cột cho nháp và 20 cho file thật (VERIFIED, `sales_history_workbook.py:279`, test `:323`).

**Câu hỏi cho chủ dự án:**
1. Có muốn nháp dùng tên sheet khác `sheet1` (ví dụ `NHÁP`) để dán nhầm bị Excel và kế toán thấy ngay không? (Red Team mục 1.)
2. Cột `Tiền Vô` trong nháp là số tạm thời khi đơn còn nhiều giao dịch chưa về; kế toán có chấp nhận hiểu như vậy không?
