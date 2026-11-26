---
title: "Bỏ phiếu nhập hàng trả về (ZDE1) khỏi file gửi kế toán"
description: "File gửi kế toán chỉ giữ phiếu giao bán ZDA1; phiếu nhập hàng trả về ZDE1 bị bỏ, đếm lý do, không còn cảnh báo thiếu mã đơn giả."
status: in-progress
priority: P1
effort: "3h"
tags: [accounting, zrsd004, sap]
created: 2026-11-26
---

# Bỏ phiếu nhập hàng trả về (ZDE1) khỏi file gửi kế toán

## Overview

ZRSD004 của khách sàn có cả phiếu nhập hàng trả về (`Delivery Type = ZDE1`, kho QC `0301`). Các dòng này không có đơn trên sàn, nên bị báo "thiếu mã đơn, tên khách, địa chỉ" và bị cộng như hàng xuất vào file kế toán (lần gửi 8, ngày 26/11, có 5 dòng). Kế hoạch này chỉ giữ phiếu giao bán `ZDA1`.

Quyết định, bằng chứng và đánh đổi: [brainstorm-261126-1311-exclude-return-deliveries-from-accounting-file.md](../reports/brainstorm-261126-1311-exclude-return-deliveries-from-accounting-file.md).

## Goals

| # | Goal | Priority |
|---|------|----------|
| 1 | File gộp gửi kế toán chỉ có dòng `ZDA1`; dòng khác bị bỏ với lý do riêng, dòng tổng tính lại không gồm chúng | P1 |
| 2 | Bản xem trước khi robot đọc (trang Robot SAP) không cảnh báo thiếu thông tin cho dòng không phải `ZDA1` | P1 |
| 3 | Tài liệu vận hành nói rõ phiếu nhập hàng trả về không vào file | P2 |

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Lọc phiếu không phải giao bán](./phase-01-filter-return-deliveries.md) | Completed |
| 2 | [Tài liệu và kiểm tra trên máy chạy thật](./phase-02-docs-and-production-check.md) | In progress |

## Constraints

- Lọc theo `Delivery Type`, theo danh sách cho phép (`ZDA1`), không theo dấu hiệu thiếu thông tin khách.
- Không đổi schema, không đổi giao diện; trang đợt đã liệt kê mọi lý do bỏ dòng.
- Không sửa file 26/11 (đã chốt, người dùng đã bỏ tay 5 dòng).

## Non-goals

- Ghép phiếu `ZDE1` với tính năng phiếu trả hàng hoặc báo cáo trả hàng.
- Đưa danh sách loại phiếu vào `.env` hay trang cài đặt.

## Success Criteria

- [x] Gộp file có cả `ZDA1` và `ZDE1`: không còn dòng `ZDE1`, dòng tổng chỉ tính `ZDA1`, `dropped` có lý do mới với đúng số dòng.
- [x] Dòng `ZDE1` chưa goods issue xong bị bỏ vì loại phiếu, không nằm trong `skipped`.
- [x] File gộp thiếu cột `Delivery Type` bị từ chối với thông báo thiếu cột.
- [x] Bản xem trước một file không cảnh báo dòng `ZDE1`, vẫn cảnh báo dòng `ZDA1` thiếu dữ liệu.
- [x] `uv run pytest` qua toàn bộ; ruff sạch.
- [ ] Sau deploy, đợt gửi kế toán kế tiếp trên máy chạy thật hiện lý do bỏ dòng mới nếu có phiếu `ZDE1`, và không còn cảnh báo thiếu mã đơn cho chúng.

<!-- slug: exclude-return-deliveries-from-accounting-file -->
