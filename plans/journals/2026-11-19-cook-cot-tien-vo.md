# Làm cột Tiền Vô (phase 1-2 và tài liệu phase 3)

Ngày 2026-11-19.

- Bảng `platform_settlement` (migration `0009_platform_settlement`), bộ đọc `read_settlement_file` cho Shopee/TikTok, `ingest_settlement` upsert theo `(platform, line_key)`.
- Chạy bộ đọc trên file mẫu `docs/tienvo/`: Shopee 177 dòng (3 âm, bỏ 3 dòng "Điều chỉnh"), TikTok 115 dòng (21 bằng 0, 1 âm), Lazada bị từ chối.
- Đối chiếu mã đơn TikTok: 7/7 mã 18 số trong các file đơn TikTok ở `docs/` có trong `ID đơn hàng liên quan`. Vẫn phải đối chiếu với production trước khi deploy.
- File tải về có cột 20 `Tiền Vô`; hộp "Đơn chờ tiền vô" và form upload (chỉ admin) ở `/sales-history`.
- `.gitignore` thêm `docs/**/*.xlsx` để file mẫu có mã đơn thật không bị commit.
- `uv run pytest` 431 test xanh, `ruff check` sạch.

Còn lại: sao lưu DB, deploy, `alembic upgrade head` và upload file quyết toán phủ phần tồn trên production (phase 3 bước 2-5).
