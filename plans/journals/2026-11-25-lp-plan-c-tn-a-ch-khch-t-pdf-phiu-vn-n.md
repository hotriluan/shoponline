---
title: "Lập plan đọc tên, địa chỉ khách từ PDF phiếu vận đơn"
date: 2026-11-25
summary: "Plan 5 phase đọc tên và địa chỉ khách Shopee (SPX) và TikTok (J&T) từ PDF phiếu vận đơn vào customer_info, thêm cột address_source, không lưu PDF."
---

# Lập plan đọc tên, địa chỉ khách từ PDF phiếu vận đơn

## What happened
File Excel của Shopee và TikTok che tên người mua, nên admin phải gõ tay tên khách. Khảo sát hai PDF mẫu trong `docs/tenkhach/`: cả hai đều có lớp chữ. Nguyên mẫu `pdfplumber` đọc đúng mã đơn, tên và địa chỉ ở 16/16 trang SPX và 7/7 trang J&T, và `province_of` nhận ra tỉnh mới cho cả 23 địa chỉ.

Hai điểm khó: phiếu SPX in hai cột nên phải cắt theo toạ độ. Nhãn J&T ngắt dòng địa chỉ theo ký tự và không giữ dấu cách, nên khi nối lại thì dùng quy tắc một cụm nguyên âm (một âm tiết tiếng Việt).

## Decision
- Đọc lớp chữ cục bộ, không OCR, không AI hay API của sàn.
- Không lưu PDF: đọc trong bộ nhớ, đóng `UploadFile` trong `finally`.
- Thêm cột `customer_info.address_source` (`file` / `label` / `admin`) để chỉ hỏi admin khi ghi đè địa chỉ do admin sửa tay.
- Tên TikTok dạng `user…` ghi nguyên.
- Giới hạn 40 MB và 500 trang mỗi file, tối đa 10 file mỗi lần. Có một file lỗi thì từ chối cả lần tải.
- Nhiều trang cùng mã đơn mà lệch nhau thì đưa vào trang xác nhận.
- `.gitignore` thiếu `docs/**/*.pdf`; sửa trong phase 2.

## Next steps
Chạy `/ak-cook plans/261125-0825-customer-from-shipping-label-pdf/plan.md`. Phase 1 cần sao lưu database dev trước migration `0017`.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
