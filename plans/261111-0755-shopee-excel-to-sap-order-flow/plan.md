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
| 2 | [Lõi dữ liệu và nhập file Shopee, TikTok](./phase-02-data-core-and-shopee-import.md) | 1 | 5d | 1 | Done (Lazada chờ file mẫu) |
| 3 | [Web UI và file đơn hàng cho sales admin](./phase-03-web-ui-and-sap-order-file.md) | 1 | 4d | 2 | Done (chờ sales admin dùng thử) |
| 4 | [Xác nhận lô, báo cáo SAP và file gửi kế toán](./phase-04-sap-report-import-and-accounting-file.md) | 1 | 4d | 3 | In progress: mã xong; chờ triển khai máy thật và 10 ngày chạy song song |
| 5 | [Khung robot và đọc báo cáo SAP trên Production](./phase-05-robot-framework-and-sap-report-reading.md) | 2 | 6d | 4 | In progress: khung robot, hàng đợi, màn hình xong; còn lớp chặn T-code, thao tác đọc báo cáo (chờ bản ghi recorder), user SAP robot, cổng G1 |
| 6 | [Robot tạo SO Shopee](./phase-06-robot-sales-order-shadow-to-live.md) | — | — | — | Bỏ (2026-11-12) |
| 7 | [Robot tạo SO có giảm giá ZDI1](./phase-07-robot-discounted-sales-order-zdi1.md) | — | — | — | Bỏ (2026-11-12) |
| 8 | [Robot tạo DO và post goods issue](./phase-08-robot-delivery-and-goods-issue.md) | — | — | — | Bỏ (2026-11-12) |
| 9 | [Vận hành và bàn giao](./phase-09-operations-and-handover.md) | — | 3d | 1–5 | Pending |

Chặng 1 (phase 1–4) là chế độ thủ công hoàn chỉnh. Chặng 2 (phase 5) thay việc admin tải báo cáo lên bằng robot đọc.

## Việc của chủ dự án, bắt đầu ngay vì phụ thuộc người khác

- File "chờ giao hàng" tải từ trang quản lý Lazada. Chưa có thì chưa viết được bộ đọc Lazada.
- Bảng ánh xạ đầy đủ sản phẩm Shopee và TikTok sang mã SAP.
- User SAP riêng cho robot trên Production, vào được `zrsd001` và `zrsd004` (IT đã đồng ý, license đã có). Khuyến nghị nhờ IT giới hạn role chỉ gồm hai báo cáo này, nhưng đây không phải điều kiện.
- Máy chạy thật (riêng, bật liên tục) và nơi sao lưu ngoài máy: ổ mạng công ty và Google Drive.
- Ghi recorder trên Production bằng user robot cho `zrsd001` và `zrsd004` (đã có ảnh màn hình lọc và màn hình kết quả của cả hai).

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
4. Dòng Lazada trong `zrsd004` được điền mã đơn từ `zrsd001`; tên và địa chỉ do admin nhập theo mã đơn trên web cho tới khi có bộ đọc Lazada.
5. Cột `Created Time` của TikTok có dạng ngày/tháng/năm.

## Câu hỏi còn mở

1. User SAP của robot là `AL17016` (quyết định ngày 2026-11-12; không dùng `BASIS01`). Ngày 2026-11-12 `AL17016` mở được màn hình đầu của `VA02`, tức là có quyền T-code sửa SO, nên lớp chặn T-code là hàng rào duy nhất phía robot. Chủ dự án quyết định giữ nguyên quyền của `AL17016` và bảo vệ máy robot (phase 9, bước 4); không ai khác dùng `AL17016`. Ngày 12.11.2026 `AL17016` được đổi từ Dialog sang **Service**, nên mật khẩu không hết hạn (chu kỳ 180 ngày của hệ thống chỉ áp dụng cho user Dialog). User Service không báo đăng nhập trùng, nên việc phát hiện người khác dùng mật khẩu dựa vào bảo vệ máy robot ở phase 9.

Đã trả lời ngày 2026-11-12:
- `zrsd004` được lọc theo Sold-to Party và Actual GI (ngày goods issue). Production là `AEP`, client 300.
- Danh sách T-code được phép là `S000` (đăng nhập, client hiện `000`), `SESSION_MANAGER`, `ZRSD001`, `ZRSD004`. Đã kiểm bằng `AL17016`; user không có start transaction. Scripting đọc được màn hình đăng nhập, nên robot tự đăng nhập lại bằng scripting được.

<!-- slug: shopee-excel-to-sap-order-flow -->
