---
title: "Tải file tiền về Lazada theo số hóa đơn"
description: "Admin tải file Excel 3 cột (Số hóa đơn, Ngày nhận tiền, Số tiền); hệ thống tra số hóa đơn ra đơn Lazada, cho xem trước rồi lưu vào platform_settlement."
status: pending
priority: P1
effort: 7h
branch: main
tags: [feature, backend, frontend]
blockedBy: []
blocks: []
created: 2026-11-25
---

# Tải file tiền về Lazada theo số hóa đơn

## Overview

Trang `/settlements/lazada` hiện cho nhập tiền từng đơn hoặc dán nhiều dòng theo mã đơn ([manual_settlement.py](../../src/shoponline/accounting/manual_settlement.py), [settlements.py](../../src/shoponline/web/routes/settlements.py)). Kế toán có file Excel theo số hóa đơn SAP chứ không có mã đơn, nên kế hoạch này thêm đường tải file: đọc 3 cột, tra số hóa đơn ra đúng một đơn Lazada, xem trước từng dòng, rồi lưu bằng `set_amount` như tiền nhập tay.

## Contract

- **Kết quả:** admin chọn file `.xlsx` ở trang Tiền về Lazada, thấy bảng xem trước (dòng lưu được, dòng bị từ chối kèm lý do), bấm lưu thì các dòng đúng vào `platform_settlement` (`source = 'manual'`), và cột `Tiền Vô` của file Shop Online có số.
- **Ràng buộc:**
  - Không đổi schema, không migration. Dùng lại `manual_settlement.check` và `set_amount`, nên có `event_log` và kiểm ngày, số tiền như hiện nay.
  - Chỉ admin tải lên. File không được lưu lên đĩa và không tạo `import_batch`; chỉ nội dung đã chuẩn hóa đi qua form xem trước.
  - Số hóa đơn phải tra ra đúng một đơn Lazada. Không có đơn nào hoặc nhiều đơn thì từ chối dòng đó, không đoán và không chia tiền.
  - File đọc theo tên cột ở dòng 1 của sheet đầu: `Số hóa đơn`, `Ngày nhận tiền`, `Số tiền` (chủ dự án xác nhận đúng tên cột trong file của kế toán). Thiếu cột thì từ chối cả file.
- **Ngoài phạm vi:** file CSV, chia tiền một hóa đơn cho nhiều đơn, cột mã đơn trong file, lưu số hóa đơn vào `platform_settlement`, tự lấy tiền từ API Lazada, đổi báo cáo hay file lịch sử.
- **Bằng chứng nền** (truy vấn chỉ đọc trên dev DB, 2026-11-25): 290 hóa đơn SAP không có số trùng (kể cả sau khi bỏ số 0 đầu), 0 DO Lazada gom nhiều đơn, 0 hóa đơn ứng với nhiều đơn Lazada, 15 trong 17 đơn Lazada có DO đã có hóa đơn. Dữ liệu dev nhỏ và `sap_tax_invoice` không lưu ký hiệu hóa đơn, nên phép từ chối dòng mơ hồ là lớp bảo vệ bắt buộc, không phải tùy chọn.

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Phase 1: Đọc file và tra số hóa đơn](./phase-01-invoice-file-logic.md) | Pending |
| 2 | [Phase 2: Trang tải file và tài liệu](./phase-02-upload-page-and-docs.md) | Pending |

Phase 2 phụ thuộc phase 1 (dùng hàm đọc file và tra hóa đơn).

## Success Criteria

- [ ] Xem trước phân loại đúng: dòng lưu được, hóa đơn không có trong SAP, hóa đơn chưa gắn đơn Lazada, hóa đơn ứng với nhiều đơn, hóa đơn trùng trong file, ngày sai, số tiền sai, ô trống.
- [ ] Số hóa đơn mất số 0 đầu hoặc đọc thành số (`1234`, `1234.0`) vẫn khớp hóa đơn `00001234`.
- [ ] Tải lại cùng file thì cập nhật dòng cũ, không tạo dòng trùng; `event_log` giữ số cũ và số mới.
- [ ] Lưu xong, cột `Tiền Vô` của file Shop Online (đơn Lazada) hiện số tiền.
- [ ] Viewer không thấy ô tải file và không gọi được hai route mới.
- [ ] `uv run pytest tests/accounting tests/web tests/exports` xanh; `uv run ruff check` sạch.
- [ ] `docs/daily-operations.md` và `docs/system-architecture.md` mô tả cách tải file.

## Rủi ro

- Số hóa đơn trong file có thể không đúng định dạng SAP (chữ, khoảng trắng): chuẩn hóa chỉ bỏ khoảng trắng và số 0 đầu, nên giá trị lạ không khớp và bị báo "không có trong SAP", không lưu nhầm.
- Số hóa đơn có thể trùng khi SAP đổi ký hiệu: dòng đó thành "ứng với nhiều đơn" và bị từ chối.
- Giữa lúc xem trước và lúc lưu dữ liệu có thể đổi: bước lưu kiểm lại toàn bộ như `save_paste`, dòng hỏng được nêu tên và bỏ qua.
