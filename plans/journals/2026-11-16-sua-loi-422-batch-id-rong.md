---
title: Sửa lỗi 422 khi lọc khách hàng không chọn lô
date: 2026-11-16
summary: Ô "— theo sàn —" gửi batch_id rỗng, FastAPI từ chối vì kiểu int; đổi sang nhận chuỗi
---

# Sửa lỗi 422 khi lọc khách hàng không chọn lô

## What happened
Trang **Khách hàng** trả `{"detail":[{"type":"int_parsing","loc":["query","batch_id"],"input":""}]}`. Form lọc là `method="get"`, lựa chọn "— theo sàn —" có `value=""` nên URL thành `/customers?batch_id=&platform=...`. FastAPI chỉ coi chuỗi rỗng là "không có" với trường form (body), còn với query thì vẫn parse `int | None` và báo 422.

## Decision
Đổi tham số query `batch_id` của `GET /customers` và `GET /sap-reports` sang `str = ""`, chỉ lấy lô khi `batch_id.strip().isdigit()` — giống cách `robot.py` đã làm với form robot. Các route POST giữ nguyên vì trường form rỗng đã được FastAPI xử lý.

Test hồi quy `test_filter_forms_accept_the_empty_batch_choice` trong `tests/web/test_web_flow.py`: chạy trên code cũ ra 422, trên code mới qua. Toàn bộ `pytest` 368 passed, `ruff check` sạch.

## Next steps
Deploy cùng lần tới.
