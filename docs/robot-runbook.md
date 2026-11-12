# Sổ tay robot SAP

Dành cho admin shop online và người trực hệ thống. Cách dựng máy: [robot-machine-setup.md](robot-machine-setup.md).

## Robot làm gì

Robot chỉ đọc SAP, không tạo chứng từ nào. Nó chạy trên Production `AEP`, client `300`, bằng user `AL17016`, và chỉ vào hai báo cáo `ZRSD001` và `ZRSD004`; lớp chặn T-code bảo đảm điều này (xem [Lớp chặn T-code](#lớp-chặn-t-code)).

| Khi nào | Việc | Kết quả |
|---|---|---|
| Admin bấm "Sales admin đã tạo SO và DO" trên một lô | `read_zrsd001`: `zrsd001` lựa chọn "Complete", lọc theo khách hàng SAP của sàn và ngày xử lý của lô | Lưu số SO, nối đơn, báo lệch trên trang lô, giống hệt khi tải file lên |
| Admin bấm "Xuất file gửi kế toán" trên lô vào ngày goods issue | `read_zrsd004` cho ngày goods issue | Đơn có DO chuyển "Đã có DO"; link "Tải file kế toán" hiện ở trang Robot SAP và trang Báo cáo SAP |

Kết quả robot đọc đi qua đúng các hàm nhập file của trang **Báo cáo SAP**. Khi robot dừng, admin vẫn tải hai file báo cáo lên bằng tay như trước.

## Trạng thái việc

| Trạng thái | Nghĩa | Làm gì |
|---|---|---|
| Chờ | Đang đợi robot | — |
| Đang chạy | Robot đang làm | — |
| Xong | Đã nhập kết quả | Xem cảnh báo trong cột kết quả |
| Lỗi | Không làm được (SAP báo lỗi, file sai, chưa có thao tác, lớp chặn T-code…) | Xem lỗi và ảnh; bấm "Chạy lại" sau khi sửa nguyên nhân |
| Cần kiểm tra | Gặp cửa sổ lạ; robot không bấm gì | Xem ảnh. Nếu cửa sổ an toàn để trả lời, thêm nó vào `config/sap_popups.yaml`, khởi động lại robot, bấm "Chạy lại" |
| Chưa rõ | Việc ghi SAP bị ngắt giữa chừng | Không xảy ra: dự án không có việc ghi SAP |

## Robot tự dừng

Robot dừng và hiện dòng cảnh báo trên mọi trang khi:

- số việc lỗi liên tiếp đạt `SHOPONLINE_ROBOT_MAX_FAILURES`;
- phiên SAP đang mở không đúng hệ thống, client hoặc user của việc. Robot không đăng nhập thêm khi đã có phiên của hệ thống khác; nó từ chối việc và dừng;
- lớp chặn T-code bắt được T-code, phím hoặc thao tác ngoài danh sách được phép (xem mục dưới).

Chỉ admin bật lại được, trên trang **Robot SAP** hoặc bằng `uv run shoponline robot-resume`. Xem nguyên nhân trong cột lỗi và ảnh chụp trước khi bật lại.

Tạm dừng chủ động (bảo trì SAP, đổi mật khẩu robot): nút "Tạm dừng robot" hoặc `uv run shoponline robot-pause --reason "<lý do>"`. Việc đang chạy vẫn chạy xong.

## Lớp chặn T-code

User `AL17016` mở được cả `VA02`, nên role phía SAP không ngăn robot sửa SO. Hàng rào phía robot là lớp bọc phiên trong [guard.py](../src/shoponline/saprobot/guard.py): mọi thao tác của robot với SAP GUI đi qua nó, kể cả màn hình đăng nhập và việc trả lời cửa sổ phụ.

| Danh sách | Giá trị | Ghi chú |
|---|---|---|
| T-code phiên được phép đứng | `S000`, `SESSION_MANAGER`, `ZRSD001`, `ZRSD004` | Màn hình đăng nhập, menu chính, hai báo cáo (cả màn hình lọc và lưới kết quả). Lấy từ System → Status trên `AEP`/300 ngày 2026-11-12 |
| T-code robot được tự mở | `ZRSD001`, `ZRSD004` | Chỉ mở qua ô lệnh bằng `/n<T-code>`; không có đường nào khác ghi vào ô lệnh `okcd` |
| Phím được gửi | Enter, F8 | Phím lưu (Ctrl+S, `sendVKey 11`) luôn bị cấm |
| Hàm đọc phần tử | `GetCellValue`, `GetColumnTitles`, `GetDisplayedColumnTitle` | Đọc lưới ALV; robot không bấm đúp vào dòng |

Robot đọc `Info.Transaction` của phiên ngay khi nhận phiên, rồi trước và sau mỗi thao tác (gõ chữ, chọn, bấm nút, gửi phím, trả lời cửa sổ phụ). Khi gặp T-code ngoài danh sách, hoặc một phím hay thao tác bị cấm:

1. Robot không bấm gì thêm trên phiên đó.
2. Robot chụp màn hình; ảnh hiện ở cột ảnh của việc trên trang **Robot SAP**.
3. Việc chuyển "Lỗi", nội dung lỗi bắt đầu bằng "Lớp chặn T-code".
4. Robot tự tạm dừng với cùng lý do; nhật ký sự kiện ghi `robot_guard_violation`.

Admin làm gì:

1. Xem ảnh và lỗi để biết robot đang đứng ở màn hình nào. Nếu phiên SAP còn ở T-code lạ (ví dụ `VA02`), thoát bằng tay **không lưu** và về menu chính.
2. Tìm vì sao robot tới đó: nút trên lưới mở chứng từ, màn hình SAP đổi sau nâng cấp, hay lỗi trong thao tác của robot. Chưa rõ nguyên nhân thì không bật lại robot; trong lúc chờ, tải file báo cáo lên bằng tay.
3. Bật lại robot rồi bấm "Chạy lại" cho việc.

Các danh sách này nằm cứng trong mã, không nằm trong YAML hay `.env`. Muốn thêm T-code, phím hoặc hàm đọc (ví dụ khi bản ghi recorder cho thấy cần xuất Excel), sửa `guard.py` kèm test trong `tests/saprobot/test_guard.py`, chạy lại `uv run pytest tests/saprobot`, và chủ dự án duyệt thay đổi.

Giới hạn: lớp chặn bảo vệ trước lỗi trong mã robot và trước màn hình SAP tự chuyển sang T-code khác. Nó không chặn người đăng nhập SAP bằng tay với `AL17016`, và không bảo vệ trước lỗi nằm trong chính `guard.py`. Vì vậy tài khoản Windows của robot không dùng cho việc khác, và nên đề nghị IT thu role của `AL17016` về hai báo cáo.

## Khởi động lại và mất phiên

- Phiên SAP bị ngắt hoặc đăng xuất: ở việc kế tiếp robot đăng nhập lại qua mục SAP Logon đã cấu hình, rồi kiểm tra lại hệ thống, client và user.
- Robot bị tắt giữa lúc đang chạy một việc đọc: lần khởi động sau việc đó về "Chờ" và chạy lại.
- Ảnh chụp màn hình lỗi nằm ở `<SHOPONLINE_DATA_DIR>\robot-evidence` và tự xóa sau `SHOPONLINE_ROBOT_EVIDENCE_KEEP_DAYS` ngày, vì có thể chứa dữ liệu khách.

## Chưa có, chờ bản ghi recorder

Các mục dưới đây được điền khi có bản ghi recorder trên `AEP`/300 bằng `AL17016`. Chưa có thì không viết:

- ID phần tử màn hình lọc và lưới kết quả của `zrsd001` và `zrsd004` trong `config/sap_screens.yaml`.
- Cách lấy dữ liệu báo cáo: đọc thẳng lưới hay xuất Excel ra thư mục cố định.
- Danh sách cửa sổ phụ đã biết trong `config/sap_popups.yaml`.
- Thời gian một lần đọc báo cáo.
- Biên bản chạy thử trên Production ngoài giờ cao điểm (50 việc đọc liên tiếp, ngắt mạng, sai hệ thống đích) và 5 ngày so robot với file tải lên.
