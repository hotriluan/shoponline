---
title: "Phase 1: Nền tảng dự án"
status: todo
priority: P1
effort: 2d
dependencies: []
---

# Phase 1: Nền tảng dự án

## Overview

Biến thư mục hiện chỉ có `docs/` thành một repo Python chạy được: có git, quản lý bí mật, database PostgreSQL, migration, kiểm thử và CI. Sau phase này mọi phase khác có chỗ đặt mã và có lệnh kiểm chứng chung.

## Key Insights

- Repo chưa có git và chưa có mã nguồn. `docs/passwordapi.txt` chứa bí mật dạng văn bản thường, nên `.gitignore` phải có trước lần `git add` đầu tiên.
- Toàn bộ hệ thống chạy trên một máy Windows, không Docker. Máy phát triển đã có dịch vụ PostgreSQL 16 và SAP GUI.
- Máy phát triển có Python 3.14. Chốt một phiên bản Python mà `pywin32` hỗ trợ.
- Cùng một gói chạy ba tiến trình `sync`, `web`, `robot` tùy lệnh khởi động.

## Requirements

- Một gói Python duy nhất tên `shoponline`, cài bằng `uv`, có CLI `shoponline <lệnh>`.
- PostgreSQL cài trực tiếp trên Windows. Máy phát triển có hai database `shoponline_dev` và `shoponline_test`; database thật `shoponline` chỉ tồn tại trên máy chạy thật (tạo ở phase 4 khi triển khai lần đầu). Migration bằng Alembic.
- Bí mật không nằm trong repo. Cấu hình đọc từ biến môi trường, có `.env.example` chỉ chứa tên biến.
- `pytest`, `ruff`, kiểm tra kiểu chạy được bằng một lệnh và chạy trong CI.
- Phần phụ thuộc `pywin32` là extra `robot`, để CI Linux không cần nó và phần còn lại vẫn test được ở đó.

## Architecture

```
shoponline/
├── pyproject.toml            # uv, ruff, pytest; extra "robot" = pywin32
├── scripts/windows/          # tạo database, đăng ký Task Scheduler, sao lưu
├── .env.example  .gitignore
├── alembic.ini  migrations/
├── config/                   # cấu hình không bí mật: popup SAP, ID màn hình
├── src/shoponline/
│   ├── config.py             # đọc biến môi trường, kiểm tra khi khởi động
│   ├── cli.py                # điểm vào: migrate, sync, web, robot
│   ├── db/                   # engine, session, models
│   ├── domain/               # đơn chung, trạng thái, giá, ánh xạ SKU
│   ├── connectors/           # shopee, lazada, tiktok
│   ├── sync/  labels/  exports/  alerts/  reconcile/
│   ├── sapjobs/              # hàng đợi (chạy được ở mọi nơi)
│   ├── saprobot/             # GUI Scripting (chỉ Windows)
│   └── web/                  # FastAPI + template
├── tests/
└── docs/  plans/
```

Thư viện: SQLAlchemy 2 + Alembic + psycopg 3, httpx, FastAPI + Jinja2, openpyxl, cryptography (mã hóa token), pytest, ruff.

## Related Code Files

- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `alembic.ini`, `migrations/env.py`
- Create: `scripts/windows/create-databases.ps1`
- Create: `src/shoponline/__init__.py`, `src/shoponline/config.py`, `src/shoponline/cli.py`, `src/shoponline/db/session.py`
- Create: `tests/test_config.py`, `tests/conftest.py`
- Create: `.github/workflows/ci.yml` (hoặc CI tương đương nơi lưu repo)
- Create: `README.md`
- Move: `docs/passwordapi.txt` ra khỏi repo, vào kho bí mật

## Implementation Steps

1. Viết `.gitignore` trước tiên: `.env*` (trừ `.env.example`), `docs/passwordapi.txt`, `*.key`, thư mục ảnh chụp màn hình robot, file Excel xuất ra, `__pycache__`, `.venv`.
2. Chuyển nội dung `docs/passwordapi.txt` vào kho bí mật mà chủ dự án chọn, rồi xóa file. Nếu file này từng được gửi qua chat hay email thì đổi mật khẩu đó.
3. Chạy `git init`, tạo nhánh `main`, kiểm tra `git status` không liệt kê file bí mật, rồi commit đầu tiên.
4. Tạo `pyproject.toml` với `uv`, khai báo phụ thuộc, extra `robot`, cấu hình `ruff` và `pytest`.
5. Viết `config.py`: một lớp cấu hình đọc biến môi trường, báo lỗi rõ tên biến thiếu khi khởi động.
6. Viết `scripts/windows/create-databases.ps1` nhận tham số môi trường (`dev` tạo `shoponline_dev` và `shoponline_test`; `prod` tạo `shoponline`) và một tài khoản database riêng cho ứng dụng trên dịch vụ PostgreSQL sẵn có; PostgreSQL chỉ nghe trên `localhost`. Trước khi chạy, kiểm tra dịch vụ PostgreSQL 16 trên máy đang được dùng cho việc gì khác để không đụng dữ liệu sẵn có.
7. Khởi tạo Alembic, một migration rỗng, lệnh `shoponline migrate`.
8. Viết `conftest.py` tạo database kiểm thử riêng và rollback sau mỗi test.
9. Viết CI: cài bằng `uv`, chạy `ruff check`, kiểm tra kiểu, `pytest` với dịch vụ PostgreSQL.
10. Viết `README.md`: yêu cầu, cách dựng môi trường, các lệnh, nơi lấy bí mật (không ghi giá trị).

## Todo

- [ ] `.gitignore` có trước lần `git add` đầu tiên
- [ ] `docs/passwordapi.txt` đã vào kho bí mật và bị xóa khỏi thư mục
- [ ] `git init` và commit đầu không chứa bí mật
- [ ] `pyproject.toml`, `uv.lock`, extra `robot`
- [ ] `config.py` và test báo lỗi khi thiếu biến
- [ ] Database `shoponline_dev`, `shoponline_test` và tài khoản ứng dụng trên máy phát triển
- [ ] Alembic và lệnh `shoponline migrate`
- [ ] CI chạy lint, kiểu, test
- [ ] `README.md`

## Success Criteria

- Trên máy Windows mới đã cài PostgreSQL, làm theo `README.md` thì `create-databases.ps1`, `shoponline migrate` và `pytest` đều chạy thành công.
- CI xanh trên commit đầu.
- `git log -p` không chứa mật khẩu, token hay khóa.

## Verification

- `git ls-files | grep -i -E "password|\.env$|\.key$"` không trả kết quả nào.
- `psql -l` trên máy phát triển liệt kê `shoponline_dev` và `shoponline_test`; test chỉ chạy khi tên database kết thúc bằng `_test` (có test kiểm tra điều này).
- `uv run pytest` và `uv run ruff check` thoát mã 0.

## Risk Assessment

- **Bí mật lọt vào lịch sử git.** Giảm thiểu bằng thứ tự bước 1–3. Nếu đã lọt thì coi bí mật đó là đã lộ và đổi ngay, không chỉ xóa file.
- **`pywin32` chưa hỗ trợ phiên bản Python đã chọn.** Kiểm tra trên máy Windows trước khi chốt phiên bản trong `pyproject.toml`.

## Rollback

Phase này chỉ tạo file mới. Hoàn tác bằng cách xóa các file vừa tạo; `docs/` không bị sửa ngoài việc gỡ file bí mật.

## Security Considerations

- Không commit `.env`, token, khóa mã hóa, mật khẩu SAP.
- Khóa mã hóa token (dùng ở phase 3) cũng là bí mật, lưu cùng kho bí mật.

## Next Steps

Phase 3 thêm schema vào `migrations/`. Phase 2 chạy song song.
