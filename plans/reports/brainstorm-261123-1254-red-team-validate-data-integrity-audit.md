# Brainstorm: red team, validate các plan còn thiếu và rà soát trùng/sót dữ liệu

Ngày: 2026-11-23. Người quyết định: chủ dự án.

## Hợp đồng

**Outcome.** Mọi plan còn hiệu lực đều đã qua red team và validate. Có một báo cáo, xếp theo mức độ nghiêm trọng, chỉ ra từng chỗ nghiệp vụ có thể làm trùng hoặc sót dữ liệu: đơn hàng, liên kết SO/DO, file gửi kế toán, file lịch sử Shop Online, hóa đơn (Tax Invoice từ zrsd003), tiền vô (file quyết toán), cùng chuyện xóa/khôi phục dữ liệu. Mỗi phát hiện có bằng chứng từ mã, từ test tái hiện hoặc từ truy vấn chỉ đọc trên production.

**Constraints.**
- Với plan đã làm thành mã, red team soi **mã đối chiếu với plan** (hợp đồng, quyết định đã chốt, tiêu chí hoàn thành), không chỉ soi văn bản plan.
- Plan chưa làm (`261113-1142-robot-manual-run-on-demand`) được red team và validate trên văn bản như quy trình thường lệ.
- Truy vấn production chỉ được đọc: dùng role chỉ đọc hoặc phiên `default_transaction_read_only = on`; không ghi, không sửa, không chạy migration. Kết quả truy vấn không được chứa tên khách, SĐT hay địa chỉ; chỉ ghi số đếm và mã đơn/DO.
- Không sửa mã nghiệp vụ trong plan này.
- Hai plan ít dính dữ liệu nghiệp vụ (`261113-1012-sap-connection-settings-web`, `261116-0944-win10-production-machine-hidden-tasks`) chỉ red team nhẹ, tập trung vào rủi ro mất hoặc trùng dữ liệu (tác vụ chạy hai lần, robot chạy song song, chuyển máy sót bảng).

**Non-goals.**
- Sửa lỗi. Mỗi phát hiện cần sửa sẽ thành plan hoặc lệnh `/ak-fix` riêng sau khi chủ dự án duyệt.
- Plan đã hủy `261111-0431-ecommerce-sap-automation`.
- Chạy lại red team/validate cho ba plan đã có đủ cả hai (`261113-1230-merged-accounting-file`, `261119-0719-tien-vo-column`, `261123-0312-backup-restore-server-migration`). Tuy vậy mã của chúng vẫn nằm trong phạm vi rà soát trùng/sót theo luồng dữ liệu.
- Rà soát UI, hiệu năng, bảo mật ngoài phạm vi toàn vẹn dữ liệu.

**Acceptance criteria.**
1. Mỗi plan trong danh sách dưới đây có mục `## Red Team Review` và `## Validation Log` ghi vào `plan.md`, hoặc có ghi chú vì sao được làm nhẹ.
2. Có một báo cáo rà soát toàn vẹn dữ liệu trong `plans/reports/`. Mỗi luồng dữ liệu ghi rõ: các bất biến (invariant) phải đúng, bằng chứng đã kiểm, phát hiện (mức Critical/High/Medium/Low), và đề xuất hướng sửa.
3. Mỗi bất biến có một câu SQL chỉ đọc đi kèm, đã chạy trên production, và ghi kết quả (số đếm).
4. Trạng thái plan lệch với thực tế được sửa trong văn bản plan. Ví dụ: `261113-1230-merged-accounting-file` ghi `pending` nhưng mã đã commit ở `1db7fdb`.

## Danh sách plan cần làm

| Plan | Trạng thái thực tế | Thiếu | Mức |
|---|---|---|---|
| 261111-0755 shopee-excel-to-sap-order-flow | phần lớn đã làm | red team, validate | đầy đủ, soi mã |
| 261113-1012 sap-connection-settings-web | đã làm | red team, validate | nhẹ |
| 261113-1142 robot-manual-run-on-demand | chưa làm | red team, validate | đầy đủ, soi văn bản |
| 261116-0944 win10-production-machine-hidden-tasks | đã làm | red team, validate | nhẹ |
| 261116-1354 shop-online-history-export | đã làm | red team | đầy đủ, soi mã |
| 261116-1520 delete-spent-files | đã làm | red team, validate | đầy đủ, soi mã (rủi ro sót do xóa sớm) |
| 261119-0605 zrsd003-tax-invoice-in-history | đã làm | red team, validate | đầy đủ, soi mã |
| 261119-0828 draft-history-file | hoàn thành | red team, validate | đầy đủ, soi mã |
| 261119-0854 month-pick-zrsd003-read | đã làm | red team, validate | đầy đủ, soi mã |

## Luồng dữ liệu cần rà soát và giả thuyết ban đầu

Các giả thuyết dưới đây suy ra từ khóa trong `src/shoponline/db/models.py`. Chúng chưa được kiểm chứng, và việc kiểm chứng là nhiệm vụ của plan.

1. **Đơn hàng** (`importers/*`, `sales_order` duy nhất theo `platform, platform_order_id`; `order_batch` duy nhất theo `platform, processing_date`). Cần xét: nhập lại cùng một file, hai file chồng ngày, đơn đổi trạng thái hoặc bị hủy sau khi nhập, đơn nhiều sản phẩm, một đơn xuất hiện ở hai lô.
2. **Liên kết SO/DO và báo cáo SAP** (`reconcile/report_ingest.py`, `so_link.py`, `sap_so_ref`). Cần xét: một đơn có nhiều DO, SO tạo tay, kết quả "No data", đọc lại cùng ngày.
3. **File gửi kế toán** (`accounting/ledger.py`, `runs.py`, `accounting_sent_delivery` theo DO). Cần xét: DO bị gửi hai lần, DO không bao giờ được gửi, baseline, đợt xuất bị hủy giữa chừng.
4. **File lịch sử Shop Online** (`sales_history_exported` theo đơn, `sales_history_file_order`, file nháp, chọn tháng). Cần xét: đơn có nhiều DO nhưng chỉ đánh dấu một lần; xóa file đã tải thì đơn có được trả lại hàng chờ không; đơn bị chặn vì chờ hóa đơn/tiền vô có bị kẹt mãi; đơn nằm ở ranh giới tháng.
5. **Hóa đơn** (`sap_tax_invoice` khóa theo DO). Cần xét: một DO có nhiều hóa đơn (hủy rồi xuất lại), hóa đơn xuất sau cửa sổ đọc tháng.
6. **Tiền vô** (`platform_settlement` duy nhất theo `platform, line_key`). Cần xét: nhiều dòng cho một đơn (điều chỉnh, số âm), cùng một dòng trong hai file khác nhau với `line_key` khác nhau, tiền vô thay đổi sau khi đã xuất (rủi ro đã chấp nhận trong plan tiền vô, chỉ cần kiểm tra lại).
7. **Xóa, retention, sao lưu/khôi phục** (`maintenance/retention.py`, `backup/restore.py`). Cần xét: xóa dữ liệu hoặc file trước khi nó được dùng xong; khôi phục bản cũ làm trạng thái "đã xuất" hoặc "đã gửi" quay về, dẫn tới xuất trùng.

## Trade-offs

- **Soi mã theo plan** (đã chọn). Cách này dựa vào giả định rằng plan ghi đủ hợp đồng để làm chuẩn so sánh. Nó yếu nhất khi plan bị lệch so với mã: khi đó lấy quyết định trong journal và tài liệu `docs/` làm chuẩn bổ sung.
- **Chỉ soi văn bản plan** (không chọn). Cách này giả định mã làm đúng plan. Giả định đó sai ngay ở plan merged-accounting-file, vốn đã lệch trạng thái.
- **Truy vấn production chỉ đọc** (đã chọn). Cách này giả định có thể mở kết nối chỉ đọc tới máy chạy thật (`AlkanaDuongPC`). Nó thất bại khi không có quyền mạng hoặc role; khi đó dùng phương án dự phòng là phục hồi bản sao lưu mới nhất vào một DB riêng trên máy dev.

## Hướng đi được chọn

Lập một plan gồm các phase sau:
1. Inventory, chuẩn bị truy cập chỉ đọc, sửa trạng thái plan bị lệch.
2. Red team và validate theo từng plan. Có thể chạy song song vì mỗi phase chỉ ghi vào `plan.md` của plan mình.
3. Rà soát toàn vẹn dữ liệu theo bảy luồng nói trên, mỗi luồng có bất biến, SQL và test tái hiện nếu cần. Test tái hiện chỉ để chứng minh, không được commit làm thay đổi hành vi.
4. Báo cáo tổng hợp kèm danh sách đề xuất sửa để chủ dự án duyệt.

## Câu hỏi còn mở

- Cách kết nối chỉ đọc tới DB production: đã có role chỉ đọc chưa, hay sẽ dùng phiên `read_only` bằng tài khoản ứng dụng? Plan sẽ kiểm tra `.env`/`docs/deployment-guide.md` trước, và chỉ hỏi nếu tài liệu không trả lời được.
