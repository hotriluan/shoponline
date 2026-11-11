---
title: "Đơn sàn TMĐT từ file Excel tới file gửi kế toán, có robot SAP cho Shopee"
description: "Admin tải file đơn Shopee, TikTok lên; hệ thống sinh file đơn hàng cho sales admin, đối chiếu SO trong SAP và xuất file zrsd004 gửi kế toán; robot tạo SO và DO cho Shopee là chế độ chọn thêm."
status: in-progress
priority: P1
effort: 36d
tags: [feature, backend, database, infra, critical]
blockedBy: []
blocks: []
created: 2026-11-11
---

# Đơn sàn TMĐT từ file Excel tới file gửi kế toán, có robot SAP cho Shopee

## Overview

Admin shop online tải file "chờ giao hàng" của sàn lên hệ thống. Hệ thống ánh xạ sản phẩm sang mã SAP và sinh file đơn hàng cho sales admin. Sau khi SO và DO có trong SAP, hệ thống đối chiếu và xuất file `zrsd004` có thêm mã đơn hàng, tên khách hàng, địa chỉ để gửi kế toán. Việc tạo SO và DO do người làm (chế độ thủ công) hoặc do robot làm (chỉ Shopee).

Kế hoạch này thay cho [kế hoạch 12 phase](../261111-0431-ecommerce-sap-automation/plan.md). Hợp đồng, quy tắc nghiệp vụ và bằng chứng nằm trong [báo cáo brainstorm](../reports/brainstorm-261111-1425-excel-import-sap-order-flow.md); mọi phase đọc báo cáo đó trước.

## Hợp đồng

- **Ràng buộc:** SAP chỉ qua GUI Scripting, một phiên; thử trên QA, rồi shadow, rồi mới ghi thật. Không mã đơn nào có hai SO. Mã đơn luôn là chuỗi. Ở chế độ thủ công hệ thống không ghi gì vào SAP. Một máy Windows, Python, PostgreSQL, web render phía máy chủ, không Docker, không LLM trong đường nghiệp vụ.
- **Ngoài phạm vi:** việc của kế toán (billing, sales invoice, hóa đơn VAT, BKAV, đối soát), API sàn, in vận đơn, đẩy tồn kho, tự hủy DO và SO, robot ghi SAP cho TikTok và Lazada.
- **Quyết định kiến trúc:** một gói Python `shoponline` với hai tiến trình `web` và `robot` chạy bằng Task Scheduler. Hàng đợi việc SAP là bảng PostgreSQL. Một luồng duy nhất, chỉ rẽ ở bước "ai tạo SO và DO".

## Chế độ theo từng sàn

| Chế độ | Ai tạo SO và DO | Sàn dùng được |
|---|---|---|
| `manual` (mặc định) | Sales admin, theo file hệ thống sinh | Shopee, TikTok, Lazada |
| `shadow` | Sales admin; hệ thống so đề xuất của robot với SO thật | Shopee |
| `live` | Robot | Shopee |

Chế độ `manual` là tùy chọn lâu dài và là đường lùi khi robot dừng.

## Luồng một lô (một sàn, một ngày xử lý D)

1. Admin tải file sàn lên. Hệ thống ánh xạ mã SAP, đề xuất ngày goods issue, sinh file `ĐƠN HÀNG ONLINE`.
2. SO và DO được tạo trong SAP: sales admin ở chế độ `manual` và `shadow`, robot ở chế độ `live`.
3. Chế độ `manual` và `shadow`: admin bấm xác nhận "đã tạo SO và DO". Hệ thống lấy `zrsd001` với lựa chọn "Complete", lưu cặp mã đơn ↔ số SO và báo các điểm lệch.
4. Vào ngày goods issue, hệ thống lấy `zrsd004`, chèn ba cột và xuất file gửi kế toán. Đơn đã hủy DO không còn trong `zrsd004` nên tự rơi ra.

"Hệ thống lấy báo cáo" nghĩa là admin tải file báo cáo lên (phase 4), và từ phase 5 là robot tự đọc SAP.

Ngày goods issue là ngày làm việc kế tiếp (bỏ thứ Bảy, Chủ nhật). Nếu ngày đó rơi sang tháng khác thì dùng chính ngày D. Admin sửa được ngày này.

## Phases

| # | Phase | Chặng | Công | Phụ thuộc | Status |
|---|-------|-------|------|-----------|--------|
| 1 | [Nền tảng dự án](./phase-01-start.md) | 1 | 2d | — | Done (trừ việc chủ dự án chuyển `passwordapi.txt`) |
| 2 | [Lõi dữ liệu và nhập file Shopee, TikTok](./phase-02-data-core-and-shopee-import.md) | 1 | 5d | 1 | Done (Lazada chờ file mẫu) |
| 3 | [Web UI và file đơn hàng cho sales admin](./phase-03-web-ui-and-sap-order-file.md) | 1 | 4d | 2 | Done (chờ sales admin dùng thử) |
| 4 | [Xác nhận lô, báo cáo SAP và file gửi kế toán](./phase-04-sap-report-import-and-accounting-file.md) | 1 | 4d | 3 | In progress: mã xong; chờ triển khai máy thật và 10 ngày chạy song song |
| 5 | [Khung robot và đọc báo cáo SAP](./phase-05-robot-framework-and-sap-report-reading.md) | 2 | 6d | 4 | Blocked: chờ bản ghi recorder, user SAP robot, cổng G1 |
| 6 | [Robot tạo SO Shopee: shadow rồi ghi thật](./phase-06-robot-sales-order-shadow-to-live.md) | 3 | 5d | 5 | Pending |
| 7 | [Robot tạo SO có giảm giá ZDI1](./phase-07-robot-discounted-sales-order-zdi1.md) | 3 | 3d | 6 | Pending |
| 8 | [Robot tạo DO và post goods issue](./phase-08-robot-delivery-and-goods-issue.md) | 3 | 4d | 6 | Pending |
| 9 | [Vận hành và bàn giao](./phase-09-operations-and-handover.md) | — | 3d | 1–8 | Pending |

Chặng 1 (phase 1–4) là chế độ thủ công hoàn chỉnh. Phase 7 và 8 độc lập với nhau. Cho tới khi phase 7 xong, robot chuyển đơn có trợ giá cho người làm tay.

## Việc của chủ dự án, bắt đầu ngay vì phụ thuộc người khác

- File "chờ giao hàng" tải từ trang quản lý Lazada. Chưa có thì chưa viết được bộ đọc Lazada.
- Bảng ánh xạ đầy đủ sản phẩm Shopee và TikTok sang mã SAP.
- Văn bản chấp thuận của cấp trên và IT cho robot thao tác SAP; user SAP riêng cho robot trên QA và hệ thống thật.
- Máy chạy thật (riêng, bật liên tục) và nơi sao lưu ngoài máy: ổ mạng công ty và Google Drive.
- Ảnh màn hình lọc của `zrsd004`. Ghi recorder trên QA cho `zrsd001`, `zrsd004`, tạo SO, `VK11` hoặc `VK12` cho `ZDI1`, tạo DO và post. Khi ghi tạo SO, thử nhập `ZDI1` tay trên tab điều kiện của dòng.

## Phân công

Claude Code viết mã, test, migration, tài liệu, và viết thao tác SAP từ bản ghi recorder. Chủ dự án chạy robot trên QA, xác nhận kết quả trong SAP, ký các cổng và đổi chế độ của sàn. Claude Code không chạy lệnh ghi vào SAP thật. Bí mật không dán vào hội thoại. Tên khách hàng thật không vào repo; dữ liệu test là dữ liệu tự dựng theo đúng cấu trúc file thật.

## Cổng chuyển chặng

| Cổng | Điều kiện đo được |
|------|-------------------|
| G1 – Chế độ thủ công dùng thật (sau phase 4) | 10 ngày làm việc liên tiếp, file gửi kế toán khớp từng ô với file admin tự làm; sales admin tạo SO từ file hệ thống sinh; mọi SO gõ sai mã đơn đều được hệ thống chỉ ra. |
| G2 – Robot ghi SO Shopee thật (trong phase 6) | Đơn mẫu tạo đúng trên QA, chạy lại không trùng. Ít nhất 100 đơn liên tiếp và 10 ngày làm việc ở chế độ `shadow`, giá trị và mã vật tư hệ thống tính khớp 100% với SO sales admin tạo. |
| G3 – Robot ghi DO thật (trong phase 8) | 30 SO liên tiếp robot tạo thật không trùng, không lệch giá trị; tạo DO và post với ngày goods issue tương lai chạy đúng trên QA, gồm cả trường hợp cuối tháng. |

## Success Criteria

- [ ] Chế độ `manual`: từ file sàn tới file gửi kế toán, admin không còn chép tay hay VLOOKUP, trừ việc nhập tên khách hàng.
- [ ] Chế độ `live`: đơn Shopee không có trợ giá đi từ file sàn tới DO đã post mà không ai gõ tay vào SAP.
- [ ] Không mã đơn nào có hai SO.
- [ ] Giá trị SO trong `zrsd001` khớp giá trị tính từ file sàn cho mọi đơn.
- [ ] Nhập lại cùng một file không đổi dữ liệu; file thiếu cột bắt buộc bị từ chối toàn bộ.
- [ ] Diễn tập dựng lại máy và khôi phục database từ bản sao lưu thành công.

## Rủi ro chính

- **Sales admin gõ sai mã đơn vào `PO No`.** Hệ thống liệt kê SO của sàn trong ngày không khớp đơn nào để admin nối tay (phase 4).
- **Bản ghi `ZDI1` dùng chung cho mọi SO Shopee.** Bản ghi sót lại làm SO sau bị giảm giá sai. Phase 7 có bốn chốt chặn và ưu tiên cách nhập tay trên dòng SO nếu SAP cho phép.
- **Robot không biết SO đã lưu hay chưa khi mất phiên.** Việc tạo chứng từ có trạng thái "chưa rõ"; từ đó chỉ đi tiếp sau khi tra `zrsd001` theo `PO No`.
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

1. `ZDI1` có nhập tay được trên dòng SO không? Trả lời khi ghi recorder; chỉ ảnh hưởng phase 7.
2. `zrsd004` lọc theo ngày nào? Cần ảnh màn hình lọc; ảnh hưởng phase 5.

<!-- slug: shopee-excel-to-sap-order-flow -->
