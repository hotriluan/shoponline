# Phase 6: Tài liệu và chạy thử Production

## Bối cảnh

Quy trình hằng ngày bước 10 đến 12 nằm ở [daily-operations.md](../../docs/daily-operations.md); bảng việc của robot ở [robot-runbook.md](../../docs/robot-runbook.md) (dòng 12 nhắc liên kết "Tải file kế toán" ở trang Robot SAP và Báo cáo SAP, dòng 35 khuyên dùng form lệnh tay để lấy file cho ngày không thuộc lô, điều không còn đúng); sự cố vận hành ở [operations-runbook.md](../../docs/operations-runbook.md) (dòng 78 nói về lỗi file `zrsd004` bị xóa của route cũ); kiến trúc ở [system-architecture.md](../../docs/system-architecture.md); thời hạn lưu dữ liệu ở [security-and-data-retention.md](../../docs/security-and-data-retention.md) (dòng 22 dựa trên "chưa có file gửi kế toán").

## Yêu cầu

- `daily-operations.md`: viết lại bước gửi kế toán theo trang **Gửi kế toán** (bắt đầu đợt, theo dõi, đối chiếu, chốt), một file cho cả 3 sàn và mọi ngày goods issue chưa gửi.
- `robot-runbook.md`: sửa dòng 12 và 35; cập nhật dòng `read_zrsd004` (đọc từng ngày trong một đợt; "SAP chưa có DO" là kết quả hợp lệ, không tăng bộ đếm lỗi; lệnh tay chỉ nhập dữ liệu, file kế toán lấy ở trang Gửi kế toán).
- `operations-runbook.md`:
  - một sàn đọc lỗi (Đọc lại, tải tay, chốt thiếu sàn và hệ quả cho lần sau);
  - đơn nằm ở khung "Chưa thấy DO" và cách xác nhận;
  - đợt `OPEN` bị bỏ quên (Hủy đợt);
  - chốt nhầm: dùng `accounting-run revoke` (không dùng SQL), nêu thêm việc báo kế toán không dùng file đó;
  - DO bị hủy sau khi đã chốt (vẫn báo kế toán bằng tay);
  - các lệnh `accounting-ledger list/add/remove/cutoff`;
  - sửa dòng 78 cho đúng với file đã chốt (file đã chốt không bị retention xóa).
- `system-architecture.md`: thêm sổ DO đã gửi, mốc ngày và đợt xuất vào sơ đồ và bảng mô-đun.
- `security-and-data-retention.md`: sửa dòng 22 (tên, địa chỉ khách được giữ tới khi DO vào sổ); sổ chỉ chứa số Delivery; file đã chốt và file nguồn đợt đang mở không bị xóa theo thời hạn.
- Sửa ghi chú rủi ro trong [kế hoạch lệnh robot theo yêu cầu](../261113-1142-robot-manual-run-on-demand/plan.md) cho khớp phase 3.

## Chạy thử trên Production (cần chủ dự án có mặt)

1. Sao lưu database, chạy migration `0006`.
2. `accounting-ledger list`: chủ dự án duyệt sổ nền và mốc ngày. DO nào chưa thật sự gửi kế toán thì `remove` (và đưa mốc về trước ngày của chúng bằng `cutoff --set` nếu cần); DO đã gửi mà còn thiếu thì `add`. Ghi nhận các giới hạn: sổ nền từ đơn chỉ có DO đầu của mỗi SO, nên phần còn lại dựa vào mốc ngày.
3. Xác nhận trên SAP thật hai điều và ghi kết quả vào `plans/reports/`: ô `P_WADAT` lọc theo ngày goods issue thực hay dự kiến (nếu là dự kiến, cửa sổ từng ngày có thể không cần, hoặc cần đổi); cột `Total Movement Goods Stat` sau goods issue là `C`.
4. Bắt đầu một đợt thật với một ngày có đủ 3 sàn. Kiểm: số cặp xếp việc, robot không dừng khi có cặp "chưa có DO".
5. So **bản nháp** với file làm tay của kế toán cho cùng DO: từng ô, hai dòng tổng, thứ tự dòng, và thứ tự các đơn vị ở dòng tổng. So thêm với một file thật chỉ có một đơn vị (một dòng tổng) và một file thật có đơn vị thứ ba nếu có, để xác nhận bảng thứ tự đơn vị. Lệch thì sửa quy tắc dòng tổng ở phase 2 trước khi dùng thật.
6. Chốt (chỉ sau khi chủ dự án đồng ý), rồi bắt đầu đợt mới: file mới không chứa DO vừa chốt.

## Tệp được sửa

Các file tài liệu ở trên; không đổi mã.

## Các bước

1. Cập nhật tài liệu sau khi phase 5 qua hết test.
2. Kiểm liên kết và các số liệu trích (tên trang, nút, lệnh CLI) so với mã nguồn.
3. Chạy thử Production theo danh sách trên và ghi kết quả vào `plans/reports/`.

## Kiểm tra

- Mọi liên kết tương đối trong tài liệu sửa đều mở được; tên nút và lệnh khớp mã.
- Bước 5 của chạy thử đạt: bản nháp khớp file làm tay.

## Rủi ro và hoàn tác

- Chạy thử trên dữ liệu thật ghi sổ khi chốt. Các bước 4 và 5 chỉ dùng bản nháp; chỉ chốt ở bước 6 sau khi chủ dự án đồng ý. Chốt nhầm thì dùng `accounting-run revoke <run_id> --yes`, rồi báo kế toán không dùng file đã gửi.
