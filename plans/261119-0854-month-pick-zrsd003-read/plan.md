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
