---
title: "Phase 5: Khung robot và đọc báo cáo SAP trên Production"
status: in-progress
priority: P1
effort: 6d
dependencies: [4]
---

# Phase 5: Khung robot và đọc báo cáo SAP trên Production

## Overview

Xây hàng đợi việc SAP trong PostgreSQL và khung robot GUI Scripting: quản lý phiên, đọc thanh trạng thái, xử lý popup, chụp màn hình khi lỗi, công tắc dừng, và lớp chặn T-code. Robot tự chạy `zrsd001` và `zrsd004` trên Production thay cho việc admin tải file lên. Robot chỉ đọc; dự án không có việc nào ghi vào SAP và không dùng QA.

## Key Insights

- Màn hình lọc `zrsd001` (`docs/zrsd001filter.png`): Sales Organization `1000`, Sales Office `1401`, Document Date từ–đến, Sold-To Party, Purchase Order No., và lựa chọn "Open Sales Order" hoặc "Complete".
- Tra SO theo mã đơn làm được bằng chính `zrsd001` với ô "Purchase Order No.", chạy hai lần với "Open" và "Complete". Không cần thêm T-code tra cứu.
- Robot làm thẳng trên Production vì nó chỉ đọc. Hệ thống đích vẫn là một phần của từng việc và được kiểm tra trước mỗi việc, để robot không chạy nhầm trên phiên của hệ thống khác.
- User robot được IT cấp quyền vào `zrsd001` và `zrsd004`, nhưng role có thể rộng hơn. Vì vậy việc "chỉ vào hai báo cáo" được bảo đảm bằng lớp chặn T-code trong mã, và lớp chặn phải có trước lần chạy đầu tiên trên Production.
- Báo cáo ALV trên Production có thể tự chuyển sang T-code khác, ví dụ bấm đúp vào dòng mở VA03 hoặc VA02. Vì vậy lớp chặn phải kiểm tra cả *sau* mỗi thao tác, không chỉ lúc mở T-code.
- Production là `AEP`, client 300 (`SHOPONLINE_SAP_SYSTEM=AEP`, `SHOPONLINE_SAP_CLIENT=300`). User robot là `AL17016`, chỉ dành cho robot. Không dùng `BASIS01`: mật khẩu user Basis sẽ nằm trên máy robot, và `ensure_session` sẽ nhận cả phiên do người mở nếu cùng user.
- Giá trị `Info.Transaction` đã thấy (System → Status, ngày 2026-11-12): menu chính `SESSION_MANAGER` (`SAPLSMTR_NAVIGATION`, màn hình 100); `ZRSD001` ở màn hình lọc (`ZRSD00B`, 1000) và màn hình kết quả (`SAPLSLVC_FULLSCREEN`, 500); `ZRSD004` ở màn hình lọc (`ZRSD00F`, 1000) và màn hình kết quả (`SAPLSLVC_FULLSCREEN`, 500). Màn hình đăng nhập: `S000` (`SAPMSYST`, màn hình 20; client hiện `000` trước khi đăng nhập). Danh sách được phép vì vậy là `S000`, `SESSION_MANAGER`, `ZRSD001`, `ZRSD004`. `AL17016` không có start transaction.
- `AL17016` mở được `VA02` (kiểm ngày 2026-11-12), tức là role phía SAP không chặn việc sửa SO. Lớp chặn T-code là hàng rào duy nhất phía robot, nên bước 9 (cổng trước lần chạy đầu) là bắt buộc.
- Kết quả của cả hai báo cáo là lưới ALV toàn màn hình (`SAPLSLVC_FULLSCREEN`), nên đọc thẳng lưới bằng scripting là hướng chính. Bấm đúp vào số SO hoặc số DO trên lưới có thể mở T-code khác; robot không bấm đúp, và lớp chặn bắt nếu điều đó xảy ra.
- Màn hình lọc `zrsd001`: Sales Organization `1000`, Sales Office `1401`, Document Date, Sold-To Party `1200001145`, lựa chọn "Complete". Màn hình lọc `zrsd004`: Sales Organization `1000`, Sold-to Party, Actual GI. Nút lưu trên màn hình lọc là lưu variant; robot không dùng variant và phím lưu luôn bị cấm.
- Robot cần phiên Windows có màn hình, nên chạy trong phiên đăng nhập của tài khoản robot; `web` chạy nền.
- ID phần tử màn hình và danh sách popup là cấu hình lấy từ bản ghi recorder, không viết cứng trong mã.

## Requirements

- Hàng đợi `sap_job`, nhận việc bằng `SELECT … FOR UPDATE SKIP LOCKED`; một robot nhận việc tại một thời điểm.
- Trạng thái việc: `PENDING`, `RUNNING`, `DONE`, `FAILED`, `UNKNOWN`, `NEED_REVIEW`.
- Mỗi việc ghi hệ thống đích (tên hệ thống, client). Trước mỗi việc robot đọc tên hệ thống, client, user của phiên đang mở; không khớp thì từ chối và cảnh báo.
- **Lớp chặn T-code**, điều kiện trước lần chạy đầu tiên trên Production:
  - Mọi thao tác với SAP GUI đi qua một lớp bọc phiên duy nhất. Thao tác trong `transactions/`, xử lý popup và chụp màn hình chỉ nhận phiên đã bọc.
  - Danh sách T-code được phép nằm cứng trong mã, không nằm trong YAML: `ZRSD001`, `ZRSD004`, màn hình đăng nhập và menu chính. Tên kỹ thuật chính xác của hai màn hình sau lấy từ bản ghi recorder.
  - Chỉ mở được T-code nằm trong danh sách; không có đường nào khác ghi vào ô lệnh `okcd`.
  - Trước và sau mỗi thao tác (gõ chữ, bấm nút, gửi phím, trả lời popup), robot đọc `session.Info.Transaction`. Nếu T-code nằm ngoài danh sách, robot không bấm gì thêm, chụp màn hình, chuyển việc sang `FAILED` và tự tạm dừng. Chỉ `admin` bật lại được.
  - Chỉ gửi được các phím đã liệt kê (Enter, F8, cùng các phím mà bản ghi recorder cần). Phím lưu (`sendVKey 11`) luôn bị cấm.
- Sau mỗi bước đọc thanh trạng thái. Popup không có trong danh sách đã biết thì không bấm gì, chụp màn hình, chuyển `NEED_REVIEW`.
- Phát hiện phiên bị ngắt hoặc đăng xuất, đăng nhập lại.
- Tự dừng khi số lỗi liên tiếp vượt ngưỡng; chỉ `admin` bật lại.
- Báo cáo luôn được lọc theo ngày chứng từ và theo khách hàng SAP của sàn, để không tạo tải nặng cho Production.
- Kết quả đọc báo cáo đi qua đúng các hàm của phase 4 (`so_link`, `accounting_workbook`), cho cùng kết quả như khi tải file lên.
- Sau khi admin xác nhận lô, hệ thống tự xếp việc đọc `zrsd001`. Vào ngày goods issue, admin bấm "xuất file gửi kế toán" và hệ thống xếp việc đọc `zrsd004`.
- Đường tải file lên của phase 4 vẫn giữ, dùng khi robot dừng.

## Architecture

```
sapjobs/queue.py             enqueue (có khóa chống trùng), claim, complete, mark_unknown
saprobot/guard.py            lớp bọc phiên: danh sách T-code và phím được phép, kiểm tra trước và sau mỗi thao tác
saprobot/session.py          chọn đúng connection/session theo hệ thống, client, user
saprobot/statusbar.py        đọc loại và nội dung thông báo
saprobot/popups.py           nhận diện cửa sổ phụ, tra config/sap_popups.yaml
saprobot/screen.py           truy cập phần tử theo ID từ config/sap_screens.yaml
saprobot/evidence.py         chụp màn hình khi lỗi
saprobot/worker.py           vòng lặp: công tắc → claim → kiểm tra hệ thống → bọc phiên → chạy → ghi kết quả
saprobot/transactions/read_zrsd001.py
saprobot/transactions/read_zrsd004.py
```

`worker.py` bọc phiên ngay sau `ensure_session` và chỉ đưa phiên đã bọc vào `JobContext`. T-code lạ dẫn tới cùng cách xử lý như `WrongSystem`: việc `FAILED` và robot tạm dừng.

**Lấy dữ liệu báo cáo.** Ưu tiên đọc thẳng lưới kết quả trên màn hình (số dòng, giá trị từng ô theo tên cột), vì không phụ thuộc hộp thoại lưu file của Windows. Nếu lưới không đọc được bằng scripting thì dùng chức năng xuất Excel của báo cáo ra một thư mục cố định rồi đọc bằng bộ đọc của phase 4. Chọn cách nào được quyết định khi ghi recorder và ghi vào `docs/robot-runbook.md`. Nếu xuất Excel cần phím hoặc T-code phụ, thêm vào danh sách được phép trong mã kèm test.

Robot là tác vụ Task Scheduler chạy khi tài khoản robot đăng nhập; trước khi khởi động kiểm tra chưa có tiến trình robot nào đang chạy.

## Related Code Files

- Create: `src/shoponline/sapjobs/queue.py`, `migrations/versions/<rev>_sap_job.py`
- Create: `src/shoponline/saprobot/session.py`, `statusbar.py`, `popups.py`, `screen.py`, `evidence.py`, `worker.py`
- Create: `src/shoponline/saprobot/guard.py`, `tests/saprobot/test_guard.py`
- Modify: `src/shoponline/saprobot/screen.py` (`start_transaction` chuyển vào lớp chặn), `worker.py` (bọc phiên), `config/sap_screens.yaml` (chú thích ghi recorder trên Production)
- Create: `src/shoponline/saprobot/transactions/read_zrsd001.py`, `read_zrsd004.py`
- Create: `config/sap_popups.yaml`, `config/sap_screens.yaml`
- Create: `docs/sap-recordings/` (bản ghi recorder đã gỡ dữ liệu khách), `docs/robot-machine-setup.md`, `docs/robot-runbook.md`
- Modify: `docs/robot-machine-setup.md`, `docs/robot-runbook.md` (ví dụ hệ thống đích đổi từ QA sang Production; mục lớp chặn T-code)
- Modify: `src/shoponline/cli.py` (lệnh `robot`, `robot-pause`, `robot-resume`), `web/routes/` (màn hình hàng đợi, ảnh lỗi, công tắc), `scripts/windows/register-tasks.ps1`
- Create: `tests/sapjobs/test_queue.py`, `tests/saprobot/`

## Implementation Steps

1. Chủ dự án chuẩn bị: user robot trên Production, cấu hình máy theo `robot-machine-setup.md` (độ phân giải cố định, tắt khóa màn hình và ngủ, tự đăng nhập tài khoản robot, bật SAP GUI Scripting, tắt hai ô thông báo script, ngôn ngữ đăng nhập SAP cố định).
2. Chủ dự án ghi recorder trên Production bằng user robot cho `zrsd001` (cả "Open" và "Complete") và `zrsd004`, kèm ảnh mọi màn hình và popup. Chỉ chạy báo cáo, không bấm đúp vào dòng kết quả. Ghi lại `Info.Transaction` của màn hình đăng nhập và menu chính.
3. Viết `queue.py`. Test: hai tiến trình không nhận trùng việc; xếp hai việc cùng khóa thì việc thứ hai bị từ chối.
4. Viết `session.py`, `statusbar.py`, `popups.py`, `screen.py`, `evidence.py`. Phần logic test được với lớp thực thi giả trên máy không có SAP.
5. Viết `guard.py` và nối vào `worker.py`. Test với SAP GUI giả:
   - mở T-code ngoài danh sách bị từ chối, và không có gì được ghi vào `okcd`;
   - một thao tác làm phiên chuyển sang `VA02` thì robot dừng ngay, việc `FAILED`, robot tạm dừng, có ảnh chụp;
   - một popup trả lời xong mà phiên chuyển sang T-code lạ cũng bị bắt;
   - `sendVKey 11` và phím ngoài danh sách bị từ chối;
   - test quét mã nguồn: ngoài `guard.py`, không chỗ nào trong `saprobot/` ghi `okcd` hoặc nhận phiên gốc.
6. Viết `read_zrsd001.py` và `read_zrsd004.py` từ bản ghi recorder, chỉ qua phiên đã bọc.
7. Viết `worker.py` với công tắc dừng và kiểm tra hệ thống đích.
8. Thêm màn hình hàng đợi: danh sách việc, ảnh lỗi, nút thử lại cho việc đọc, nút tạm dừng và bật lại robot.
9. Cổng trước lần chạy đầu tiên: `uv run pytest tests/saprobot` thoát mã 0, gồm toàn bộ test lớp chặn ở bước 5. Chủ dự án xác nhận danh sách T-code được phép khớp bản ghi recorder.
10. Chạy trên Production ngoài giờ cao điểm: 50 việc đọc liên tiếp; rút mạng giữa chừng; đặt hệ thống đích khác phiên đang mở và xác nhận robot từ chối. Các thử nghiệm này an toàn trên Production vì robot chỉ đọc.
11. Chạy song song 5 ngày làm việc: admin vẫn tải file lên; so kết quả robot đọc với file tải lên.
12. Đo thời gian một lần đọc báo cáo và ghi vào `docs/robot-runbook.md`.

## Todo

- [ ] User robot trên Production, máy robot
- [ ] Bản ghi recorder `zrsd001`, `zrsd004` trên Production
- [x] Hàng đợi và test nhận việc đồng thời
- [x] Phiên, thanh trạng thái, popup, chụp màn hình (logic test với SAP GUI giả; chưa chạy trên SAP thật)
- [x] Lớp chặn T-code và test (`guard.py`, nối vào `worker.py` và đăng nhập; cổng bước 9 còn chờ chủ dự án xác nhận danh sách khớp bản ghi recorder)
- [ ] Đọc `zrsd001` và `zrsd004` (chờ bản ghi recorder; kết quả đọc đã nối vào hàm nhập của phase 4)
- [x] Worker, công tắc dừng, kiểm tra hệ thống đích, một robot duy nhất (khóa advisory PostgreSQL)
- [x] Màn hình hàng đợi; xếp việc khi xác nhận lô và khi bấm xuất file kế toán (chỉ khi đặt `SHOPONLINE_SAP_SYSTEM`)
- [x] Tài liệu robot đổi ví dụ từ QA sang Production (`AEP`/300, `AL17016`); thêm mục lớp chặn T-code
- [ ] 50 việc đọc trên Production và thử ngắt mạng
- [ ] 5 ngày so robot với file tải lên trên Production
- [ ] Sổ tay robot (đã có `docs/robot-runbook.md` và `docs/robot-machine-setup.md`; còn phần từ recorder và biên bản chạy thử)

## Success Criteria

- Robot không vào được T-code nào ngoài danh sách được phép; gặp T-code lạ thì dừng, chụp màn hình và tự tạm dừng.
- 5 ngày làm việc liên tiếp, dữ liệu robot đọc giống hệt file admin tải lên.
- Rút mạng hoặc đóng SAP GUI giữa chừng: robot không treo, việc về đúng trạng thái, có ảnh và cảnh báo.
- Việc nhắm vào một hệ thống không chạy trên phiên của hệ thống khác.

## Verification

- `uv run pytest tests/sapjobs tests/saprobot` thoát mã 0 trên máy không có SAP.
- Biên bản chạy thử ghi trong `docs/robot-runbook.md`.

## Risk Assessment

- **Robot vào T-code ghi chứng từ.** Lớp chặn kiểm tra trước và sau mỗi thao tác. Lớp chặn không ngăn được người đăng nhập bằng tay với user robot; khuyến nghị IT giới hạn role của user robot.
- **Robot đọc sai làm file gửi kế toán sai.** Chạy song song 5 ngày; đường tải tay giữ làm đường lùi.
- **Màn hình khác bản ghi recorder.** Ghi recorder bằng user robot, cùng độ phân giải, ngôn ngữ và phiên bản SAP GUI với máy chạy thật.
- **Phiên bị khóa khi ngắt điều khiển từ xa.** Kiểm tra ở bước 10; nếu không giữ được phiên thì máy cần màn hình thật hoặc màn hình ảo.
- **Báo cáo trả quá nhiều dòng hoặc làm chậm Production.** Luôn lọc theo ngày chứng từ và khách hàng SAP của sàn; chạy thử ngoài giờ cao điểm.

## Rollback

Robot chỉ đọc. Tắt tiến trình `robot` và quay lại tải file lên.

## Security Considerations

- Mật khẩu SAP của robot đọc từ kho bí mật trên máy robot, không nằm trong database hay nhật ký.
- Ảnh chụp màn hình có thể chứa dữ liệu khách; lưu trong thư mục giới hạn quyền, có thời hạn xóa.
- Robot chỉ vào `ZRSD001` và `ZRSD004`, do lớp chặn T-code bảo đảm. Khuyến nghị thêm: IT giới hạn role của user robot chỉ gồm hai báo cáo này.
- Tài khoản Windows của robot không dùng cho việc khác, để giảm khả năng có người đăng nhập SAP bằng tay với user robot.

## Next Steps

Phase 9 (vận hành và bàn giao). Phase 6–8 (robot ghi SAP) đã bỏ ngày 2026-11-12.
