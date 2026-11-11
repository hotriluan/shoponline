---
title: "Phase 6: Hàng đợi SAP và khung robot"
status: todo
priority: P1
effort: 6d
dependencies: [2, 3]
---

# Phase 6: Hàng đợi SAP và khung robot

## Overview

Xây hàng đợi công việc SAP trong PostgreSQL và khung robot GUI Scripting trên máy Windows: quản lý phiên, đọc thanh trạng thái, xử lý popup, chụp màn hình khi lỗi, công tắc dừng khẩn cấp. Phase này chỉ làm các thao tác đọc (tìm SO, đọc SO, đọc tồn kho). Chưa ghi chứng từ nào.

Ứng với V2 mục 2.2, 2.3, mục 5 (quy tắc xử lý lỗi) và mục 11.

## Key Insights

- Điểm nguy hiểm nhất của robot GUI là không biết thao tác tạo vừa rồi đã thành công hay chưa (mất phiên giữa chừng). Vì vậy việc tạo chứng từ có một trạng thái riêng là "chưa rõ", và từ đó chỉ được đi tiếp sau khi tra SAP.
- Một phiên GUI dùng cho mọi việc, nên chỉ một robot nhận việc tại một thời điểm.
- Công ty có cả hệ thống QA lẫn hệ thống thật, và cả hai mở được trên cùng một máy. Robot ghi nhầm hệ thống là lỗi nghiêm trọng nhất có thể xảy ra, nên hệ thống đích là một phần của từng việc chứ không phải cấu hình ngầm.
- Sản lượng khoảng 24 đơn/ngày tương đương khoảng 150 thao tác GUI mỗi ngày. Ngày cao điểm là 100 đơn, tức khoảng 600 thao tác; ở mức một phút mỗi thao tác thì một phiên cần khoảng 10 giờ. Vì vậy số thao tác mỗi đơn phải được giữ thấp: tồn kho đọc một lần cho mỗi mã vật tư rồi dùng lại trong thời hạn đệm, không đọc lại cho từng đơn.
- Máy phát triển làm việc với QA; máy chạy thật làm việc với hệ thống thật. Kiểm tra hệ thống đích vẫn giữ vì cấu hình có thể bị đặt sai.
- Robot cần phiên Windows có màn hình, nên nó chạy trong phiên đăng nhập của tài khoản robot; `sync` và `web` thì chạy nền không cần đăng nhập.
- ID phần tử màn hình và danh sách popup khác nhau theo cấu hình công ty, nên chúng là cấu hình lấy từ bản ghi recorder của phase 2.

## Requirements

- Hàng đợi `sap_job` có ưu tiên theo V2 mục 2.3, nhận việc bằng `SELECT … FOR UPDATE SKIP LOCKED`.
- Trạng thái việc: `PENDING`, `RUNNING`, `DONE`, `FAILED`, `UNKNOWN`, `NEED_REVIEW`.
- Việc tạo chứng từ không bao giờ tự thử lại từ `UNKNOWN`; phải qua bước tra SAP.
- Mỗi T-code là một hàm nhỏ trả về kết quả rõ: thành công kèm số chứng từ, hoặc lỗi kèm loại và nội dung thông báo.
- Sau mỗi bước, đọc thanh trạng thái (loại thông báo và nội dung).
- Popup không có trong danh sách đã biết thì không bấm gì, chụp màn hình, chuyển `NEED_REVIEW`.
- Phát hiện phiên bị ngắt hoặc bị đăng xuất, đăng nhập lại, đưa việc đang dở về `UNKNOWN`.
- Tự dừng khi số lỗi liên tiếp vượt ngưỡng; chỉ người có quyền bật lại.
- Chạy được chế độ thử (dry-run) trên máy không có SAP để test hàng đợi.
- Mỗi việc ghi rõ hệ thống đích (tên hệ thống và client). Trước mỗi việc, robot đọc tên hệ thống, client và user của phiên đang mở; không khớp thì từ chối chạy và cảnh báo.
- Việc nhắm vào QA nằm trong `shoponline_dev` trên máy phát triển; việc nhắm vào hệ thống thật nằm trong `shoponline` trên máy chạy thật. Chứng từ thử không lẫn vào dữ liệu thật.
- Đệm tồn kho theo mã vật tư và kho, có thời hạn cấu hình được; mỗi lần robot tạo SO thì trừ số lượng vào bản đệm để các đơn kế tiếp không dùng số tồn đã cũ.

## Architecture

```
sapjobs/queue.py        enqueue (có khóa chống trùng), claim, complete, mark_unknown
sapjobs/priorities.py   1 sắp quá hạn · 2 SO/DO/PGI · 3 billing · 4 tồn kho, hoàn, báo cáo
saprobot/session.py     kết nối SAPGUI → GetScriptingEngine → chọn đúng connection/session
saprobot/statusbar.py   đọc wnd[0]/sbar: loại (S/W/E/A/I), mã, nội dung
saprobot/popups.py      nhận diện wnd[1], tra config/sap_popups.yaml
saprobot/screen.py      truy cập phần tử theo ID lấy từ config/sap_screens.yaml
saprobot/evidence.py    chụp màn hình khi lỗi, lưu đường dẫn vào sap_job
saprobot/worker.py      vòng lặp: kiểm tra công tắc → claim → chạy → ghi kết quả
saprobot/transactions/  find_so.py (VA05), read_so.py (VA03), read_stock.py (MMBE)
config/sap_popups.yaml  popup đã biết: nhận diện bằng gì, hành động cho phép
config/sap_screens.yaml ID phần tử theo T-code
```

**Vòng đời một việc tạo chứng từ**

1. `PENDING` → robot nhận, đặt `RUNNING`.
2. Thành công và đọc được số chứng từ → `DONE`.
3. SAP báo lỗi rõ ràng trước khi lưu → `FAILED` (được thử lại có giới hạn nếu lỗi thuộc loại tạm thời, ví dụ chứng từ bị khóa).
4. Mất phiên, hết thời gian, hoặc không đọc được kết quả sau khi đã bấm lưu → `UNKNOWN`.
5. Từ `UNKNOWN`: chạy việc tra SAP theo mã đơn sàn. Tìm thấy chứng từ thì ghi nhận và `DONE`; không thấy thì quay lại `PENDING`; tra không được thì `NEED_REVIEW`.

Robot kết nối PostgreSQL qua `localhost`; PostgreSQL không nhận kết nối từ máy khác.

Robot được đăng ký là tác vụ Task Scheduler chạy khi tài khoản robot đăng nhập (máy tự đăng nhập tài khoản này sau khi khởi động lại). Trước khi khởi động, tác vụ kiểm tra chưa có tiến trình robot nào đang chạy.

## Related Code Files

- Create: `src/shoponline/sapjobs/queue.py`, `sapjobs/priorities.py`
- Create: `src/shoponline/saprobot/session.py`, `statusbar.py`, `popups.py`, `screen.py`, `evidence.py`, `worker.py`
- Create: `src/shoponline/saprobot/transactions/find_so.py`, `read_so.py`, `read_stock.py`
- Create: `config/sap_popups.yaml`, `config/sap_screens.yaml`
- Modify: `src/shoponline/cli.py` (lệnh `robot`, `robot-pause`, `robot-resume`)
- Modify: `src/shoponline/web/routes/` (màn hình hàng đợi, ảnh lỗi, nút thử lại, công tắc dừng)
- Create: `tests/sapjobs/test_queue.py`, `tests/sapjobs/test_unknown_recovery.py`, `tests/saprobot/test_popups.py`, `tests/saprobot/test_statusbar_parsing.py`
- Create: `docs/robot-runbook.md`

## Implementation Steps

1. Viết `queue.py`. Test: hai tiến trình cùng nhận việc không bao giờ nhận trùng; xếp hai việc tạo SO cho cùng một đơn thì việc thứ hai bị từ chối; thứ tự nhận theo ưu tiên rồi theo hạn giao.
2. Viết test vòng đời `UNKNOWN` bằng một lớp thực thi giả lập lỗi mất phiên, chứng minh không có đường nào từ `UNKNOWN` thẳng tới chạy lại lệnh tạo.
3. Viết `session.py`: liệt kê connection và session, chọn theo tên hệ thống, client và user robot thay vì luôn lấy phần tử đầu; kiểm tra đã đăng nhập; đăng nhập lại khi cần; chờ khi phiên đang bận.
4. Viết `statusbar.py` và `popups.py`; nạp cấu hình từ YAML. Popup được phép bỏ qua phải khớp cả tiêu đề lẫn nội dung.
5. Viết `screen.py` để mọi truy cập phần tử đi qua một chỗ, báo lỗi có tên T-code và ID khi không tìm thấy phần tử.
6. Viết `evidence.py` chụp cửa sổ SAP khi lỗi.
7. Viết ba thao tác đọc từ bản ghi recorder: tìm SO theo mã đơn sàn, đọc chi tiết SO (dòng, số lượng, giá, điều kiện, tổng), đọc tồn kho theo mã vật tư và kho.
8. Viết `worker.py` với công tắc dừng: đếm lỗi liên tiếp, vượt ngưỡng thì dừng nhận việc và cảnh báo. Việc sắp quá hạn mà robot đang dừng cũng cảnh báo.
9. Thêm màn hình hàng đợi trên web: danh sách việc, ảnh lỗi, nút thử lại (chỉ cho việc đọc và việc `FAILED`), nút tạm dừng và bật lại robot.
10. Cảnh báo mật khẩu user robot sắp hết hạn theo chính sách đã hỏi ở phase 2.
11. Chạy thử trên máy phát triển với hệ thống QA: xếp 50 việc đọc SO, để chạy qua đêm, kiểm tra kết quả và hành vi khi rút mạng giữa chừng. Thử thêm: đặt cấu hình hệ thống đích khác với phiên đang mở, robot phải từ chối.
12. Đo năng lực: ghi thời gian trung bình của từng loại thao tác đọc, ước lượng số đơn một phiên xử lý được mỗi giờ, so với mục tiêu 100 đơn/ngày trong hạn giao của sàn. Ghi kết quả vào `docs/robot-runbook.md`. Phép đo lặp lại ở phase 8 khi đã có đủ thao tác ghi.
13. Thêm tác vụ `robot` vào `scripts/windows/register-tasks.ps1`. Triển khai lên máy chạy thật ở chế độ chỉ đọc, khởi động lại máy và kiểm tra robot tự chạy lại, rồi lặp lại 50 việc đọc SO trên hệ thống thật để xác nhận màn hình ở đó khớp với QA.
14. Viết `docs/robot-runbook.md`: khởi động, dừng, đăng nhập lại, xử lý popup lạ, bổ sung popup vào cấu hình.

## Todo

- [ ] Hàng đợi và test nhận việc đồng thời
- [ ] Test vòng đời `UNKNOWN`
- [ ] Quản lý phiên và đăng nhập lại
- [ ] Thanh trạng thái và popup theo cấu hình
- [ ] Chụp màn hình khi lỗi
- [ ] Thao tác tìm SO, đọc SO, đọc tồn kho
- [ ] Worker và công tắc dừng khẩn cấp
- [ ] Màn hình hàng đợi trên web
- [ ] Cảnh báo mật khẩu sắp hết hạn
- [ ] Kiểm tra hệ thống đích trước mỗi việc và test từ chối khi sai hệ thống
- [ ] Chạy thử 50 việc đọc trên QA
- [ ] Đo năng lực một phiên
- [ ] Tác vụ `robot` tự chạy lại sau khi khởi động máy
- [ ] Sổ tay robot

## Success Criteria

- 50 việc đọc SO chạy liên tục cho kết quả khớp với xem tay trên SAP.
- Rút mạng hoặc đóng SAP GUI giữa chừng: robot phát hiện, không treo, việc đang dở về đúng trạng thái, có ảnh và cảnh báo.
- Popup lạ dẫn tới `NEED_REVIEW` mà không có lần bấm nào.
- Việc nhắm vào QA không bao giờ chạy trên phiên hệ thống thật và ngược lại (có test tự động và có lần thử thật).
- Có con số năng lực đo được và kết luận một phiên có đủ cho ngày cao điểm hay không.

## Verification

- `uv run pytest tests/sapjobs tests/saprobot` thoát mã 0 (các test này chạy được trên Linux nhờ lớp thực thi giả).
- Biên bản chạy thử trên máy robot ghi vào `docs/robot-runbook.md`.

## Risk Assessment

- **Màn hình khác với bản ghi recorder** (bố cục cá nhân hóa, phiên bản GUI). Giảm thiểu bằng việc ghi recorder trên chính máy robot với user robot, và cố định ngôn ngữ, độ phân giải.
- **Phiên bị khóa khi ngắt RDP.** Kiểm tra trong bước chạy qua đêm; nếu không giữ được thì dùng mini PC có màn hình ảo như V2 gợi ý.
- **Đọc tồn kho chậm.** Lưu đệm kết quả có thời hạn ngắn; chạy ở ưu tiên thấp.

## Rollback

Robot chỉ đọc ở phase này. Tắt tiến trình `robot` là đủ.

## Security Considerations

- Mật khẩu SAP của robot đọc từ kho bí mật trên máy robot, không nằm trong database hay nhật ký.
- Ảnh chụp màn hình có thể chứa dữ liệu khách hàng; lưu ở thư mục giới hạn quyền, có thời hạn xóa.
- User robot chỉ có quyền các T-code cần dùng.

## Next Steps

Phase 7 thêm thao tác tạo SO lên khung này.
