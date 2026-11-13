---
title: "Cấu hình kết nối SAP và kiểm tra kết nối trên web"
description: "Admin sửa cấu hình SAP trên web, bấm Kiểm tra để robot đăng nhập thử và báo kết quả; mật khẩu ở lại máy robot trong Windows Credential Manager."
status: in-progress
priority: P2
effort: 4d
tags: [feature, backend, database, web, robot]
blockedBy: []
blocks: []
created: 2026-11-13
---

# Cấu hình kết nối SAP và kiểm tra kết nối trên web

## Overview

Hiện 8 biến SAP nằm trong `.env` và biến môi trường của máy robot. Muốn đổi phải sửa file, khởi động lại, và chỉ biết đúng hay sai khi có việc thật. Kế hoạch này chuyển cấu hình (trừ mật khẩu) vào database, có trang web để sửa, và thêm loại việc `check_connection` để robot đăng nhập thử rồi báo kết quả về web.

Web không tự gọi SAP được: SAP GUI Scripting chỉ chạy trong phiên Windows có màn hình của robot ([session.py](../../src/shoponline/saprobot/session.py)). Vì vậy nút Kiểm tra xếp một việc vào hàng đợi `sap_job` có sẵn, và robot làm việc đó.

## Hợp đồng

- **Kết quả:** admin vào **Robot SAP → Kết nối SAP**, sửa cấu hình, bấm **Lưu và kiểm tra**, và trong khoảng 30 giây thấy kết quả: thành công (hệ thống, client, user thật của phiên, thời gian đăng nhập) hoặc lỗi tiếng Việt kèm cách sửa.
- **Ràng buộc:** chỉ robot chạm SAP. Lần kiểm tra đi qua lớp chặn T-code, `check_identity`, và đăng xuất ngay. Mật khẩu không vào database, nhật ký hay ảnh chụp. Chỉ `admin` sửa và kiểm tra. Không thêm thư viện mới (`pywin32` đã có trong extra `robot`).
- **Ngoài phạm vi:** nới danh sách T-code; nhiều hệ thống đích hoặc QA; nhập mật khẩu trên web; đổi cách deploy ngoài điều kiện bật robot.
- **Tiêu chí hoàn thành:** xem mục cuối.

## Quyết định đã chốt (2026-11-13, chủ dự án)

1. **Mật khẩu ở lại máy robot.** Lưu trong Windows Credential Manager của tài khoản chạy robot, đặt bằng `shoponline sap-password set`. Web chỉ thấy "đã có / chưa có" qua heartbeat. Biến `SHOPONLINE_SAP_PASSWORD` vẫn được đọc làm đường dự phòng. Quyết định bảo mật cũ (mật khẩu không nằm trong cấu hình dùng chung với web) được giữ nguyên.
2. **`check_connection` chạy được khi robot đang tạm dừng.** Các việc đọc báo cáo vẫn bị chặn. Kết quả kiểm tra không tăng bộ đếm lỗi liên tiếp và không tự tạm dừng robot.
3. **Đổi `SYSTEM` hoặc `CLIENT` thì phải kiểm tra thành công trước.** Đến khi có một lần `check_connection` thành công với đúng hệ thống và client mới, web không xếp việc đọc báo cáo, và robot không nhận việc nào ngoài `check_connection`.

## Kiến trúc

```
Trình duyệt ─▶ web /robot/sap-connection
                 ├─ Lưu → bảng sap_settings (một dòng, ghi nhật ký sự kiện)
                 └─ Kiểm tra → sap_job kind=check_connection
                        ▼
                   PostgreSQL ◀── robot (phiên Windows có màn hình)
                        │          • mỗi vòng: heartbeat + danh sách mục SAP Logon
                        │          • đọc sap_settings ở mỗi việc
                        │          • mật khẩu từ Credential Manager
                        ▼
                   web tự làm mới đến khi việc Xong hoặc Lỗi
```

## Phases

| # | Phase | Trạng thái | Phụ thuộc |
|---|---|---|---|
| 1 | [Bảng cấu hình SAP và heartbeat](phase-01-sap-settings-store.md) | completed | — |
| 2 | [Robot: mật khẩu, heartbeat, việc kiểm tra](phase-02-robot-check-connection.md) | completed | 1 |
| 3 | [Trang web Kết nối SAP](phase-03-web-sap-connection-page.md) | completed | 1, 2 |
| 4 | [Deploy, tài liệu và chạy thử trên Production](phase-04-ops-docs-and-live-check.md) | in-progress | 1–3 |

Các phase làm tuần tự: phase 2 và 3 cùng sửa `sapjobs/queue.py` và cùng phụ thuộc hợp đồng của phase 1.

## Tiêu chí hoàn thành

1. Đổi user, mục SAP Logon hoặc ngôn ngữ trên web thì việc kế tiếp của robot dùng giá trị mới, không cần khởi động lại web hay robot.
2. Bấm Kiểm tra: thành công hiện hệ thống/client/user của phiên. Mật khẩu sai, mục SAP Logon không có, SAP Logon chưa bật scripting, sai hệ thống, hoặc có phiên lạ đang mở: mỗi trường hợp ra đúng thông báo riêng. Có test cho từng trường hợp bằng engine giả.
3. Robot tắt: web báo "Robot không chạy" khi heartbeat cũ hơn 30 giây, việc kiểm tra không treo im lặng.
4. Robot đang tạm dừng vẫn chạy được `check_connection`; việc đọc báo cáo vẫn nằm chờ.
5. Đổi `SYSTEM` hoặc `CLIENT`: nút xếp việc đọc báo cáo bị khóa kèm lý do, robot không nhận việc đọc báo cáo, cho đến khi kiểm tra thành công đúng hệ thống mới.
6. Nhật ký sự kiện ghi ai đổi trường nào, lúc nào (không ghi mật khẩu vì web không có nó).
7. `uv run pytest` và `uv run ruff check` thoát mã 0. Máy hiện tại đang chạy với `.env` cũ vẫn chạy tiếp sau deploy mà không cần sửa gì.
8. Chạy thử trên `AEP`/300 thành công một lần, và thất bại có chủ đích một lần (mục SAP Logon sai).

## Rủi ro chính

- **Phân loại lỗi đăng nhập dựa vào thông báo SAP.** Mã thông báo cho "sai mật khẩu" và "user bị khóa" phải đối chiếu trên `AEP` ở phase 4; nếu không khớp thì vẫn hiện nguyên văn thông báo SAP.
- **Credential Manager theo từng tài khoản Windows.** Lệnh `sap-password set` phải chạy dưới đúng tài khoản chạy robot (`luanh` trên máy hiện tại, `saprobot` trên máy riêng).
- **Việc kiểm tra phải chờ việc đang chạy.** Robot làm từng việc một; nếu đang đọc báo cáo thì trang hiện "đang chờ robot xong việc #N".
