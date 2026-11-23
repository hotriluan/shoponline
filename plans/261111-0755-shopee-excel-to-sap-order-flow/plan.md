---
title: "Đơn sàn TMĐT từ file Excel tới file gửi kế toán, có robot đọc báo cáo SAP"
description: "Admin tải file đơn Shopee, TikTok lên; hệ thống sinh file đơn hàng cho sales admin, đối chiếu SO trong SAP và xuất file zrsd004 gửi kế toán; robot chỉ đọc zrsd001 và zrsd004 trên Production."
status: in-progress
priority: P1
effort: 24d
tags: [feature, backend, database, infra, critical]
blockedBy: []
blocks: []
created: 2026-11-11
---

# Đơn sàn TMĐT từ file Excel tới file gửi kế toán, có robot đọc báo cáo SAP

## Overview

Admin shop online tải file "chờ giao hàng" của sàn lên hệ thống. Hệ thống ánh xạ sản phẩm sang mã SAP và sinh file đơn hàng cho sales admin. Sales admin tạo SO và DO trong SAP như hiện nay. Sau đó hệ thống đối chiếu và xuất file `zrsd004` có thêm mã đơn hàng, tên khách hàng, địa chỉ để gửi kế toán. Hai báo cáo `zrsd001` và `zrsd004` do admin tải lên, hoặc do robot tự đọc trên Production.

Kế hoạch này thay cho [kế hoạch 12 phase](../261111-0431-ecommerce-sap-automation/plan.md). Hợp đồng, quy tắc nghiệp vụ và bằng chứng nằm trong [báo cáo brainstorm](../reports/brainstorm-261111-1425-excel-import-sap-order-flow.md); mọi phase đọc báo cáo đó trước.

**Thay đổi phạm vi ngày 2026-11-12.** Bỏ robot tạo SO, DO và post goods issue (phase 6–8). Robot chỉ đọc báo cáo, làm thẳng trên Production và không dùng QA. Lý do và thiết kế lớp chặn T-code nằm trong [báo cáo brainstorm thu hẹp robot](../reports/brainstorm-261112-0915-robot-read-only-production-scope.md).

## Hợp đồng

- **Ràng buộc:** SAP chỉ qua GUI Scripting, một phiên. Hệ thống không ghi gì vào SAP. Robot chỉ vào được `ZRSD001` và `ZRSD004`; điều này do lớp chặn T-code trong mã bảo đảm. Mã đơn luôn là chuỗi. Một máy Windows, Python, PostgreSQL, web render phía máy chủ, không Docker, không LLM trong đường nghiệp vụ.
- **Ngoài phạm vi:** robot tạo SO, DO, post goods issue, `ZDI1`; chạy thử trên QA; việc của kế toán (billing, sales invoice, hóa đơn VAT, BKAV, đối soát); API sàn; in vận đơn; đẩy tồn kho; robot cho TikTok và Lazada ngoài việc đọc báo cáo chung.
- **Quyết định kiến trúc:** một gói Python `shoponline` với hai tiến trình `web` và `robot` chạy bằng Task Scheduler. Hàng đợi việc SAP là bảng PostgreSQL. Một luồng duy nhất cho mọi sàn. Cột chế độ trong `platform_setting` được giữ nguyên và không dùng; giá trị luôn là `manual`.

## Luồng một lô (một sàn, một ngày xử lý D)

1. Admin tải file sàn lên. Hệ thống ánh xạ mã SAP, đề xuất ngày goods issue, sinh file `ĐƠN HÀNG ONLINE`.
2. Sales admin tạo SO và DO trong SAP theo file đó.
3. Admin bấm xác nhận "đã tạo SO và DO". Hệ thống lấy `zrsd001` với lựa chọn "Complete", lưu cặp mã đơn ↔ số SO và báo các điểm lệch.
4. Vào ngày goods issue, hệ thống lấy `zrsd004`, chèn ba cột và xuất file gửi kế toán. Đơn đã hủy DO không còn trong `zrsd004` nên tự rơi ra.

"Hệ thống lấy báo cáo" nghĩa là admin tải file báo cáo lên (phase 4), và từ phase 5 là robot tự đọc trên Production. Đường tải file lên vẫn giữ làm đường lùi.

Ngày goods issue là ngày làm việc kế tiếp (bỏ thứ Bảy, Chủ nhật). Nếu ngày đó rơi sang tháng khác thì dùng chính ngày D. Admin sửa được ngày này.

## Phases

| # | Phase | Chặng | Công | Phụ thuộc | Status |
|---|-------|-------|------|-----------|--------|
| 1 | [Nền tảng dự án](./phase-01-start.md) | 1 | 2d | — | Done (trừ việc chủ dự án chuyển `passwordapi.txt`) |
| 2 | [Lõi dữ liệu và nhập file Shopee, TikTok](./phase-02-data-core-and-shopee-import.md) | 1 | 5d | 1 | Done |
| 3 | [Web UI và file đơn hàng cho sales admin](./phase-03-web-ui-and-sap-order-file.md) | 1 | 4d | 2 | Done (chờ sales admin dùng thử) |
| 4 | [Xác nhận lô, báo cáo SAP và file gửi kế toán](./phase-04-sap-report-import-and-accounting-file.md) | 1 | 4d | 3 | In progress: mã xong, đã chạy thật trên máy phát triển (`C:\shoponline`); cổng G1 bắt đầu đếm từ 2026-11-12 |
| 5 | [Khung robot và đọc báo cáo SAP trên Production](./phase-05-robot-framework-and-sap-report-reading.md) | 2 | 6d | 4 | In progress: mã xong (khung robot, hàng đợi, màn hình, lớp chặn T-code, đọc `zrsd001`/`zrsd004` bằng xuất Excel; test với SAP GUI giả); còn chủ dự án xác nhận cổng bước 9, chạy thử 50 việc và 5 ngày song song trên Production |
| 6 | [Robot tạo SO Shopee](./phase-06-robot-sales-order-shadow-to-live.md) | — | — | — | Bỏ (2026-11-12) |
| 7 | [Robot tạo SO có giảm giá ZDI1](./phase-07-robot-discounted-sales-order-zdi1.md) | — | — | — | Bỏ (2026-11-12) |
| 8 | [Robot tạo DO và post goods issue](./phase-08-robot-delivery-and-goods-issue.md) | — | — | — | Bỏ (2026-11-12) |
| 9 | [Vận hành và bàn giao](./phase-09-operations-and-handover.md) | — | 3d | 1–5 | In progress: xóa theo thời hạn (90 ngày, chế độ liệt kê), sổ tay vận hành, tài liệu kiến trúc và bảo mật xong; còn chuyển máy, diễn tập dựng lại và sự cố, rà soát quyền trên máy thật, đào tạo |

Chặng 1 (phase 1–4) là chế độ thủ công hoàn chỉnh. Chặng 2 (phase 5) thay việc admin tải báo cáo lên bằng robot đọc.

## Việc của chủ dự án, bắt đầu ngay vì phụ thuộc người khác

- ~~File "chờ giao hàng" tải từ trang quản lý Lazada.~~ Đã có (`docs/lazadaexport.xlsx`), bộ đọc Lazada xong 2026-11-13.
- Bảng ánh xạ đầy đủ sản phẩm Shopee và TikTok sang mã SAP.
- User SAP riêng cho robot trên Production, vào được `zrsd001` và `zrsd004` (IT đã đồng ý, license đã có). Khuyến nghị nhờ IT giới hạn role chỉ gồm hai báo cáo này, nhưng đây không phải điều kiện.
- Máy chạy thật (riêng, bật liên tục) và nơi sao lưu ngoài máy: ổ mạng công ty và Google Drive. Tạm thời dùng chung máy phát triển (xem Quyết định ngày 2026-11-12).
- Ghi recorder trên Production bằng user robot cho `zrsd001` và `zrsd004` (đã có ảnh màn hình lọc và màn hình kết quả của cả hai).

## Quyết định ngày 2026-11-12

- **Cổng G1 bắt đầu ngày 2026-11-12 (ngày 1).** Đếm 10 ngày làm việc liên tiếp; ngày nào có ô lệch thì đếm lại từ đầu.
- **Tạm dùng chung máy phát triển làm máy chạy thật, cả web lẫn robot.** Bản chạy thật nằm ở `C:\shoponline`, tách khỏi thư mục dev `C:\dev\shoponline`. Khi hoàn thiện sẽ chuyển sang một máy riêng; việc chuyển máy nằm trong phase 9. Đánh đổi được chấp nhận trong thời gian này: web, sao lưu và robot chỉ chạy khi `luanh` đăng nhập; robot dùng chung SAP GUI với người dùng máy nên không chạy robot khi đang làm việc tay trên SAP; server dev phải đổi cổng khác 8750.

## Phân công

Claude Code viết mã, test, migration, tài liệu, và viết thao tác SAP từ bản ghi recorder. Chủ dự án chạy robot trên Production, xác nhận kết quả và ký các cổng. Claude Code không chạy robot trên SAP thật. Bí mật không dán vào hội thoại. Tên khách hàng thật không vào repo; dữ liệu test là dữ liệu tự dựng theo đúng cấu trúc file thật.

## Cổng chuyển chặng

| Cổng | Điều kiện đo được |
|------|-------------------|
| G1 – Chế độ thủ công dùng thật (sau phase 4) | 10 ngày làm việc liên tiếp, file gửi kế toán khớp từng ô với file admin tự làm; sales admin tạo SO từ file hệ thống sinh; mọi SO gõ sai mã đơn đều được hệ thống chỉ ra. |
| Robot chạy lần đầu trên Production (trong phase 5) | Lớp chặn T-code đã có, test chứng minh không có đường nào vào T-code ngoài `ZRSD001` và `ZRSD004`. |

Cổng G2 (robot ghi SO) và G3 (robot ghi DO) đã bỏ cùng phase 6–8.

## Success Criteria

- [ ] Từ file sàn tới file gửi kế toán, admin không còn chép tay hay VLOOKUP, trừ việc nhập tên khách hàng.
- [ ] Robot đọc `zrsd001` và `zrsd004` trên Production cho kết quả giống hệt file admin tải lên trong 5 ngày làm việc liên tiếp.
- [ ] Robot không vào được T-code nào ngoài `ZRSD001` và `ZRSD004`; gặp T-code lạ thì dừng và tự tạm dừng.
- [ ] Mọi mã đơn có hai SO, hoặc SO có giá trị khác giá trị tính từ file sàn, đều được hệ thống chỉ ra.
- [ ] Nhập lại cùng một file không đổi dữ liệu; file thiếu cột bắt buộc bị từ chối toàn bộ.
- [ ] Diễn tập dựng lại máy và khôi phục database từ bản sao lưu thành công.

## Rủi ro chính

- **Sales admin gõ sai mã đơn vào `PO No`.** Hệ thống liệt kê SO của sàn trong ngày không khớp đơn nào để admin nối tay (phase 4).
- **Robot vào T-code khác hai báo cáo.** Lớp chặn T-code kiểm tra trước và sau mỗi thao tác; danh sách T-code nằm cứng trong mã. Lớp chặn không ngăn được người dùng user robot đăng nhập bằng tay; giới hạn role phía SAP là lớp bảo vệ thêm.
- **Robot đọc sai làm file gửi kế toán sai.** Chạy song song 5 ngày với file tải lên; đường tải tay giữ làm đường lùi.
- **Robot ghi nhầm hệ thống.** Mỗi việc mang tên hệ thống đích; robot kiểm tra phiên đang mở trước khi làm.
- **Sàn đổi mẫu file.** Cột nhận diện theo tên; thiếu cột bắt buộc thì từ chối cả file.
- **Một máy là điểm hỏng duy nhất.** Sao lưu mã hóa ra ngoài máy từ phase 4; diễn tập dựng lại ở phase 9; khi máy dừng, admin quay lại làm Excel tay.

## Giả định đang dùng, cần chủ dự án xác nhận

1. Số tiền trợ giá ghi vào cột `Sale` của file `ĐƠN HÀNG ONLINE`, theo một đơn vị sản phẩm. File mẫu Shopee có thêm cột `giảm giá`; file TikTok và Lazada chỉ có `Sale`.
2. Với TikTok, trợ giá là `SKU Seller Discount` cộng `SKU Platform Discount`, chia cho số lượng. File mẫu TikTok chỉ có một đơn và hai cột này đều bằng 0.
3. Lô được xác nhận trong ngày D; file gửi kế toán xuất vào ngày goods issue.
4. Dòng Lazada trong `zrsd004` được điền mã đơn từ `zrsd001`; từ 2026-11-13 tên (`billingName`) và địa chỉ (`billingAddr`) lấy từ file Lazada, admin chỉ sửa khi cần.
5. Cột `Created Time` của TikTok có dạng ngày/tháng/năm.

## Câu hỏi còn mở

1. User SAP của robot là `AL17016` (quyết định ngày 2026-11-12; không dùng `BASIS01`). Ngày 2026-11-12 `AL17016` mở được màn hình đầu của `VA02`, tức là có quyền T-code sửa SO, nên lớp chặn T-code là hàng rào duy nhất phía robot. Chủ dự án quyết định giữ nguyên quyền của `AL17016` và bảo vệ máy robot (phase 9, bước 4); không ai khác dùng `AL17016`. Ngày 12.11.2026 `AL17016` được đổi từ Dialog sang **Service**, nên mật khẩu không hết hạn (chu kỳ 180 ngày của hệ thống chỉ áp dụng cho user Dialog). User Service không báo đăng nhập trùng, nên việc phát hiện người khác dùng mật khẩu dựa vào bảo vệ máy robot ở phase 9.

Đã trả lời ngày 2026-11-12:
- `zrsd004` được lọc theo Sold-to Party và Actual GI (ngày goods issue). Production là `AEP`, client 300.
- Danh sách T-code được phép là `S000` (đăng nhập, client hiện `000`), `SESSION_MANAGER`, `ZRSD001`, `ZRSD004`. Đã kiểm bằng `AL17016`; user không có start transaction. Scripting đọc được màn hình đăng nhập, nên robot tự đăng nhập lại bằng scripting được.

## Red Team Review

Ngày 2026-11-23. Bốn lens (Security Adversary, Failure Mode Analyst, Assumption Destroyer, Scope & Complexity Critic) cộng lens trùng/sót, chạy bằng cách soi mã và test thật; một người soi, tự phân xử. Số đếm là dev DB, 2026-11-23, không phải production. Chi tiết, SQL và test tái hiện: [báo cáo phase 2](../reports/data-integrity-audit-261123-1320-orders-sap.md). Lens Scope & Complexity và Security không có phát hiện vượt phạm vi toàn vẹn dữ liệu (phạm vi là yêu cầu của chủ dự án).

| # | Phát hiện | Mức | Bằng chứng trong mã | Disposition | Hướng xử lý |
|---|-----------|-----|---------------------|-------------|-------------|
| 1 | Đơn đã hủy mà SO còn trong SAP: không cảnh báo; DO của SO đó vẫn vào file kế toán kèm mã đơn đã hủy | High | `reconcile/so_link.py:143-146`, `:252-261`, `:269`, `:313`; `exports/accounting_workbook.py:54-58`. Dev: 2 đơn CANCELLED, 1 có SO nối, 1 SO không nối với đơn nào | Accept (chủ dự án duyệt 2026-11-23) | `/ak-fix`: mục "SO của đơn đã hủy" trong `batch_report`; cảnh báo ở file kế toán |
| 2 | 17/117 đơn đã nối (14,5%) có giá trị SO khác giá trị tính từ file sàn mà vẫn giao và gửi kế toán; chỉ có danh sách báo cáo, không có cổng | High | `so_link.py:268-296`, `:303-318`; `accounting/runs.py:99-110`. Dev: Lazada 8, TikTok 5, Shopee 4 (4 đơn Shopee lệch ±1 đồng) | Accept (chủ dự án duyệt 2026-11-23) | Xác nhận Giả định 1 và 2; sau đó cổng chặn hoặc ghi nhận chấp nhận lệch, dung sai làm tròn |
| 3 | Một SO nhiều DO: chỉ DO đầu được lưu, DO thứ hai không vào hóa đơn và tiến độ theo đơn | Medium | `so_link.py:304-306`, `:314`; `db/models.py:118`; `exports/sales_history_workbook.py:183,228`; `reconcile/order_progress.py:33,67`. Dev: 0 trường hợp | Accept (chủ dự án duyệt 2026-11-23) | SQL #6 trên production; nếu có thì bảng DO riêng, tạm cảnh báo |
| 4 | Đơn đã có ở lô D1 mà nhập lại cho D2 vẫn ở D1, đếm `unchanged`, lô D2 thiếu đơn không báo | Medium | `importers/order_import.py:151-155`, `:178-179` | Accept (chủ dự án duyệt 2026-11-23) | Hiện "đã có ở lô khác" trên trang kết quả nhập |
| 5 | Sàn đổi số lượng/giá sau khi đơn đã có SO: bỏ qua im lặng, báo cáo lệch so với dữ liệu cũ nên không thấy | Medium | `order_import.py:178-179`; `so_link.py:274-296` | Accept (chủ dự án duyệt 2026-11-23) | Ghi sự kiện và hiện trên trang lô, không ghi đè |
| 6 | TikTok: dòng có mã đơn rỗng hoặc không phải chữ số bị bỏ im lặng (đã tái hiện) | Medium | `importers/tiktok_orders.py:58-60`; `importers/excel_table.py:142-143` (ô số mất chữ số) | Accept (chủ dự án duyệt 2026-11-23) | Chỉ bỏ dòng mô tả và dòng trống; dòng có dữ liệu mà mã sai thì từ chối cả file |
| 7 | Đơn MAPPING_ERROR/NEED_REVIEW không vào file đơn hàng và không nằm trong "READY chưa có SO" sau khi xác nhận lô | Medium | `exports/order_workbook.py:63-64`; `so_link.py:247-250`; `web/routes/batches.py:90-92` | Accept (chủ dự án duyệt 2026-11-23) | `missing_so` lấy mọi đơn mở chưa có SO; cảnh báo ở nút xác nhận |
| 8 | `so_number`, `do_number` không UNIQUE ở DB | Low | `db/models.py:117-118`; `migrations/versions/0002_core_schema.py:125` | Accept (chủ dự án duyệt 2026-11-23) | UNIQUE từng phần khi có plan sửa; chấp nhận trước mắt |
| 9 | Nhập chồng đồng thời (hai người, hoặc web và robot) gây `IntegrityError`, rollback sạch, không hỏng dữ liệu | Low | `order_import.py:41-52,151-176`; `so_link.py:80-85` | Reject (chấp nhận rủi ro; khóa UNIQUE chặn trùng, kiểm bằng `db/models.py:107` và khóa chính `sap_so_ref`) | Ghi vào sổ tay vận hành |
| 10 | Tải file đơn hàng hai lần trước khi đọc zrsd001 có thể làm sales admin tạo SO hai lần; chỉ bắt được sau đó bằng `duplicate_po` | Low | `exports/order_workbook.py:63`; `so_link.py:262-266` | Reject (chấp nhận rủi ro; `duplicate_po` đã bắt, dev 0 PO trùng) | Nhắc trong sổ tay |
| 11 | zrsd001 "No data" tính vào bộ đếm lỗi liên tiếp, có thể tự dừng robot | Low | `saprobot/worker.py:363-368`, `:462`; `sapjobs/queue.py:287-299`. Dev: việc #35 | Accept (chủ dự án duyệt 2026-11-23) | Coi là trung tính khi lô chưa có SO, hoặc chấp nhận |
| 12 | `sap_so_ref` không bao giờ bị xóa; SO hủy rồi tạo lại cùng PO No làm đơn không tự nối được | Low | `so_link.py:71-100`, `:150` | Reject (chấp nhận rủi ro; `duplicate_po` đã báo, nối tay là đường xử lý đã có tại `so_link.py:164-188`) | Không đổi |

## Validation Log

Ngày 2026-11-23. Chỉ đối chiếu mã, test và dev DB (production không mở được); không hỏi chủ dự án trong lượt này, câu hỏi nằm ở cuối.

### Tiêu chí hoàn thành

| # | Tiêu chí | Kết quả | Bằng chứng |
|---|----------|---------|------------|
| 1 | Từ file sàn tới file gửi kế toán, không còn chép tay hay VLOOKUP, trừ tên khách | VERIFIED (mã) | `exports/order_workbook.py` sinh file đơn; `exports/accounting_workbook.py:147-177` điền mã đơn, tên, địa chỉ; Lazada lấy tên từ file (`importers/lazada_orders.py:92`). Dev: 5 đợt kế toán đã chốt |
| 2 | Robot đọc zrsd001/zrsd004 giống hệt file tải lên trong 5 ngày làm việc | UNVERIFIED | Mã dùng chung hàm nhập (`reconcile/report_ingest.py:1-5`, `saprobot/worker.py:110-135`); dev có 21 việc zrsd001 DONE, 23 zrsd004 DONE, nhưng không có bản ghi so sánh với file tải tay. Cần production |
| 3 | Robot không vào T-code nào ngoài ZRSD001/ZRSD004; gặp lạ thì dừng và tự tạm dừng | VERIFIED (test) | `tests/saprobot/test_guard.py` (danh sách cứng, T-code lạ bị từ chối, popup mở T-code lạ bị bắt); `saprobot/worker.py:354-361` tạm dừng khi vi phạm. Không kiểm trên SAP thật |
| 4 | Mã đơn có hai SO, hoặc SO lệch giá trị so với file sàn, đều được hệ thống chỉ ra | VERIFIED một phần | `so_link.py:262-296` chỉ ra cả hai, nhưng chỉ khi lô đã xác nhận và chỉ là danh sách; không chặn. 17/117 đơn dev lệch giá (phát hiện 2). Điểm mù: phát hiện 1, 5 |
| 5 | Nhập lại cùng file không đổi dữ liệu; file thiếu cột bắt buộc bị từ chối toàn bộ | VERIFIED | `tests/importers/test_order_import.py:51` (`test_import_twice_changes_nothing`); dev có 3 lần nhập lại, `new=0, updated=0`; `importers/excel_table.py:207-209` từ chối thiếu cột. Ngoại lệ TikTok: phát hiện 6 |
| 6 | Diễn tập dựng lại máy và khôi phục database từ bản sao lưu thành công | UNVERIFIED (ngoài phạm vi phase này) | Thuộc plan `261123-0312-backup-restore-server-migration` và `live-check-261123-1210-backup-restore.md`; không kiểm lại ở đây |

### Giả định đang dùng

| # | Giả định | Kết quả | Bằng chứng |
|---|----------|---------|------------|
| 1 | Trợ giá ghi vào cột `Sale` của file đơn hàng, theo một đơn vị sản phẩm | FAILED một phần | Cột `Sale` ghi `unit_subsidy` (`exports/order_workbook.py:29,102`), nhưng dev: 13 đơn có trợ giá có SO cao hơn giá trị kỳ vọng 300 đến 99.999 đồng (Lazada 8, TikTok 5), tức SO trong SAP có vẻ không áp trợ giá như file. Chưa biết nguyên nhân: sales admin bỏ trợ giá, hay `ZDI1` làm tròn khác. Cần chủ dự án |
| 2 | TikTok: trợ giá = Seller Discount + Platform Discount, chia số lượng | UNVERIFIED | Mã đúng như giả định (`importers/tiktok_orders.py:62-71`) và có test chia không hết; 5 đơn TikTok dev lệch giá (cùng bằng chứng giả định 1), chưa tách được nguyên nhân |
| 3 | Lô xác nhận trong ngày D, file kế toán xuất vào ngày goods issue | VERIFIED với một rủi ro | `web/routes/batches.py:168-197` (xác nhận), `accounting/runs.py:125-153` (đọc theo ngày dự kiến tới hôm nay, có cửa sổ lùi). Dev: SO nối đều có ngày chứng từ đúng ngày lô (0 lệch, SQL #3). Rủi ro: SO tạo ngày sau D không được đọc (zrsd001 lọc đúng một ngày, `saprobot/transactions/read_zrsd001.py:25-26`) nhưng bị báo "READY chưa có SO" (`so_link.py:247-250`) |
| 4 | Lazada: điền mã đơn từ zrsd001, tên và địa chỉ từ file Lazada | VERIFIED | `importers/order_import.py:226-247` (chỉ điền chỗ trống, không ghi đè sửa tay); `tests/importers/test_order_import.py:179,194`; `accounting_workbook.py:54-71` |
| 5 | `Created Time` của TikTok có dạng ngày/tháng/năm | VERIFIED (mã và dev) | `importers/tiktok_orders.py:40-41`; test `test_tiktok_day_first_dates`; `_check_dates` chặn đọc nhầm (`order_import.py:118-129`). Dev: 0 đơn lệch quá 3 ngày so với ngày lô (SQL #8) |

### Câu hỏi cho chủ dự án

1. Giả định 1 và 2: 17 trên 117 đơn đã giao có SO khác giá trị tính từ file sàn (13 đơn có trợ giá, SO cao hơn 300 đến 99.999 đồng; 4 đơn Shopee lệch 1 đồng). Đây là chủ ý (sales admin nhập giá khác file, hoặc `ZDI1` làm tròn) hay lỗi dữ liệu cần sửa, và có nên chặn hoặc bắt xác nhận trước khi gửi kế toán?
2. Đơn bị admin hủy mà SO đã tồn tại trong SAP (dev có 2): quy trình mong muốn là gì (ai hủy SO bên SAP, và hệ thống có cần báo để tránh DO của đơn hủy vào file kế toán)?
3. Có từng gặp một SO chia thành hai DO (giao một phần) trên production không? Nếu có, DO thứ hai cần vào hóa đơn và file lịch sử theo đơn không?
4. SO có thể được tạo sau ngày xử lý D (qua đêm hoặc cuối tuần) trên production không? Nếu có, robot cần đọc zrsd001 theo khoảng ngày thay vì một ngày.
5. Chủ dự án chấp nhận coi zrsd001 "No data" là trung tính (không tính vào bộ đếm tự dừng robot) hay giữ như hiện nay?
6. Việc chạy song song 5 ngày robot so với file tải tay (tiêu chí 2) đã làm chưa, và có biên bản không?

<!-- slug: shopee-excel-to-sap-order-flow -->

### Cập nhật 2026-11-23: chủ dự án trả lời

- **Chênh lệch giá trị SO (phát hiện 2) là cố ý.** Khi nhập SO trong SAP, chủ dự án bỏ qua trợ giá và chỉ nhập giá gốc, nên SO cao hơn giá trị tính từ file sàn đúng bằng trợ giá (13/17 đơn). 4 đơn Shopee còn lại lệch ±1 VND là sai số làm tròn. Phát hiện này hạ xuống Low (nhiễu trong báo cáo lô); giả định "trợ giá nằm ở cột Sale" chỉ cần ghi lại rằng SAP nhập giá gốc, không trừ trợ giá. Đề xuất còn lại: báo cáo lô nên cộng lại trợ giá trước khi so để khỏi báo nhầm.
- Bằng chứng production (2026-11-23, kết nối chỉ đọc): hàng đợi `sap_job` có "read_zrsd001" chạy lặp cho cùng một lô (lô 1 và 3 chạy 3 lần, lô 9 và 12 chạy 2 lần), nên việc đọc lại zrsd001 đã được dùng trên production. Không phân biệt được lần nào do nút "Đọc lại" và lần nào do luồng tự động.
