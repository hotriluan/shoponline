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

## Red Team Review

Red team nhẹ: chỉ mất/trùng dữ liệu (quyết định 2026-11-23). Một người soi, lens trùng/sót dữ liệu, chỉ hai câu: hai bản chạy cùng lúc, và chuyển máy có đủ dữ liệu cấu hình không. Số đếm là dev DB, 2026-11-23. Chi tiết: [báo cáo](../reports/data-integrity-audit-261123-1320-deletion-machine.md).

| # | Phát hiện | Mức | Bằng chứng trong mã | Disposition | Hướng xử lý |
|---|-----------|-----|---------------------|-------------|-------------|
| 1 | Chỉ đổi `system`/`client` mới xóa trạng thái đã kiểm tra. Đổi user SAP không buộc kiểm tra lại, nên robot có thể đọc zrsd001/zrsd004 bằng user kém quyền (SAP trả ít dòng, không báo lỗi) và file kế toán thiếu DO. Chưa tái hiện (cần SAP thật) | Low | `sapjobs/sap_settings.py:225-227`; `saprobot/worker.py:303` | Accept (chủ dự án duyệt 2026-11-23) | Xóa trạng thái đã kiểm tra cả khi `sap_user` đổi, hoặc ghi vào docs rằng đổi user phải bấm Kiểm tra |
| 2 | Việc đã xếp cho hệ thống cũ sau khi đổi `system`/`client`: robot không chạy mà đánh FAILED, đơn không mất, người dùng xếp lại | Low | `saprobot/worker.py:305-318` | Reject (đã kiểm: không mất hay trùng dữ liệu; lỗi hiện rõ trên trang việc) | Không đổi |
| 3 | `check_connection` bị cắt ngang giữ khóa chống trùng và chặn nút Kiểm tra | Low | `sapjobs/queue.py:34,231-232`: `CHECK_CONNECTION` nằm trong `READ_KINDS` nên về PENDING khi robot khởi động | Reject (đã kiểm: tự chạy lại, không treo) | Không đổi |
| 4 | Hai robot cùng một DB: khóa tư vấn Postgres giữ bằng một kết nối không kiểm tra lại (xem phát hiện 9 của báo cáo) | Low | `saprobot/worker.py:484-495`, `:504-526`; `sapjobs/queue.py:119` (`SKIP LOCKED`) cho phép hai robot nhận việc khác nhau, không trùng việc | Accept (chủ dự án duyệt 2026-11-23) | Kiểm kết nối khóa trong vòng lặp robot |
| 5 | Cấu hình SAP đi theo bản sao lưu (cùng `sap_settings`); mật khẩu ở lại máy robot nên máy mới phải đặt lại, không trùng và không sót dữ liệu | Low | `sapjobs/sap_settings.py:105-127`, `:141-150`; dev: 1 dòng `sap_settings`, `password_present` do robot báo | Reject (đã kiểm: thiết kế đã chốt, quyết định 1) | Không đổi |

## Validation Log

Validate nhẹ ngày 2026-11-23: chỉ các tiêu chí liên quan hai câu hai bản chạy và chuyển máy. Không hỏi chủ dự án trong lượt này.

### Tiêu chí hoàn thành (phạm vi rút gọn)

| # | Tiêu chí | Kết quả | Bằng chứng |
|---|----------|---------|------------|
| 4 | Robot tạm dừng vẫn chạy `check_connection`; việc đọc báo cáo nằm chờ | VERIFIED (mã) | `saprobot/worker.py:303-304` (`CHECK_ONLY` khi tạm dừng hoặc chưa kiểm tra) |
| 5 | Đổi `SYSTEM`/`CLIENT` thì khóa việc đọc cho tới khi kiểm tra thành công đúng hệ thống mới | VERIFIED (mã) | `sapjobs/sap_settings.py:225-227`, `:234-243` (`mark_verified` chỉ nhận đúng mục tiêu hiện tại); `worker.py:305-318` |
| 7 | Máy đang chạy với `.env` cũ vẫn chạy tiếp sau deploy | VERIFIED một phần | `sap_settings.py:105-127` chép biến môi trường vào DB và coi là đã kiểm tra; không kiểm được trên production |
| 8 | Chạy thử trên `AEP`/300 thành công một lần và thất bại có chủ đích một lần | VERIFIED (dev) | Dev: 4 việc `check_connection` DONE và 1 FAILED (2026-11-13 tới 2026-11-16) |
| - | Chỉ một robot chạm SAP tại một thời điểm | VERIFIED với một rủi ro | Khóa tư vấn mỗi DB (`worker.py:484-495`); máy cũ `Alkana_IT` có 5 tác vụ `shoponline-*` ở trạng thái Disabled (kiểm 2026-11-23); `robot_control.robot_host = AlkanaDuongPC` (dev DB). Rủi ro: phát hiện 4 |

### Giả định đang dùng

| # | Giả định | Kết quả | Bằng chứng |
|---|----------|---------|------------|
| 1 | Mật khẩu không vào DB, nhật ký hay ảnh chụp, nên bản sao lưu không mang mật khẩu | VERIFIED (mã) | `sap_settings.py` không có cột mật khẩu; `RobotControl.password_present` chỉ là cờ (`db/models.py:305-306`) |
| 2 | Việc đọc báo cáo chạy lại sau khi robot bị cắt ngang không làm trùng dữ liệu | UNVERIFIED | `sapjobs/queue.py:222-239` đưa việc đọc về PENDING; tính chống trùng của lần nhập lại thuộc kiểm tra phase 2 và 4 của đợt rà soát |

### Câu hỏi cho chủ dự án

1. Phát hiện 1: đổi user SAP có cần buộc kiểm tra lại như đổi hệ thống/client không?
