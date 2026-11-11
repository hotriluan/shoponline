---
title: "Phase 5: Khung robot và đọc báo cáo SAP"
status: todo
priority: P1
effort: 6d
dependencies: [4]
---

# Phase 5: Khung robot và đọc báo cáo SAP

## Overview

Xây hàng đợi việc SAP trong PostgreSQL và khung robot GUI Scripting: quản lý phiên, đọc thanh trạng thái, xử lý popup, chụp màn hình khi lỗi, công tắc dừng. Phase này chỉ đọc: robot tự chạy `zrsd001` và `zrsd004` thay cho việc admin tải file lên. Chưa ghi chứng từ nào.

## Key Insights

- Màn hình lọc `zrsd001` (`docs/zrsd001filter.png`): Sales Organization `1000`, Sales Office `1401`, Document Date từ–đến, Sold-To Party, Purchase Order No., và lựa chọn "Open Sales Order" hoặc "Complete".
- Tra SO theo mã đơn làm được bằng chính `zrsd001` với ô "Purchase Order No.", chạy hai lần với "Open" và "Complete". Không cần thêm T-code tra cứu.
- Màn hình lọc `zrsd004` chưa có ảnh; lấy khi ghi recorder.
- Công ty có cả QA lẫn hệ thống thật. Robot ghi nhầm hệ thống là lỗi nặng nhất, nên hệ thống đích là một phần của từng việc, và được kiểm tra ngay cả với việc đọc.
- Robot cần phiên Windows có màn hình, nên chạy trong phiên đăng nhập của tài khoản robot; `web` chạy nền.
- ID phần tử màn hình và danh sách popup là cấu hình lấy từ bản ghi recorder, không viết cứng trong mã.

## Requirements

- Hàng đợi `sap_job`, nhận việc bằng `SELECT … FOR UPDATE SKIP LOCKED`; một robot nhận việc tại một thời điểm.
- Trạng thái việc: `PENDING`, `RUNNING`, `DONE`, `FAILED`, `UNKNOWN`, `NEED_REVIEW`.
- Mỗi việc ghi hệ thống đích (tên hệ thống, client). Trước mỗi việc robot đọc tên hệ thống, client, user của phiên đang mở; không khớp thì từ chối và cảnh báo.
- Sau mỗi bước đọc thanh trạng thái. Popup không có trong danh sách đã biết thì không bấm gì, chụp màn hình, chuyển `NEED_REVIEW`.
- Phát hiện phiên bị ngắt hoặc đăng xuất, đăng nhập lại.
- Tự dừng khi số lỗi liên tiếp vượt ngưỡng; chỉ `admin` bật lại.
- Kết quả đọc báo cáo đi qua đúng các hàm của phase 4 (`so_link`, `accounting_workbook`), cho cùng kết quả như khi tải file lên.
- Sau khi admin xác nhận lô, hệ thống tự xếp việc đọc `zrsd001`. Vào ngày goods issue, admin bấm "xuất file gửi kế toán" và hệ thống xếp việc đọc `zrsd004`.
- Đường tải file lên của phase 4 vẫn giữ, dùng khi robot dừng.

## Architecture

```
sapjobs/queue.py             enqueue (có khóa chống trùng), claim, complete, mark_unknown
saprobot/session.py          chọn đúng connection/session theo hệ thống, client, user
saprobot/statusbar.py        đọc loại và nội dung thông báo
saprobot/popups.py           nhận diện cửa sổ phụ, tra config/sap_popups.yaml
saprobot/screen.py           truy cập phần tử theo ID từ config/sap_screens.yaml
saprobot/evidence.py         chụp màn hình khi lỗi
saprobot/worker.py           vòng lặp: công tắc → claim → chạy → ghi kết quả
saprobot/transactions/read_zrsd001.py
saprobot/transactions/read_zrsd004.py
```

**Lấy dữ liệu báo cáo.** Ưu tiên đọc thẳng lưới kết quả trên màn hình (số dòng, giá trị từng ô theo tên cột), vì không phụ thuộc hộp thoại lưu file của Windows. Nếu lưới không đọc được bằng scripting thì dùng chức năng xuất Excel của báo cáo ra một thư mục cố định rồi đọc bằng bộ đọc của phase 4. Chọn cách nào được quyết định khi ghi recorder và ghi vào `docs/robot-runbook.md`.

Robot là tác vụ Task Scheduler chạy khi tài khoản robot đăng nhập; trước khi khởi động kiểm tra chưa có tiến trình robot nào đang chạy.

## Related Code Files

- Create: `src/shoponline/sapjobs/queue.py`, `migrations/versions/<rev>_sap_job.py`
- Create: `src/shoponline/saprobot/session.py`, `statusbar.py`, `popups.py`, `screen.py`, `evidence.py`, `worker.py`
- Create: `src/shoponline/saprobot/transactions/read_zrsd001.py`, `read_zrsd004.py`
- Create: `config/sap_popups.yaml`, `config/sap_screens.yaml`
- Create: `docs/sap-recordings/` (bản ghi recorder đã gỡ dữ liệu khách), `docs/robot-machine-setup.md`, `docs/robot-runbook.md`
- Modify: `src/shoponline/cli.py` (lệnh `robot`, `robot-pause`, `robot-resume`), `web/routes/` (màn hình hàng đợi, ảnh lỗi, công tắc), `scripts/windows/register-tasks.ps1`
- Create: `tests/sapjobs/test_queue.py`, `tests/saprobot/`

## Implementation Steps

1. Chủ dự án chuẩn bị: văn bản chấp thuận, user robot trên QA và hệ thống thật, cấu hình máy theo `robot-machine-setup.md` (độ phân giải cố định, tắt khóa màn hình và ngủ, tự đăng nhập tài khoản robot, bật SAP GUI Scripting, tắt hai ô thông báo script, ngôn ngữ đăng nhập SAP cố định).
2. Chủ dự án ghi recorder trên QA bằng user robot cho `zrsd001` (cả "Open" và "Complete") và `zrsd004`, kèm ảnh mọi màn hình và popup.
3. Viết `queue.py`. Test: hai tiến trình không nhận trùng việc; xếp hai việc cùng khóa thì việc thứ hai bị từ chối.
4. Viết `session.py`, `statusbar.py`, `popups.py`, `screen.py`, `evidence.py`. Phần logic test được với lớp thực thi giả trên máy không có SAP.
5. Viết `read_zrsd001.py` và `read_zrsd004.py` từ bản ghi recorder.
6. Viết `worker.py` với công tắc dừng và kiểm tra hệ thống đích.
7. Thêm màn hình hàng đợi: danh sách việc, ảnh lỗi, nút thử lại cho việc đọc, nút tạm dừng và bật lại robot.
8. Chạy trên QA: 50 việc đọc liên tiếp; rút mạng giữa chừng; đặt hệ thống đích khác phiên đang mở và xác nhận robot từ chối.
9. Triển khai lên máy chạy thật ở chế độ chỉ đọc. Trong 5 ngày làm việc, admin vẫn tải file lên song song; so kết quả robot đọc với file tải lên.
10. Đo thời gian một lần đọc báo cáo và ghi vào `docs/robot-runbook.md`.

## Todo

- [ ] Chấp thuận, user robot, máy robot
- [ ] Bản ghi recorder `zrsd001`, `zrsd004`
- [ ] Hàng đợi và test nhận việc đồng thời
- [ ] Phiên, thanh trạng thái, popup, chụp màn hình
- [ ] Đọc `zrsd001` và `zrsd004`
- [ ] Worker, công tắc dừng, kiểm tra hệ thống đích
- [ ] Màn hình hàng đợi
- [ ] 50 việc đọc trên QA và thử ngắt mạng
- [ ] 5 ngày so robot với file tải lên trên hệ thống thật
- [ ] Sổ tay robot

## Success Criteria

- 5 ngày làm việc liên tiếp, dữ liệu robot đọc giống hệt file admin tải lên.
- Rút mạng hoặc đóng SAP GUI giữa chừng: robot không treo, việc về đúng trạng thái, có ảnh và cảnh báo.
- Việc nhắm vào QA không chạy trên phiên hệ thống thật và ngược lại.

## Verification

- `uv run pytest tests/sapjobs tests/saprobot` thoát mã 0 trên máy không có SAP.
- Biên bản chạy thử ghi trong `docs/robot-runbook.md`.

## Risk Assessment

- **Màn hình khác bản ghi recorder.** Ghi recorder bằng user robot, cùng độ phân giải, ngôn ngữ và phiên bản SAP GUI với máy chạy thật.
- **Phiên bị khóa khi ngắt điều khiển từ xa.** Kiểm tra ở bước 8; nếu không giữ được phiên thì máy cần màn hình thật hoặc màn hình ảo.
- **Báo cáo trả quá nhiều dòng.** Luôn lọc theo ngày chứng từ và khách hàng SAP của sàn.

## Rollback

Robot chỉ đọc. Tắt tiến trình `robot` và quay lại tải file lên.

## Security Considerations

- Mật khẩu SAP của robot đọc từ kho bí mật trên máy robot, không nằm trong database hay nhật ký.
- Ảnh chụp màn hình có thể chứa dữ liệu khách; lưu trong thư mục giới hạn quyền, có thời hạn xóa.
- User robot chỉ có quyền các T-code cần dùng.

## Next Steps

Phase 6 thêm thao tác tạo SO lên khung này.
