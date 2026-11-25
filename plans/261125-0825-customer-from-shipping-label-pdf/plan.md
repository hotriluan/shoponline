---
title: "Đọc tên và địa chỉ khách Shopee/TikTok từ PDF phiếu vận đơn"
description: "Admin tải PDF phiếu vận đơn Shopee (SPX) và TikTok (J&T) lên trang Khách hàng; hệ thống đọc mã đơn, tên, địa chỉ vào customer_info rồi bỏ file."
status: in-progress
priority: P1
effort: 16h
branch: main
tags: [feature, backend, database, web]
blockedBy: []
blocks: []
created: 2026-11-25
---

# Đọc tên và địa chỉ khách từ PDF phiếu vận đơn

## Overview

Admin tải PDF phiếu vận đơn Shopee (SPX) và TikTok (J&T) lên trang Khách hàng; hệ thống đọc mã đơn, tên, địa
chỉ vào `customer_info` rồi bỏ file. Hiện admin phải gõ tay tên khách của hai sàn này vì file Excel của sàn
che tên, còn địa chỉ từ Excel chỉ có dạng "xã, tỉnh".

Nguồn quyết định: [brainstorm-261125-1458-customer-name-from-shipping-label-pdf.md](../reports/brainstorm-261125-1458-customer-name-from-shipping-label-pdf.md).
Nguyên mẫu đã đọc đúng 23/23 trang mẫu (`docs/tenkhach/`), cả 23 địa chỉ được `province_of` nhận ra tỉnh.

## Hợp đồng

- **Ràng buộc:** đọc lớp chữ bằng `pdfplumber` có sẵn, không OCR, không gửi PDF ra ngoài; chỉ admin; tối đa
  40 MB và 500 trang mỗi file; **không lưu PDF** (đọc trong bộ nhớ, đóng `UploadFile` trong `finally`, không ghi
  vào thư mục dữ liệu); không ghi tên, địa chỉ vào log hay `event_log`; sao lưu `db` trước migration.
- **Không làm:** đọc SĐT, Lazada, đơn vị vận chuyển khác SPX/J&T (làm khi có file mẫu), sửa chính tả địa chỉ.
- **Quy tắc tên:** trống thì ghi; giống thì giữ; khác thì chờ admin xác nhận. Tên TikTok dạng `user…` ghi nguyên.
- **Quy tắc địa chỉ** theo cột mới `customer_info.address_source` (`file` | `label` | `admin`, NULL = chưa rõ):
  trống thì ghi; giống thì giữ; khác mà nguồn `file`/`label` thì ghi đè; khác mà nguồn `admin`/NULL thì chờ
  xác nhận. Mỗi lần đổi địa chỉ tính lại `province`, `place_key`.

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Cột nguồn địa chỉ](./phase-01-address-source-column.md) | Done |
| 2 | [Bộ đọc PDF phiếu vận đơn](./phase-02-label-pdf-reader.md) | Done |
| 3 | [Ghi kết quả vào customer_info](./phase-03-apply-labels-to-customers.md) | Done |
| 4 | [Route tải lên và trang xác nhận](./phase-04-upload-route-and-confirm-page.md) | Done |
| 5 | [Tài liệu và nghiệm thu](./phase-05-docs-and-acceptance.md) | Code done; dev run pending |

Thứ tự: 1 → 3 → 4; 2 độc lập với 1 và phải xong trước 3; 5 sau cùng.

## Success Criteria

- [ ] Tải `Shopee - Kênh Người bán.pdf` ghi đúng 16 tên và địa chỉ (`SHOPEE`), `tiktok.pdf` ghi đúng 7 (`TIKTOK`,
      kể cả `user8822216008733`), tải cả hai cùng lúc cũng vậy; 23 dòng có `province`.
- [ ] Quy tắc tên và địa chỉ ở trên đúng trong test, gồm trường hợp admin chỉ sửa tên thì nguồn địa chỉ không đổi.
- [ ] Màn hình xác nhận ghi được dòng đã chọn mà không cần tải lại file.
- [ ] Thông báo chỉ nêu số lượng và số trang, không nêu tên hay địa chỉ.
- [ ] File sai loại, quá 40 MB, quá 500 trang, không trang nào nhận ra: từ chối, không ghi gì.
- [ ] Sau mỗi lần tải (thành công, lỗi, quá thời gian) file upload đã đóng và thư mục dữ liệu không có file mới.
- [ ] Nhập Excel sau khi đọc nhãn không ghi đè tên, địa chỉ từ nhãn.
- [ ] `uv run pytest` và `uv run ruff check` sạch; tài liệu vận hành và bảo mật đã cập nhật.

## Validation Log

### Session 1 — 2026-11-25

Đã kiểm claim với mã nguồn: `customer_info` ở `models.py:181`; điểm ghi địa chỉ ở `order_import.py:293-304` và
`customers.py:118-121`; migration mới nhất `0016_report_views`; `PDF_SECONDS = 30` và mẫu upload ở
`returns.py:236`; mẫu test file thật dựa trên biến môi trường ở `test_invoice_pdf.py:150`; `.gitignore` thiếu
`docs/**/*.pdf`. Failed: 0.

| Câu hỏi | Trả lời |
|---|---|
| Một file lỗi trong lần tải nhiều file | Từ chối cả lần tải, không ghi gì |
| Số file tối đa mỗi lần | 10 |
| Nhiều trang cùng mã đơn mà lệch nhau | Đưa vào trang xác nhận |

Cả ba trùng với nội dung phase 2 và phase 4, không phải sửa phase nào.

<!-- slug: customer-from-shipping-label-pdf -->
