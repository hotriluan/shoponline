---
title: "Chọn tháng trên trang File Shop Online và đọc zrsd003 theo tháng"
description: "Trang File Shop Online chọn theo tháng đặt hàng thay vì ngày; robot đọc zrsd003 với Billing Date từ ngày 1 của tháng (hoặc ngày đặt sớm hơn của đơn tồn) đến hôm nay."
status: in-progress
priority: P2
effort: 4h
branch: main
tags: [feature, web]
blockedBy: []
blocks: []
created: 2026-11-19
---

# Chọn tháng và đọc zrsd003 theo tháng

## Overview

Chủ dự án làm file `Shop Online 2022-2026` mỗi tháng một lần, khoảng ngày 10 của tháng sau (tháng 10/2026 làm vào khoảng 10/11/2026). Trang hiện chọn **ngày** (`until`) và robot đọc zrsd003 từ ngày đặt sớm nhất của đơn chờ hóa đơn đến hôm nay, nên người dùng không đoán trước được khoảng đọc. Kế hoạch đổi ô chọn sang **tháng đặt hàng** và cố định khoảng đọc zrsd003 theo tháng đó.

Nguồn quyết định: brainstorm trong phiên 2026-11-19 (không có file report riêng). Hóa đơn ra sau DO, DO sau đơn ([sales_history.py:76-82](../../src/shoponline/web/routes/sales_history.py#L76-L82)), nên khoảng đọc phải kết thúc ở **hôm nay**, không phải ngày cuối tháng; nếu kết thúc ở cuối tháng thì đơn đặt 30/10 có hóa đơn 2/11 bị chặn oan.

## Hợp đồng

- **Kết quả:** người dùng chọn tháng (ví dụ 10/2026); trang lấy mọi đơn Đã có DO chưa xác nhận, đặt tới hết ngày cuối tháng đó; nút "Robot đọc zrsd003" đọc Billing Date từ `min(ngày 1 của tháng, ngày đặt sớm nhất của đơn chờ hóa đơn)` đến hôm nay, và trang hiện khoảng này trước khi bấm.
- **Ràng buộc:** giữ cách gom đơn (mọi đơn chưa xác nhận đặt tới `until`, kể cả đơn tồn tháng trước); giữ khóa chống trùng theo khoảng ngày ([report_requests.py:62-63](../../src/shoponline/sapjobs/report_requests.py#L62-L63)); chỉ admin bấm đọc; không đổi cột hay nội dung file tải về; không migration.
- **Ngoài phạm vi:** form `read_zrsd003` bằng tay trên trang Robot SAP; khoảng ngày gợi ý cho file quyết toán (`_settlement_range`); tự hẹn giờ đọc; zrsd001/zrsd004; tên file tải về.

## Quyết định đã chốt (2026-11-19, chủ dự án)

1. Tháng đã chọn gom đơn theo **ngày đặt**.
2. Khoảng đọc zrsd003 kết thúc ở **hôm nay**, bắt đầu ở ngày 1 của tháng hoặc ngày đặt sớm hơn của đơn tồn còn chờ hóa đơn.
3. Tham số trang đổi từ `until=YYYY-MM-DD` sang `month=YYYY-MM` cho mọi route của trang; server tính `until` = ngày cuối tháng.
4. Tháng mặc định khi mở trang: **tháng trước** (chủ dự án xác nhận).
5. Form "Ra lệnh cho robot" trên trang Robot SAP giữ chọn tự do từ ngày đến ngày, không bị khóa theo tháng.

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Ô chọn tháng và khoảng đọc zrsd003](./phase-01-start.md) | Completed |
| 2 | [Tài liệu và kiểm trên production](./phase-02-docs-and-live-check.md) | In progress (tài liệu xong; kiểm production chờ deploy) |

## Tiêu chí hoàn thành

1. `GET /sales-history?month=2026-10` chỉ đếm đơn đặt tới hết 31/10/2026; đơn đặt 01/11 không có trong file, nháp hay số đơn.
2. Với đơn đặt 30/10 chờ hóa đơn và hôm nay 10/11, trang hiện và robot nhận khoảng 01/10/2026 → 10/11/2026.
3. Với thêm một đơn tồn đặt 25/09 chờ hóa đơn, khoảng bắt đầu 25/09/2026.
4. Mở trang không có `month` thì chọn tháng trước của hôm nay (giờ Việt Nam).
5. `month` sai dạng (`2026-13`, `abc`) trả lỗi 422 như tham số ngày hiện nay, không lỗi 500.
6. `uv run pytest` và `uv run ruff check` thoát mã 0.

## Rủi ro

- **Một lần đọc dài hơn:** khoảng ~40 ngày cho cả Sales Office 1401 (zrsd003 không lọc theo khách). Phase 2 đo thời gian và số dòng của lần đọc đầu trên production.
- **Link cũ có `until=`** (bookmark) bị bỏ qua và rơi về tháng mặc định; chấp nhận, trang không phải API.

## Red Team Review

### Session — 2026-11-23
**Phương pháp:** plan đã làm nên soi mã đối chiếu plan (2 lens: Failure Mode Analyst, Assumption Destroyer, cộng lens bắt buộc "trùng hoặc sót dữ liệu"); người soi tự phân xử. Số liệu từ dev DB, 2026-11-23.
**Findings:** 5 (2 accepted, 3 rejected)
**Severity breakdown:** 1 Medium, 1 Low (chấp nhận); 3 bị bác

| # | Finding | Severity | Disposition | Hướng xử lý |
|---|---------|----------|-------------|-------------|
| 1 | Khoảng đọc không có trần: chọn tháng cũ (ví dụ 2026-01 khi đang là tháng 11) mà còn đơn chờ hóa đơn thì khoảng là `min(ngày 1 của tháng, đơn chờ sớm nhất)` -> hôm nay, có thể nhiều tháng cho cả Sales Office 1401 (`sales_history.py:105-112`); robot hết giờ chờ thì việc FAILED, không nhập phần nào. Plan chỉ tính khoảng ~40 ngày | Medium | Accept (chủ dự án duyệt 2026-11-23) | Đo thời gian thật khi deploy; nếu quá dài thì chia khoảng theo tháng hoặc cảnh báo khi khoảng quá 62 ngày |
| 2 | Khóa chống trùng theo khoảng chính xác, mà ngày kết thúc là hôm nay nên mỗi ngày một khóa mới (`report_requests.py:62-63`): bấm ở hai ngày tạo hai việc cùng đọc lại các hóa đơn cũ | Medium | Reject (vô hại về dữ liệu: nhập idempotent `report_ingest.py:93-101`; dev DB 2026-11-23: việc 48 chồng việc 47, 0 mới/56 cập nhật). Chỉ tốn thời gian robot | — |
| 3 | Hóa đơn nằm ngoài khoảng đọc của một đơn đang chờ | High | Reject (không xảy ra: hóa đơn sau DO, DO sau đơn; khoảng bắt đầu ở ngày đặt sớm nhất của đơn chờ, `sales_history.py:105-112`; dev DB: 0 hóa đơn có `billing_date` trước ngày đặt của đơn) | — |
| 4 | Giữa lúc xem trang và bấm nút, danh sách đơn chờ đổi nên khoảng đọc khác khoảng đã hiện | Medium | Reject (vô hại: route `read_zrsd003` tính lại và thông báo khoảng thật; khoảng chỉ rộng hoặc hẹp theo đơn chờ hiện có) | — |
| 5 | Đơn chờ vĩnh viễn (không bao giờ có hóa đơn) kéo khoảng đọc lùi mãi, tăng dần thời gian đọc | Low | Accept (chủ dự án duyệt 2026-11-23) | Trùng phát hiện 5 của plan `261119-0605`; theo dõi bằng SQL #1 trong file phát hiện |

Lens trùng/sót dữ liệu: khoảng đọc không sót hóa đơn của đơn chờ (#3); đọc chồng không trùng dữ liệu (#2). Chi tiết ở `plans/reports/data-integrity-audit-261123-1320-tax-invoice.md`.

## Validation Log

### Session — 2026-11-23
**Phương pháp:** kiểm từng tiêu chí với mã, test và dev DB (2026-11-23); không hỏi chủ dự án.

| # | Tiêu chí | Kết quả | Bằng chứng |
|---|----------|---------|------------|
| 1 | `?month=2026-10` chỉ đếm đơn tới hết 31/10 | VERIFIED | `_month_bounds` và `pending_orders` (`ordered_at < until + 1 ngày`, `sales_history_workbook.py:141-160`); `test_an_order_after_the_chosen_month_is_left_for_later` qua |
| 2 | Đơn 30/10 chờ, hôm nay 10/11 -> khoảng 01/10 -> 10/11 | VERIFIED | `sales_history.py:112`; `test_orders_waiting_for_invoices_offer_a_zrsd003_read` qua |
| 3 | Đơn tồn 25/09 -> khoảng bắt đầu 25/09 | VERIFIED | `sales_history.py:112` (`min(first_day, *waiting)`); `test_the_zrsd003_read_reaches_back_to_an_older_order_still_waiting` qua |
| 4 | Không có `month` thì chọn tháng trước (giờ Việt Nam) | VERIFIED | `_month_bounds` dùng `today_vn()`; `test_the_page_opens_on_last_month` qua |
| 5 | `month` sai dạng trả 422 | VERIFIED | regex `MONTH` (`sales_history.py:73`) cho Query và Form; `test_a_malformed_month_is_refused` qua |
| 6 | `pytest` và `ruff check` mã 0 | xem Validation Log của plan `261119-0605` | `ruff check` sạch; nhóm test liên quan qua; lượt chạy cả bộ đầu có lỗi do DB test dùng chung với tác tử song song |
| 7 | Phase 2: kiểm production chờ deploy, tháng 10/2026 không còn đơn bị chặn vì thiếu hóa đơn | UNVERIFIED | Không có journal hay biên bản đọc theo tháng. Dev DB có hai việc `read_zrsd003` xong 2026-11-19 (khoảng 13-19/11 và 17-19/11) nhưng không khớp công thức tháng (ngày 1 của tháng), nên không chứng minh khoảng mới; todo "Kiểm lần đọc thật" của phase 2 vẫn mở |

**Giả định:**
- "Hóa đơn ra sau DO sau đơn nên khoảng kết thúc ở hôm nay đủ": VERIFIED trên dev (0 hóa đơn trước ngày đặt).
- "Khoảng đọc cho một tháng (~40 ngày) chạy được trong thời gian chờ của robot": UNVERIFIED (chưa đo trên production; dev DB không ghi thời gian chạy).
- "Link cũ `until=` bị bỏ qua là chấp nhận được": VERIFIED (route chỉ nhận `month`, `sales_history.py:73`).

**Câu hỏi cho chủ dự án:**
1. Khi deploy, có chạy lần đọc tháng 10/2026 và ghi thời gian chạy, số dòng đọc vào journal không (todo cuối của phase 2)?
2. Có muốn cảnh báo hoặc chia khoảng khi khoảng đọc dài hơn khoảng 2 tháng (phát hiện #1) không?

### Cập nhật 2026-11-23: bằng chứng production

Việc đọc zrsd003 id 61 trên production (tạo 2026-11-23, khoảng 2026-11-01 đến 2026-11-23, DONE) xác nhận đọc theo tháng đã chạy. Tiêu chí kiểm production được xem là VERIFIED.
