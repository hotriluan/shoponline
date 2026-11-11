---
title: "Hoàn tất mã chặng 1: đơn sàn tới file gửi kế toán"
date: 2026-11-11
summary: Phase 1–4 xong phần mã; khớp file thật 11/11; phase 5–8 chờ recorder SAP
---

# Hoàn tất mã chặng 1: đơn sàn tới file gửi kế toán

## Đã xảy ra
- Dựng repo Python `shoponline` (uv, PostgreSQL 16, Alembic, FastAPI). Database `shoponline_dev`, `shoponline_test`, role `shoponline_app` tạo bằng `scripts/windows/create-databases.ps1`; chủ dự án tự gõ mật khẩu.
- Bộ đọc Shopee, TikTok; ánh xạ SAP theo sàn; trạng thái đơn; file `ĐƠN HÀNG ONLINE`; nhập `zrsd001` với bốn loại lệch; file `SHOP ONLINE ddmmyy` từ `zrsd004`; web có vai trò admin/viewer; sao lưu mã hóa 7-Zip và diễn tập khôi phục.
- 57 test qua, ruff sạch. Commit `d36f989`.

## Lỗi đáng nhớ
- File Shopee và TikTok thật khai sai kích thước sheet; openpyxl `read_only=True` chỉ trả cột A. Fixture tự dựng không bắt được; chỉ lộ ra khi chạy trên file thật. Đã bỏ `read_only` và thêm test vá `<dimension ref="A1"/>`.
- Cổng 8080 bị iVMS-4200 chiếm trên máy phát triển; đổi mặc định sang 8750.
- Mốc thời gian có múi giờ hiển thị theo UTC; thêm bộ lọc `localtime`.

## Kiểm chứng trên file thật 11/11
- 8/8 đơn Shopee khớp file tay về tên SAP, mã SP, số lượng, đơn giá; nhập lại không đổi.
- File gửi kế toán khớp `SHOP ONLINE 111126.XLSX` 18 × 37, 0 ô khác.

## Bước kế tiếp
- Chủ dự án: chuyển `docs/passwordapi.txt` vào kho bí mật; đổi `SHOPONLINE_WEB_PORT` trong `.env` sang 8750; sales admin dùng thử file đơn hàng; triển khai máy thật; 10 ngày chạy song song (G1).
- Phase 5–8 chờ bản ghi recorder SAP, user robot và cổng G1.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
