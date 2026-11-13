---
title: "Thao tác đọc zrsd001 và zrsd004 từ bản ghi recorder"
date: 2026-11-12
summary: Có bản ghi recorder trên AEP/300; robot mở báo cáo, điền bộ lọc và chạy được; chốt xuất Excel thay vì đọc lưới vì file kế toán phải khớp từng ô; zrsd004 tách theo sàn
---

# Thao tác đọc báo cáo từ bản ghi recorder

## Bản ghi
- Ba bản ghi `.vbs` (zrsd001 Open, zrsd001 Complete, zrsd004) và ảnh System → Status trong `docs/sap-recordings/`. `Info.Transaction` là `SESSION_MANAGER` ở menu chính, và `ZRSD001`/`ZRSD004` ở cả màn hình lọc lẫn lưới ALV. Danh sách T-code được phép trong `guard.py` khớp, không phải sửa.
- Muốn ghi recorder phải bật `sapgui/user_scripting` trên AEP trước. Nếu chưa bật, mục "Script Recording and Playback" bị xám dù phía máy khách đã bật scripting.

## Quyết định
- **Xuất Excel, không đọc lưới.** Lưới đọc được bằng scripting, nhưng file gửi kế toán được dựng thẳng từ file zrsd004 và cổng G1 đòi khớp từng ô với file admin. Đọc lưới thì mọi ô thành chữ, mất kiểu ngày, kiểu số và dòng tổng. Chủ dự án chọn xuất Excel. Bước xuất cần thêm một bản ghi nữa, nên lúc này robot chạy tới lưới kết quả rồi báo lỗi rõ ràng.
- **zrsd004 lọc theo khách SAP của sàn.** Bản ghi lọc Sold-to của Shopee. Nếu không lọc, báo cáo trả mọi DO của tổ chức bán hàng 1000, và file kế toán sẽ có dòng của khách khác. Vì vậy mỗi sàn và mỗi ngày là một việc riêng; khóa trùng đổi thành `read_zrsd004:<sàn>:<ngày>`.
- Bản ghi chọn ngày bằng lịch F4. Robot gõ ngày thẳng vào ô theo định dạng của `AL17016` (`formats.date`), nên không phải mở thêm phím F4.
- Radio "Complete" được chọn bằng `.select()`, đúng như bản ghi. Trước đây guard gán `selected = True`, nhưng thuộc tính đó của radio là chỉ đọc.

## Kiểm chứng
- Test mới `tests/saprobot/test_report_reads.py` dùng ID thật trong `config/sap_screens.yaml` với SAP GUI giả. Các trường hợp được kiểm: bộ lọc, radio, nút chạy, "No data to display", và payload ngoài phạm vi bản ghi. Toàn bộ 131 test đều đạt. Chưa chạy trên SAP thật.

## Bước xuất Excel
- Bản ghi xuất Excel (`docs/sap-recordings/exportexcel/`) chỉ có các bước chuột phải, chọn `&XXL` và trả lời hộp "Select Spreadsheet". Các cửa sổ sau đó là cửa sổ Windows, recorder không ghi được: Save As, hộp hỏi ghi đè, SAP GUI Security (Allow/Deny để mở file) và Excel tự mở file.
- Chủ dự án chọn tự động hóa các cửa sổ Windows, thay vì quay về đọc lưới. `desktop.py` dùng pywinauto (backend win32) chạy trên một luồng phụ, vì lệnh SAP mở hộp Save As bị chặn cho đến khi hộp đó đóng. Robot gõ đường dẫn đầy đủ qua control ID của hộp thoại chuẩn Windows, nên không phụ thuộc ngôn ngữ giao diện. Robot chỉ bấm Allow khi hộp SAP GUI Security nêu đúng file của nó. Mỗi việc có tên file riêng, và file cũ bị xóa trước khi xuất, nên khi chạy lại không có hộp hỏi ghi đè.
- Lớp chặn có thêm danh sách mục menu chuột phải được phép, gồm duy nhất `&XXL`.
- Hai file xuất thật đọc được bằng `read_zrsd001`, `read_zrsd004` và `build_accounting_workbook`: zrsd001 có 15 SO và 27 dòng, zrsd004 có 13 DO. File xuất thật có cột ngày kiểu ngày, cột số lượng là số thực `0.000`, cột tiền là số nguyên, và có dòng tổng. Điều này xác nhận lý do không đọc lưới.
- `update-production.ps1` chạy `uv sync --no-dev` mà không có `--extra robot`, nên mỗi lần deploy sẽ gỡ pywin32 và pywinauto trên chính máy chạy robot. Đã sửa.

## Còn lại
- Chạy thử trên Production. Lần đầu sẽ biết hộp Save As có đúng các control ID của hộp thoại chuẩn Windows không; nếu không đúng, lỗi sẽ liệt kê các phần tử của hộp.
- Ảnh và file `.XLSX` trong `docs/sap-recordings/` có tên khách, tên nhân viên bán hàng và mã đơn thật. Không đưa các file này vào git khi chưa che.
