---
phase: 3
title: "Tài liệu và chạy thử production"
status: in-progress
priority: P2
effort: "2h"
dependencies: [2]
---

# Phase 3: Tài liệu và chạy thử production

## Goal
Tài liệu vận hành mô tả cột Tiền Vô và cách upload; production chạy migration an toàn và kiểm với file thật.

## Files to Create / Modify
- Modify: `docs/daily-operations.md` — mục file Shop Online: cột 20 `Tiền Vô`, hộp "Đơn chờ tiền vô", nơi xuất file ở Shopee/TikTok, Lazada để trống, chỉ dòng đầu đơn có số, đơn giao không thành công có thể âm, Tiền Vô 0 là đơn hoàn tiền toàn bộ (TikTok) <!-- Updated: Validation Session 1 - giải thích Tiền Vô 0 -->; trong các bước dán: thêm header cột T một lần và bước sắp xếp chọn A:T (không chỉ A:S); tiền vô không cập nhật sau khi đã xác nhận dán. **[Red team]**
- Modify: `docs/system-architecture.md` — `platform_settlement`, `read_settlement_file`/`ingest_settlement`, 20 cột.
- Modify: `docs/security-and-data-retention.md` — thêm file quyết toán vào bảng "Hệ thống giữ những gì" với nội dung thật (mã đơn, số tiền; Shopee có tên đăng nhập người bán; TikTok có sheet lịch sử rút tiền với tài khoản ngân hàng đã che) và vào danh sách xóa ngay sau khi nhập; bảng chỉ giữ mã đơn, số tiền, ngày; đơn không bao giờ quyết toán giữ thông tin khách tới khi được xử lý tay. **[Red team]**
- Modify: `docs/deployment-guide.md` — rollback tính năng này là revert code, **không** downgrade 0009 (bảng còn lại vô hại với code cũ; file gốc đã xóa nên bảng là bản duy nhất); cách gỡ một lần nhập sai: sao lưu, xóa dòng theo `import_batch_id`, rồi upload lại file đúng. **[Red team]**

## Tasks & Steps
1. Cập nhật bốn tài liệu trên; đọc lại từng câu đối chiếu code.
2. Trước khi deploy: đối chiếu `ID đơn hàng liên quan` của một file quyết toán TikTok hiện tại (phủ ngày đã có trong DB) với `sales_order.platform_order_id` trên production, chỉ đọc. Không khớp thì không deploy. **[Red team]**
3. Production: sao lưu DB (theo `docs/deployment-guide.md`), deploy, `alembic upgrade head`.
4. Upload file quyết toán Shopee và TikTok phủ khoảng ngày mà hộp "Đơn chờ tiền vô" hiện (ngày đặt sớm nhất tới hôm nay). **[Red team]**
5. Kiểm: số đơn chờ tiền vô (tính cả đơn đang bị chặn vì lý do khác) giảm; vài đơn TikTok trong file tải về có cột 20 khớp `Tổng số tiền quyết toán` trên file sàn. **[Red team]**
6. Ghi journal ngắn trong `plans/journals/`.

## Verification
- Link trong docs mở đúng file; `uv run pytest -q` vẫn xanh sau khi sửa docs.
- Trên production: `/sales-history` hiện hộp chờ đúng, file tải về có 20 cột.

## Risks
- Đơn chờ quá cũ nằm ngoài kỳ export tối đa của sàn: upload nhiều file theo từng kỳ (nhập chồng kỳ an toàn nhờ khóa dòng).
- Đơn không bao giờ được quyết toán ở lại "Đơn chờ tiền vô" và giữ thông tin khách quá hạn lưu giữ (retention chỉ xóa đơn đã xuất). Nút bỏ qua nằm ngoài phạm vi; ghi ở `security-and-data-retention.md`. **[Red team]**
