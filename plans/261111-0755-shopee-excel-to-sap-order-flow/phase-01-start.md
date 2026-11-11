---
title: "Phase 1: Nền tảng dự án"
status: in-progress
priority: P1
effort: 2d
dependencies: []
---

# Phase 1: Nền tảng dự án

## Overview

Biến thư mục hiện chỉ có `docs/` và `plans/` thành một repo Python chạy được: git, quản lý bí mật, PostgreSQL, migration, kiểm thử. Sau phase này mọi phase khác có chỗ đặt mã và có lệnh kiểm chứng chung.

## Key Insights

- Repo chưa có git. `docs/passwordapi.txt` là bí mật dạng văn bản thường, và các file Excel trong `docs/` chứa tên, địa chỉ khách thật. `.gitignore` phải có trước lần `git add` đầu tiên.
- Máy phát triển có Python 3.14, PostgreSQL 16 và SAP GUI. Chốt một phiên bản Python mà `pywin32` hỗ trợ.
- Một gói chạy hai tiến trình `web` và `robot` tùy lệnh khởi động.

## Requirements

- Một gói Python `shoponline`, cài bằng `uv`, có CLI `shoponline <lệnh>`.
- PostgreSQL cài trực tiếp trên Windows, chỉ nghe trên `localhost`. Máy phát triển có `shoponline_dev` và `shoponline_test`; database thật `shoponline` chỉ có trên máy chạy thật. Migration bằng Alembic.
- Bí mật không nằm trong repo. Cấu hình đọc từ biến môi trường; `.env.example` chỉ chứa tên biến.
- `pytest` và `ruff` chạy được bằng một lệnh.
- `pywin32` là extra `robot`, để phần còn lại test được trên máy không có SAP.

## Architecture

```
pyproject.toml            uv, ruff, pytest; extra "robot" = pywin32
scripts/windows/          tạo database, đăng ký Task Scheduler, sao lưu
.env.example  .gitignore  alembic.ini  migrations/
config/                   cấu hình không bí mật: popup SAP, ID màn hình
src/shoponline/
  config.py  cli.py       đọc biến môi trường; điểm vào: migrate, web, robot
  db/                     engine, session, models
  domain/                 đơn, trạng thái, ánh xạ, ngày goods issue
  importers/              đọc file Shopee, zrsd001, zrsd004
  exports/                file đơn hàng, file gửi kế toán
  sapjobs/  saprobot/     hàng đợi; GUI Scripting (chỉ Windows)
  web/                    FastAPI + template
tests/
```

Thư viện: SQLAlchemy 2, Alembic, psycopg 3, FastAPI, Jinja2, openpyxl, pytest, ruff.

## Related Code Files

- Create: `.gitignore`, `.env.example`, `pyproject.toml`, `alembic.ini`, `migrations/env.py`, `README.md`
- Create: `scripts/windows/create-databases.ps1`
- Create: `src/shoponline/__init__.py`, `config.py`, `cli.py`, `db/session.py`
- Create: `tests/conftest.py`, `tests/test_config.py`
- Move: `docs/passwordapi.txt` ra khỏi thư mục dự án, vào kho bí mật

## Implementation Steps

1. Viết `.gitignore` trước tiên: `.env*` (trừ `.env.example`), `docs/passwordapi.txt`, `docs/*.xlsx`, `docs/*.XLSX`, `*.key`, thư mục ảnh chụp màn hình robot, thư mục file tải lên và file xuất ra, `__pycache__`, `.venv`.
2. Chủ dự án chuyển nội dung `docs/passwordapi.txt` vào kho bí mật rồi xóa file.
3. Chạy `git init`, tạo nhánh `main`, kiểm tra `git status` không liệt kê file bí mật hay file Excel có dữ liệu khách, rồi commit đầu tiên.
4. Tạo `pyproject.toml` với phụ thuộc, extra `robot`, cấu hình `ruff` và `pytest`.
5. Viết `config.py`: một lớp cấu hình đọc biến môi trường, báo rõ tên biến thiếu khi khởi động.
6. Viết `create-databases.ps1` nhận tham số `dev` hoặc `prod`, tạo database và một tài khoản riêng cho ứng dụng. Trước khi chạy, kiểm tra dịch vụ PostgreSQL 16 trên máy đang được dùng cho việc gì khác.
7. Khởi tạo Alembic, một migration rỗng, lệnh `shoponline migrate`.
8. Viết `conftest.py`: test chỉ chạy khi tên database kết thúc bằng `_test`, rollback sau mỗi test.
9. Viết `README.md`: yêu cầu, cách dựng môi trường, các lệnh, nơi lấy bí mật (không ghi giá trị).

## Todo

- [x] `.gitignore` có trước lần `git add` đầu tiên
- [ ] `docs/passwordapi.txt` đã vào kho bí mật và bị xóa (việc của chủ dự án; file đã bị `.gitignore` loại khỏi git)
- [x] `git init`, commit đầu không chứa bí mật hay dữ liệu khách
- [x] `pyproject.toml`, `uv.lock`, extra `robot` (pywin32 cài được trên Python 3.14)
- [x] `config.py` và test báo lỗi khi thiếu biến
- [x] Database `shoponline_dev`, `shoponline_test` và tài khoản ứng dụng
- [x] Alembic và lệnh `shoponline migrate`
- [x] `README.md`

## Success Criteria

- Làm theo `README.md` trên máy Windows đã cài PostgreSQL thì `create-databases.ps1`, `shoponline migrate` và `pytest` đều chạy thành công.
- `git log -p` không chứa mật khẩu, và `git ls-files docs` không có file Excel nào.

## Verification

- `uv run pytest` và `uv run ruff check` thoát mã 0.
- `git ls-files | Select-String -Pattern "password|\.env$|\.key$|\.xlsx$"` không trả kết quả.

## Risk Assessment

- **Bí mật hoặc dữ liệu khách lọt vào lịch sử git.** Giảm thiểu bằng thứ tự bước 1–3. Nếu bí mật đã lọt thì đổi ngay, không chỉ xóa file.
- **`pywin32` chưa hỗ trợ phiên bản Python đã chọn.** Kiểm tra trên máy Windows trước khi chốt phiên bản.

## Rollback

Phase này chỉ tạo file mới. Hoàn tác bằng cách xóa các file vừa tạo.

## Next Steps

Phase 2 thêm schema và bộ đọc file Shopee.
