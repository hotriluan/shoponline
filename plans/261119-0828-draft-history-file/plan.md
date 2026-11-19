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
