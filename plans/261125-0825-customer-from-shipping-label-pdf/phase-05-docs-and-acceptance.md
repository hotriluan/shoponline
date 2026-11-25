---
phase: 5
title: "Tài liệu và nghiệm thu"
status: in-progress
priority: P2
effort: "2h"
dependencies: [4]
---

# Phase 5: Tài liệu và nghiệm thu

## Goal

Tài liệu vận hành và bảo mật mô tả đúng luồng mới; chạy thử thật trên database dev với hai file mẫu.

## Files

- Modify: `docs/daily-operations.md` (bước tải PDF phiếu vận đơn thay cho gõ tay tên khách Shopee/TikTok; cách xử
  lý trang báo "không đọc được" và trang xác nhận)
- Modify: `docs/security-and-data-retention.md` (dòng về PDF phiếu vận đơn: chỉ admin, 40 MB/500 trang, đọc
  trong bộ nhớ, không lưu, file tạm của máy chủ web xóa ngay sau khi đọc; cột `address_source`)
- Modify: `docs/system-architecture.md` chỉ khi tài liệu đó đang liệt kê các importer hoặc cột `customer_info`
  (đọc trước, cập nhật phần đang có, không thêm mục mới)

## Steps

1. Đọc từng tài liệu trước khi sửa; sửa phần sở hữu nhỏ nhất.
2. Toàn bộ kiểm tra: `uv run ruff check`, `uv run ruff format --check`, `uv run pytest -q`.
3. Chạy test file thật:
   `SHOPONLINE_SAMPLE_SPX_LABEL_PDF="docs/tenkhach/Shopee - Kênh Người bán.pdf" SHOPONLINE_SAMPLE_JT_LABEL_PDF=docs/tenkhach/tiktok.pdf uv run pytest tests/importers/test_shipping_label_pdf.py -q`.
4. Nghiệm thu tay trên web dev (sao lưu database dev trước): tải hai file cùng lúc, kiểm 23 dòng trên `/customers`
   có tên, địa chỉ, tỉnh; tải lại lần hai thì báo giữ nguyên 23; sửa tay một địa chỉ rồi tải lại thì hiện trang
   xác nhận cho đúng đơn đó.
5. Kiểm thư mục dữ liệu và thư mục tạm của tiến trình web không còn PDF sau khi tải.
6. `git status` không hiện `docs/tenkhach/`.

## Todo

- [ ] Cập nhật tài liệu
- [ ] Lint, format, toàn bộ test
- [ ] Test file thật
- [ ] Nghiệm thu tay trên dev

## Verification

Mọi tiêu chí trong [plan.md](./plan.md) mục Success Criteria được đánh dấu kèm bằng chứng (lệnh và kết quả).
