# Sổ tay robot SAP

Dành cho admin shop online và người trực hệ thống. Cách dựng máy: [robot-machine-setup.md](robot-machine-setup.md).

## Robot làm gì

Robot chỉ đọc SAP, không tạo chứng từ nào. Nó chạy trên Production `AEP`, client `300`, bằng user `AL17016`, và chỉ vào hai báo cáo `ZRSD001` và `ZRSD004`; lớp chặn T-code bảo đảm điều này (xem [Lớp chặn T-code](#lớp-chặn-t-code)).

| Khi nào | Việc | Kết quả |
|---|---|---|
| Admin bấm "Sales admin đã tạo SO và DO" trên một lô | `read_zrsd001`: `zrsd001` với Sales Office `1401`, ngày chứng từ là ngày xử lý của lô, Sold-To là khách hàng SAP của sàn, lựa chọn "Complete" | Lưu số SO, nối đơn, báo lệch trên trang lô, giống hệt khi tải file lên |
| Admin bấm "Xuất file gửi kế toán" (trang lô hoặc trang Gửi kế toán) | Một đợt: với mỗi sàn còn đơn chờ, `read_zrsd004` cho từng ngày goods issue từ ngày cũ nhất của đơn chờ đến hôm nay (tối đa 31 ngày lùi): `zrsd004` với Sales Organization `1000`, Sold-to là khách hàng SAP của sàn, Actual GI là ngày đó | Đơn có DO chuyển "Đã có DO"; file kế toán dựng ở trang **Gửi kế toán**, không còn link tải trên trang Robot SAP hay Báo cáo SAP |
| Admin dùng form "Ra lệnh cho robot" trên trang Robot SAP | `read_zrsd001` cho một lô đã xác nhận, hoặc `read_zrsd004` cho một sàn và một ngày goods issue | Giống hai dòng trên, kể cả khi việc trước cùng loại đã Xong |
| Admin bấm "Đọc lại zrsd001" trên trang lô đã xác nhận | `read_zrsd001` của lô đó | Cập nhật SO đã nối và báo lệch mới; không tạo bản ghi trùng |

Bộ lọc lấy theo bản ghi recorder ngày 2026-11-12 (`docs/sap-recordings/` trên máy phát triển, không đưa vào git vì có dữ liệu khách thật). Robot gõ ngày thẳng vào ô lọc theo định dạng của `AL17016` (`formats.date` trong `config/sap_screens.yaml`), không mở lịch F4 như bản ghi. SAP báo "No data to display" cho `zrsd004` thì việc kết thúc **Xong** với kết quả "SAP chưa có DO": ngày đó chưa có giao hàng là chuyện bình thường. Kết quả này không tăng và không xóa bộ đếm lỗi liên tiếp. Với `zrsd001`, không có dữ liệu vẫn là lỗi.

Robot lấy dữ liệu bằng chức năng xuất Excel của báo cáo, giống thao tác của admin, chứ không đọc lưới trên màn hình. Lý do: file gửi kế toán được dựng thẳng từ file `zrsd004` và phải khớp từng ô với file admin tự làm (cổng G1); đọc lưới chỉ ra chữ, mất kiểu ngày, kiểu số và dòng tổng. File robot xuất đi qua đúng các hàm nhập file của trang **Báo cáo SAP**. Khi robot dừng, admin vẫn tải hai file báo cáo lên bằng tay như trước.

Cách robot xuất (theo bản ghi xuất Excel ngày 2026-11-12, `docs/sap-recordings/exportexcel/`):

1. Chuột phải vào lưới kết quả, chọn **Spreadsheet...** (`&XXL`, mục menu duy nhất lớp chặn cho phép).
2. Nếu SAP hỏi định dạng ("Select Spreadsheet"), robot bấm tiếp theo luật trong `config/sap_popups.yaml`. Nếu đã tick "Always Use Selected Format" thì SAP không hỏi.
3. Các cửa sổ sau đó là cửa sổ Windows, SAP GUI Scripting không với tới. Robot trả lời chúng bằng [desktop.py](../src/shoponline/saprobot/desktop.py):
   - **Save As**: gõ đường dẫn đầy đủ `<SHOPONLINE_DATA_DIR>\robot-work\job-<số việc>\<báo cáo>-job-<số việc>.xlsx` rồi bấm Save. File cũ của cùng việc bị xóa trước, nên khi chạy lại không có hộp hỏi ghi đè.
   - **SAP GUI Security**: chỉ bấm Allow khi hộp này nêu đúng file vừa lưu, và không tick "Remember My Decision". Hộp hỏi về file khác thì robot bấm Deny và việc chuyển "Lỗi".
   - **Excel** tự mở file vừa xuất: robot đóng cửa sổ đó rồi đọc file.

Việc báo lỗi "Không thấy hộp Save As", "Hộp Save As khác dự kiến" hoặc "Hết giờ chờ hộp thoại lưu file" nghĩa là các cửa sổ Windows khác với lúc ghi. Xem ảnh của việc, kiểm tra màn hình máy robot không bị khóa, rồi bấm "Chạy lại". Nếu Excel hoặc hộp Save As còn mở trên máy robot, đóng chúng bằng tay trước.

## Ra lệnh cho robot

Ngoài hai nút tự động, admin bảo robot đọc báo cáo khi cần: form **Ra lệnh cho robot** trên trang **Robot SAP** (đọc `zrsd001` cho một lô đã xác nhận, hoặc `zrsd004` cho một sàn và một ngày goods issue; lệnh tay chỉ nhập dữ liệu, file kế toán lấy ở trang **Gửi kế toán**) và nút **Đọc lại zrsd001** trên trang lô đã xác nhận. Form chỉ hiện với admin khi robot đã có hệ thống đích; nếu kết nối chưa được kiểm tra, form hiện lý do thay cho nút.

- **Khi nào dùng:** sales admin tạo thêm SO sau lần đọc `zrsd001` đầu; lô được xác nhận lúc kết nối chưa được kiểm tra nên chưa có việc đọc; cần đọc `zrsd004` cho một ngày goods issue hoặc một đơn chờ nằm ngoài cửa sổ 31 ngày của đợt gửi kế toán (đợt cảnh báo các đơn đó).
- **Việc trùng bị từ chối:** mỗi báo cáo chỉ có một việc mở tại một thời điểm. Nếu việc cũ còn Chờ hoặc Đang chạy, trang báo số việc đó; chờ nó xong rồi ra lệnh lại. Việc đã Xong thì ra lệnh lại được.
- **Ngày không có dữ liệu:** web chặn ngày goods issue sau hôm nay. Một ngày không có DO (ví dụ ngày nghỉ) với `zrsd004` cho kết quả "SAP chưa có DO" và không tính vào bộ đếm lỗi liên tiếp ([Robot tự dừng](#robot-tự-dừng)); với `zrsd001` đó vẫn là lỗi.
- **Nhật ký:** mỗi lệnh ghi một sự kiện `sap_job_enqueued` kèm tên người ra lệnh.

## Kiểm tra kết nối SAP

Trang **Robot SAP → Kết nối SAP** có nút **Kiểm tra**: web xếp một việc `check_connection`, robot đăng nhập thử, đọc hệ thống/client/user của phiên rồi đăng xuất, và trang hiện kết quả (tự tải lại mỗi 3 giây trong lúc chờ). Việc này không gửi T-code nào, vẫn đi qua lớp chặn T-code và so khớp phiên, và chạy được cả khi robot đang tạm dừng. Lỗi kiểm tra không tăng bộ đếm lỗi liên tiếp và không làm robot tự dừng. Không chụp ảnh màn hình khi đăng nhập lỗi vì màn hình đó có ô mật khẩu.

| Mã lỗi | Nghĩa | Cách sửa |
|---|---|---|
| `missing_settings` | Thiếu mục SAP Logon hoặc user SAP | Điền ở trang Kết nối SAP |
| `missing_password` | Máy robot chưa có mật khẩu của user | Chạy `uv run --extra robot shoponline sap-password set` dưới tài khoản chạy robot |
| `saplogon_not_running` | Không mở được SAP Logon | Mở SAP Logon bằng tay hoặc sửa `SHOPONLINE_SAPLOGON_PATH` |
| `scripting_disabled` | SAP Logon chạy nhưng scripting tắt | Bật scripting ở phía máy khách (xem [robot-machine-setup.md](robot-machine-setup.md)); phía máy chủ Basis bật `sapgui/user_scripting` |
| `connection_not_found` | Tên mục SAP Logon không tồn tại | Chọn lại đúng mục trong danh sách |
| `logon_failed` | SAP từ chối đăng nhập (thông báo nguyên văn của SAP hiện kèm) | Kiểm tra user và mật khẩu; sai nhiều lần sẽ khóa user, nên sửa rồi mới thử lại |
| `wrong_system` | Đăng nhập vào hệ thống hoặc client khác cấu hình | Mục SAP Logon đang trỏ nhầm hệ thống: chọn mục khác hoặc sửa hệ thống và client |
| `foreign_session` | Máy robot đang có phiên SAP của người khác | Đóng phiên đó rồi kiểm tra lại; robot không đăng nhập cạnh phiên lạ |
| `guard_violation`, `unknown_popup`, `error` | Phiên đang ở T-code ngoài danh sách, hộp thoại lạ hoặc lỗi khác | Xem thông báo và ảnh của việc trong hàng đợi |

Nếu robot không chạy (không có heartbeat trong 30 giây) trang báo "Robot không chạy" và việc kiểm tra nằm chờ; bấm Kiểm tra lần nữa thì lần mới thay lần đang chờ. Robot đang làm việc khác thì trang báo "Đang chờ robot xong việc #N".

**Đổi hệ thống hoặc client thì phải kiểm tra trước.** Cho đến khi một lần kiểm tra thành công với đúng hệ thống và client mới, web không xếp việc đọc báo cáo (nút bị khóa, có thanh cảnh báo trên mọi trang) và robot không nhận việc nào ngoài kiểm tra kết nối. Việc đọc báo cáo đã xếp cho hệ thống cũ sẽ lỗi "nhắm X nhưng cấu hình hiện là Y" mà không đăng nhập; xếp lại sau khi kiểm tra.

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

- số việc lỗi liên tiếp đạt giá trị "Số lỗi liên tiếp thì dừng" trên trang Kết nối SAP (mặc định 3; việc kiểm tra kết nối không tính);
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
| Mục menu chuột phải trên lưới | `&XXL` (Spreadsheet...) | Xuất Excel; mục khác (ví dụ Details, gửi email) bị cấm |

Robot đọc `Info.Transaction` của phiên ngay khi nhận phiên, rồi trước và sau mỗi thao tác (gõ chữ, chọn, bấm nút, gửi phím, trả lời cửa sổ phụ). Khi gặp T-code ngoài danh sách, hoặc một phím hay thao tác bị cấm:

1. Robot không bấm gì thêm trên phiên đó.
2. Robot chụp màn hình rồi đăng xuất (đóng kết nối, mọi thứ chưa lưu bị bỏ); ảnh hiện ở cột ảnh của việc trên trang **Robot SAP**.
3. Việc chuyển "Lỗi", nội dung lỗi bắt đầu bằng "Lớp chặn T-code".
4. Robot tự tạm dừng với cùng lý do; nhật ký sự kiện ghi `robot_guard_violation`.

Admin làm gì:

1. Xem ảnh và lỗi để biết robot đã đứng ở màn hình nào. Robot đã tự đăng xuất, nên không còn phiên nào phải thoát tay.
2. Tìm vì sao robot tới đó: nút trên lưới mở chứng từ, màn hình SAP đổi sau nâng cấp, hay lỗi trong thao tác của robot. Chưa rõ nguyên nhân thì không bật lại robot; trong lúc chờ, tải file báo cáo lên bằng tay.
3. Bật lại robot rồi bấm "Chạy lại" cho việc.

Các danh sách này nằm cứng trong mã, không nằm trong YAML hay `.env`. Muốn thêm T-code, phím hoặc hàm đọc (ví dụ khi bản ghi recorder cho thấy cần xuất Excel), sửa `guard.py` kèm test trong `tests/saprobot/test_guard.py`, chạy lại `uv run pytest tests/saprobot`, và chủ dự án duyệt thay đổi.

Giới hạn: lớp chặn bảo vệ trước lỗi trong mã robot và trước màn hình SAP tự chuyển sang T-code khác. Nó không chặn người đăng nhập SAP bằng tay với `AL17016`, và không bảo vệ trước lỗi nằm trong chính `guard.py`. Vì vậy tài khoản Windows của robot không dùng cho việc khác, và nên đề nghị IT thu role của `AL17016` về hai báo cáo.

## Đăng nhập theo việc, khởi động lại và mất phiên

- Robot chỉ đăng nhập SAP khi có việc: nhận việc, đăng nhập `AL17016` qua mục SAP Logon đã cấu hình trên web (đọc lại ở mỗi việc, mật khẩu lấy từ Windows Credential Manager), kiểm tra hệ thống, client, user, làm việc, rồi đăng xuất ngay (kể cả khi việc lỗi, sau khi chụp ảnh). Giữa hai việc robot không giữ phiên SAP nào.
- SAP Logon chưa mở thì robot tự mở `saplogon.exe` (đường dẫn mặc định của bộ cài, đổi bằng `SHOPONLINE_SAPLOGON_PATH`).
- Đang có phiên SAP của người khác (ví dụ người dùng máy đang làm tay bằng user của mình) thì robot không đăng nhập bên cạnh: việc lỗi và robot tự tạm dừng (mục **Robot tự dừng**). Robot không bao giờ đăng xuất phiên của người khác.
- Robot khởi động (sau mỗi lần deploy hoặc khi đăng nhập Windows) thì đăng xuất phiên `AL17016` còn sót từ lần chạy trước.
- Robot bị tắt giữa lúc đang chạy một việc đọc: lần khởi động sau việc đó về "Chờ" và chạy lại.
- Ảnh chụp màn hình lỗi nằm ở `<SHOPONLINE_DATA_DIR>\robot-evidence` và tự xóa sau số ngày đặt ở trang Kết nối SAP (mặc định 30), vì có thể chứa dữ liệu khách.

## Chưa có, chờ bản ghi recorder

Màn hình lọc, lưới kết quả và bước xuất Excel của hai báo cáo đã có trong `config/sap_screens.yaml` và `config/sap_popups.yaml` (bản ghi ngày 2026-11-12). Chưa chạy trên SAP thật. Các mục dưới đây điền sau lần chạy thử:
- Thời gian một lần đọc báo cáo.
- Biên bản chạy thử trên Production ngoài giờ cao điểm (50 việc đọc liên tiếp, ngắt mạng, sai hệ thống đích) và 5 ngày so robot với file tải lên.
