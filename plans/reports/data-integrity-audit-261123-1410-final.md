# Rà soát toàn vẹn dữ liệu: báo cáo tổng hợp

Ngày: 2026-11-23. Plan: [261123-0556](../261123-0556-red-team-validate-data-integrity-audit/plan.md). Chủ dự án đã duyệt áp dụng toàn bộ phát hiện (44 mục Accept) và đặt plan `261113-1142` thành `in-progress`.

## Kết luận

- Không tìm thấy trường hợp **trùng** dữ liệu đã xảy ra trong DB dev: mọi bất biến kiểm được đều đạt (đơn, SO/DO, sổ DO gửi kế toán, file lịch sử, tiền vô).
- Có **2 điểm High** (điểm thứ ba về giá trị SO đã được chủ dự án xác nhận là cố ý), đều là đường mà dữ liệu sai hoặc sót có thể đi vào file kế toán hoặc hóa đơn mà không có cảnh báo. Chưa điểm nào được chứng minh đã xảy ra trên production.
- **Bất biến đã chạy trên cả dev và production** (production qua SSH, phiên chỉ đọc, 2026-11-23): kết quả hai nơi gần như trùng. Production chưa có file lịch sử nào, đơn nào quá 90 ngày hay lần khôi phục nào, nên I7b, I8, I11, I15 vẫn chưa có dữ liệu để kết luận.

## Phát hiện, xếp từ Critical xuống Low

Con số từng mức theo báo cáo của từng phase; mỗi dòng dẫn tới file có bằng chứng `file:dòng`.

| Mức | Số | Luồng | Phát hiện chính | Plan gốc | Đề xuất |
|---|---:|---|---|---|---|
| Critical | 0 | | | | |
| High | 1 | SO/DO, kế toán | Đơn đã hủy mà SO còn trong SAP: không cảnh báo; nếu SO đó có DO thì vào file kế toán với mã đơn đã hủy (`so_link.py:143-146,252-261`). Dev có 2 đơn hủy, 1 đơn liên kết SO | 261111-0755 | `/ak-fix` |
| ~~High~~ Low | 1 | SO/DO | **Chủ dự án xác nhận cố ý (2026-11-23):** SAP chỉ nhập giá gốc, bỏ trợ giá, nên SO cao hơn đúng bằng trợ giá. 17/117 đơn đã nối SO (14,5%) có giá trị SO khác giá trị tính từ file sàn mà vẫn giao và gửi kế toán; 13 đơn có trợ giá (cao hơn 300 đến 99.999 VND), 4 đơn Shopee lệch ±1 VND. Báo cáo lô chỉ liệt kê, không chặn, nên báo nhiễu | 261111-0755 | Báo cáo lô nên cộng lại trợ giá trước khi so |
| High | 1 | Hóa đơn | Một DO có hai dòng hóa đơn trong cùng file: dòng cuối thắng, im lặng (`report_ingest.py:81`); đã tái hiện. Có thể giữ nhầm hóa đơn đã hủy | 261119-0605 | `/ak-fix` sau khi biết SAP có liệt kê ZBA1 đã hủy không |
| Medium | 19 | Nhiều luồng | Xem bảng dưới | | |
| Low | 24 | Nhiều luồng | Xem file từng phase | | |
| Info | 3 | Tiền vô, hóa đơn | Lazada không có Tiền Vô (do thiết kế); 25 DO ngày GI 11-20 chưa có hóa đơn (do chưa đọc zrsd003 của ngày đó); 163 hóa đơn không khớp DO của hệ thống (khách ngoài ba sàn) | | Chấp nhận |

### Phát hiện Medium (nhóm theo chủ đề)

| Chủ đề | Phát hiện | Nguồn |
|---|---|---|
| Nhập lại / đổi dữ liệu sàn | Đơn đã có SO, DO hoặc đã hủy bị bỏ qua im lặng dù sàn đổi số lượng hoặc giá; TikTok bỏ im lặng dòng có mã đơn trống hoặc không phải số (đã tái hiện); DO thứ hai của một SO bị bỏ | [orders-sap](data-integrity-audit-261123-1320-orders-sap.md) |
| Hóa đơn | File cũ tải lên ghi đè số hóa đơn mới; một dòng lỗi của khách khác làm hỏng cả file; đơn nhiều DO chỉ kiểm hóa đơn cho DO đầu; không có trần khi chọn tháng cũ | [tax-invoice](data-integrity-audit-261123-1320-tax-invoice.md) |
| File lịch sử | Hai file chưa xác nhận có thể chồng đơn (bấm đúp tải cũng tạo chồng); Tiền Vô và hóa đơn đóng băng lúc tải; tên khách bắt đầu bằng `=`, `+`, `-`, `@` thành công thức Excel | [history-file](data-integrity-audit-261123-1320-history-file.md) |
| Dọn file | File kế toán cũ không thuộc đợt nào bị quét xóa ngay lượt đầu; file kế toán đã chốt chỉ được `full` hằng tuần sao lưu (tối đa 6 ngày rủi ro); quét đêm không đọc `maintenance.json`, có thể xóa file mới hơn DB sau khi khôi phục; đường dẫn tuyệt đối trong DB so với `SHOPONLINE_DATA_DIR` hiện tại | [deletion-machine](data-integrity-audit-261123-1320-deletion-machine.md) |
| Robot đọc khi cần | "Đọc lại zrsd001" chỉ đọc đúng ngày của lô, SO tạo sau đó không bao giờ được đọc; trạng thái plan lệch mã | [robot-on-demand](data-integrity-audit-261123-1320-robot-on-demand.md) |

## Bảng theo dõi sửa

Trạng thái cuối của từng phát hiện đã duyệt, theo [plan sửa](../261123-0732-data-integrity-fixes-accepted-findings/plan.md). Mỗi gói thêm các dòng của mình khi xong.

| Mã | Gói | Mức | Trạng thái | Ghi chú |
|---|---|---|---|---|
| D1 | A | Medium | đã sửa | Quét đêm từ chối chạy (mã thoát 1) khi đường dẫn lưu trong DB nằm ngoài `SHOPONLINE_DATA_DIR` |
| D2 | A | Medium | đã sửa | Giữ mọi `generated_file.kind = accounting_file` |
| D3 | A | Medium | đã sửa | Bản `db` có thêm `accounting-files/`; phục hồi bản `db` chép lại file còn thiếu, không ghi đè |
| D4 | A | Medium | đã sửa | Lệnh `retention` thoát sớm (mã 0) khi `maintenance.json` đang bật |
| D5 | A | Medium | đã sửa | Từ chối gỡ xác nhận khi tên khách của đơn nào trong file đã bị xóa |
| D6 | A | Low | chấp nhận rủi ro | Thêm thời gian ân hạn cho `discard_unused` làm file "đọc một lần" không còn bị xóa ngay lúc nhập, đổi hành vi đã ghi trong tài liệu; hai upload cùng nội dung trong cùng một giây hiếm |
| D7 | A | Low | đã sửa | Bỏ qua file biến mất giữa lúc liệt kê và đọc `stat` |
| H3 | B | Medium | đã sửa | Tên bắt đầu bằng `=`, `+`, `-`, `@` ghi thành chuỗi (trừ hai cột công thức của file) |
| H1 | B | Medium | đã sửa | Xác nhận một file xóa các file chưa xác nhận chứa cùng đơn; tải khi đã có file như vậy thì cảnh báo. Kèm sửa `flash()`: thông báo thứ hai bị mất khi đã có thông báo chờ trong phiên |
| H2 | B | Medium | chấp nhận rủi ro | Production chưa có file lịch sử nào để đo; Tiền Vô và hóa đơn đổi sau khi tải không vào file đã dán (đã ghi trong sổ tay vận hành). Xem lại khi có dữ liệu |
| H7 | B | Low | chấp nhận rủi ro | `Transaction` gộp hai đơn cùng tên, cùng phút: là cách file kế toán tự định nghĩa; chưa hỏi kế toán |
| D1 (0828) | B | Low | đã sửa | Sheet của file nháp tên `NHÁP - KHÔNG DÁN` |
| H4, H5, D2 (0828) | B | Low | chấp nhận rủi ro | Không cảnh báo tuổi đơn chờ; giả định giờ Việt Nam; Tiền Vô trong nháp là số tạm |
| 6 | C | Medium | đã sửa | TikTok từ chối dòng mã đơn trống hoặc không phải số, kèm số dòng; số float vượt 2^53 không còn thành số nguyên sai |
| 5 | C | Medium | đã sửa | Đơn đã có SO, DO hoặc hủy mà file đổi nội dung: sự kiện `order_changed_after_so`, hiện ở kết quả nhập và báo cáo lô; dữ liệu không đổi |
| 4 | C | Medium | đã sửa | Kết quả nhập nêu đơn đã thuộc lô ngày khác (kèm ngày); không chuyển lô |
| 7 | C | Medium | đã sửa | Báo cáo lô có mục đơn MAPPING_ERROR/NEED_REVIEW chưa có SO |
| 10, 8, 9, 12 | C | Low | chấp nhận rủi ro | `duplicate_po` bắt tải file đơn hai lần sau khi đọc zrsd001; không UNIQUE trên `so_number`/`do_number` (nhập chồng gây lỗi 500, không hỏng dữ liệu); không thêm migration |
| 3 (tax-invoice) | D | Medium | đã sửa | `read_zrsd003` nhận tập khách sàn: dòng lỗi của khách khác bị bỏ, dòng lỗi của khách sàn vẫn từ chối file |
| 7 (tax-invoice) | D | Medium | đã sửa | Khoảng đọc zrsd003 dài hơn 62 ngày cắt thành các việc ≤ 31 ngày nối tiếp, có cảnh báo |
| 5 (tax-invoice) | D | Low | chấp nhận rủi ro | Giới hạn bởi trần của mục 7; cách xử lý đơn không bao giờ có hóa đơn ghi trong sổ tay robot |
| 4 (tax-invoice) | D | Medium | ngoài phạm vi | SO nhiều DO: cần kiểm production, làm plan riêng |
| D9 | E | Low | đã sửa | Robot kiểm lại khóa chạy duy nhất mỗi vòng, mất khóa thì thoát mã 3. Test dùng `pg_advisory_unlock_all` thay cho kết nối rụng thật |
| D10 | E | Low | đã sửa | Đổi `sap_user` xóa trạng thái đã kiểm tra kết nối |
| robot-2 | E | Medium | đã sửa | "Đọc lại zrsd001" đọc từ ngày của lô đến hôm nay, vẫn một việc mỗi lô |
| 11 | E | Low | đã sửa | zrsd001 "No data" là kết quả trung tính (DONE, không tính vào bộ đếm lỗi); test cũ khẳng định hành vi ngược đã đổi theo |
| robot-3 | E | Low | chấp nhận rủi ro | Lệnh tay zrsd004 chờ bị đợt kế toán đóng thay đúng chủ ý, còn dấu vết trong nhật ký sự kiện |
| D8 | F | Low | đã sửa | Ghi chú cập nhật ở plan `261116-1520`; `docs/deployment-guide.md` đã đúng |
| H6 | F | Low | đã sửa | Ghi chú cập nhật ở plan `261116-1354` |
| tax-6 | F | Low | đã sửa | Runbook không còn ghi "chưa chạy SAP thật"; ghi chú 20 cột ở plan `261119-0605`. Biên bản chạy thử từng màn hình vẫn chưa viết |
| robot-5, 6, 7 | F | Low | đã sửa | Ghi chú cập nhật ở plan `261113-1142` |
| Đơn nhiều DO trên một SO; chặn cứng DO đơn hủy | — | Medium | ngoài phạm vi | Cần kiểm production / chờ chủ dự án quyết; có trong mục "Rủi ro đã chấp nhận" của sổ tay vận hành |

Các Low còn lại của báo cáo từng vùng không có mã ở bảng này được đóng bằng "chấp nhận rủi ro" theo plan sửa: những mục cần người vận hành biết đã vào mục "Rủi ro đã chấp nhận" của [sổ tay vận hành](../../docs/operations-runbook.md#rủi-ro-đã-chấp-nhận); các Info (Lazada không có Tiền Vô, DO chưa có hóa đơn do chưa đọc, hóa đơn khách ngoài ba sàn) giữ nguyên là Chấp nhận.

## Kết quả validate và trạng thái plan

- Cả 9 plan có `## Red Team Review` và `## Validation Log` (riêng `261116-1354` chỉ thêm red team vì đã có validation log). Hai plan nhẹ (`261113-1012`, `261116-0944`) ghi rõ "red team nhẹ".
- `261113-1230` đã sửa thành `in-progress` (phase 1–5 `completed`, phase 6 `in-progress`); `261113-1142` đặt `in-progress`.
- **Chạy thử production chưa có biên bản** cho `261119-0605`, `261119-0854`, `261113-1142`, `261116-1354` (phần cuối) và `261123-0312`.
- **Tiêu chí FAILED:** giả định "trợ giá nằm ở cột Sale" của `261111-0755` (xem High thứ hai); luân phiên sao lưu 14 ngày của `261116-1520` đã bị thay bằng quy tắc 15 bản; plan `261119-0605` ghi "19 cột" trong khi file nay có 20.

## Bất biến chạy trên DB dev

Chi tiết trong [báo cáo bất biến](data-integrity-audit-261123-1400-invariants.md) và [số đếm nền](data-integrity-audit-261123-1310-baseline.md). Tóm tắt: 15 nhóm bất biến, mọi bất biến kiểm được đều đạt; I7b, I8, I11, I14, I15 chưa có dữ liệu để kết luận. Một mục cần xác minh trên production: 66 dòng quyết toán nằm trong khoảng ngày của dữ liệu đơn mà không khớp đơn nào (Shopee 56, TikTok 10).

## Giới hạn của lần rà soát

- Các phase 2–6 do agent làm, kết quả đã được bạn duyệt chung một lượt, chưa duyệt từng phát hiện một.
- Các test tái hiện chạy được: TikTok bỏ dòng, hóa đơn trùng DO, công thức Excel. Phần lớn phát hiện còn lại dựa trên đọc mã vì DB test dùng chung bị khóa khi nhiều agent chạy song song.
- Chưa chạy lại cả bộ test (một lần có 464 passed và 1 lỗi `DeadlockDetected` do dùng chung DB test).
- Không có thay đổi nào trong `src/`, `tests/`, `migrations/`; không có commit.

## Việc tiếp theo đề xuất

1. Kết nối chỉ đọc tới production (hoặc bản phục hồi mới nhất) rồi chạy lại `invariants.sql` cùng các câu SQL cần chạy của phase 2–5 (nằm trong file phát hiện của từng phase); mục tiêu chính là F1, I7b, I8, I11, I14, I15.
2. `/ak-fix` cho ba lỗi High (đơn hủy còn SO; hóa đơn trùng DO; file cũ ghi đè hóa đơn mới) sau khi chủ dự án trả lời các câu hỏi trong Validation Log.
3. Quyết định về chênh lệch giá trị SO (17/117) trước khi gửi thêm đợt kế toán.

## Câu hỏi chưa giải quyết

- SAP có liệt kê hóa đơn đã hủy trong zrsd003 không? (ZBA1 là loại chứng từ billing trong báo cáo, không phải tcode; câu hỏi vẫn mở.) Và production có đơn tách nhiều DO không (không đọc được từ DB vì zrsd004 gốc đã xóa)?
- 5 dòng quyết toán Shopee của đơn ngày 2026-11-11 không có đơn trong hệ thống có đúng là đơn xử lý tay trước khi chạy thật không?
- Khi nào bật `--apply` cho dọn file, và có thêm `exports/` vào sao lưu hằng ngày không?
- Khi nào xóa DB `shoponline` cũ trên `Alkana_IT`?
