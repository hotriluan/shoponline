---
title: "Tự động hóa đơn hàng sàn TMĐT ↔ SAP ECC6"
description: "Đưa đơn Shopee, Lazada, TikTok Shop tự động vào SAP ECC6 qua GUI Scripting, ra dữ liệu hóa đơn BKAV và bảng kê đối soát hằng tháng."
status: cancelled
priority: P1
effort: 66d
tags: [feature, backend, database, api, infra, critical]
blockedBy: []
blocks: []
created: 2026-11-11
---

# Tự động hóa đơn hàng sàn TMĐT ↔ SAP ECC6

> **Đã hủy ngày 11/11/2026.** Thay bằng [kế hoạch nhập file Excel](../261111-0755-shopee-excel-to-sap-order-flow/plan.md), vì không đăng ký được API sàn và phạm vi kế toán được bỏ ra.

## Overview

Đưa đơn Shopee, Lazada, TikTok Shop của Alkana Việt Nam tự động vào SAP ECC6 (SO → DO → PGI → billing), ra dữ liệu hóa đơn BKAV và bảng kê đối soát hằng tháng đúng mẫu kế toán đang dùng. Con người chỉ duyệt ở điểm khó đảo ngược và xử lý ngoại lệ.

Nguồn yêu cầu: [kế hoạch V2](../../docs/e_commerce_sap_automation_plan_v2.md). Kế hoạch này giữ nguyên phạm vi và nguyên tắc của V2, bổ sung nền tảng dự án, cổng nghiệm thu đo được và thứ tự thực thi.

## Hợp đồng

- **Ràng buộc:** SAP chỉ qua GUI Scripting (`pywin32`), một phiên. Toàn bộ hệ thống chạy trên một máy Windows (máy robot): Python, PostgreSQL cài trực tiếp, không Docker. Không LLM trong đường nghiệp vụ. Không tạo trùng chứng từ. SAP là nguồn chuẩn số liệu kế toán. Mọi thao tác ghi SAP được thử trên hệ thống QA trước, rồi shadow trên hệ thống thật, rồi mới ghi thật; mở từng sàn một.
- **Ngoài phạm vi:** RFC/BAPI, tự đảo chứng từ, tự hạch toán thanh toán trước khi bảng kê khớp nhiều tháng, đổi cấu hình SAP phía Basis.
- **Quyết định kiến trúc:** một gói Python `shoponline` với ba tiến trình (`sync`, `web`, `robot`) chạy bằng Task Scheduler của Windows. Hàng đợi là bảng PostgreSQL với `SKIP LOCKED`, không Redis/Celery. Web UI render phía máy chủ (FastAPI + template), không SPA.

## Quyết định của chủ dự án (11/11/2026)

- Công ty có hệ thống SAP test/QA.
- Gộp tất cả lên máy Windows của robot, thay cho topology Docker + máy Windows của V2. Đánh đổi được chấp nhận: máy này là điểm hỏng duy nhất, nên sao lưu phải ra ngoài máy và phải có quy trình dựng lại máy (phase 12).
- Shopee đang bán, khoảng 20 đơn/ngày.
- Lập trình bằng Claude Code; xem mục Phân công.
- Máy chạy thật là một máy riêng, tách khỏi máy phát triển. Máy phát triển chỉ làm việc với database `shoponline_dev`, `shoponline_test` và hệ thống SAP QA; máy chạy thật chỉ có database `shoponline` và là nơi duy nhất ghi vào hệ thống SAP thật.
- Sao lưu ra hai nơi ngoài máy: ổ mạng công ty và Google Drive. Bản sao lưu được mã hóa trước khi rời máy vì có dữ liệu người mua.
- Ngày cao điểm cao nhất là 100 đơn/ngày.

## Bằng chứng định hình kế hoạch

- Sản lượng: Shopee khoảng 20 đơn/ngày; tháng 10/2026 có 31 hóa đơn Lazada và 44 hóa đơn TikTok. Tổng khoảng 24 đơn/ngày, tức khoảng 150 thao tác GUI mỗi ngày, cao hơn nhiều vào các đợt sale. Shopee chiếm hơn 80% số đơn.
- Ngày cao điểm 100 đơn tương đương khoảng 600 thao tác GUI. Nếu mỗi thao tác mất khoảng một phút thì một phiên cần khoảng 10 giờ, tức là sát giới hạn. Mục tiêu năng lực là 100 đơn/ngày mà không đơn nào quá hạn giao; con số thật được đo ở phase 6 và phase 8.
- Máy phát triển hiện tại đã có SAP GUI và PostgreSQL 16.
- Đơn chủ yếu 120.000đ một dòng, mỗi đơn một hóa đơn. Lazada giữ lại khoảng 29–30%, TikTok khoảng 18%, tiền về theo tuần.
- `docs/vk11pdf.pdf` ghi `ZPR1 = PriceList IncludeTax`, `ZDI3`–`ZDI8` là các loại discount, `ZMWS = Tax`.
- `docs/passwordapi.txt` là bí mật dạng văn bản thường, phải xử lý trước lần commit đầu tiên.

## Phases

| # | Phase | Ứng với V2 | Công | Phụ thuộc | Status |
|---|-------|-----------|------|-----------|--------|
| 1 | [Nền tảng dự án](./phase-01-start.md) | — | 2d | — | Pending |
| 2 | [Chốt nghiệp vụ và quyền truy cập](./phase-02-business-decisions-and-access.md) | GĐ 0 | 5d | — | Pending |
| 3 | [Mô hình dữ liệu và lõi đơn hàng](./phase-03-data-model-and-order-core.md) | GĐ 0 | 4d | 1 | Pending |
| 4 | [Connector ba sàn và đồng bộ đơn](./phase-04-marketplace-connectors-and-order-sync.md) | GĐ 1 | 8d | 2, 3 | Pending |
| 5 | [Xuất Excel, vận đơn, Web UI](./phase-05-excel-export-labels-and-web-ui.md) | GĐ 1 | 6d | 4 | Pending |
| 6 | [Hàng đợi SAP và khung robot](./phase-06-sap-job-queue-and-robot-framework.md) | GĐ 2 | 6d | 2, 3 | Pending |
| 7 | [Robot tạo SO: shadow rồi ghi thật](./phase-07-sales-order-robot-shadow-to-live.md) | GĐ 2 | 6d | 5, 6 | Pending |
| 8 | [DO, đóng gói, PGI](./phase-08-delivery-packing-and-goods-issue.md) | GĐ 2b | 6d | 7 | Pending |
| 9 | [Billing và hóa đơn BKAV](./phase-09-billing-and-bkav-invoice.md) | GĐ 3 | 5d | 8 | Pending |
| 10 | [Bảng kê đối soát](./phase-10-settlement-reconciliation-report.md) | GĐ 4 | 6d | 4, 9 | Pending |
| 11 | [Hàng hoàn, tồn kho, ghi nhận thanh toán](./phase-11-returns-stock-sync-and-payment-posting.md) | GĐ 5 | 8d | 8, 10 | Pending |
| 12 | [Vận hành, bảo mật, bàn giao](./phase-12-operations-security-and-handover.md) | Mục 10 | 4d | 1–11 | Pending |

Phase 2 chạy song song với phase 1 và 3 vì phần lớn thời gian là chờ người khác trả lời. Phase 6 chạy song song với phase 4 và 5. Cột Công là ước tính cho một lập trình viên; với Claude Code phần viết mã nhanh hơn, còn thời gian lịch do con người quyết định: chờ xác nhận, sàn duyệt app, ghi recorder, chạy thử trên QA và các đợt shadow (ước tính 4–5 tháng).

**Thứ tự mở sàn.** Đồng bộ đơn và shadow: Shopee trước vì chiếm hơn 80% số đơn. Ghi thật vào SAP: TikTok trước (ít đơn, sai thì ảnh hưởng nhỏ), rồi Shopee, rồi Lazada.

## Phân công: người và Claude Code

- **Claude Code làm:** viết mã, test, migration, tài liệu; chạy test trên máy phát triển; viết thao tác SAP từ bản ghi recorder.
- **Chủ dự án làm:** lấy quyết định của kế toán và sales admin, đăng ký app ba sàn, ghi recorder, chạy robot trên QA và xác nhận kết quả trong SAP, ký các cổng nghiệm thu, đổi chế độ `shadow`/`live`.
- **Nguyên tắc:** mỗi phiên Claude Code làm một phase (`/ak-cook` với file phase). Bí mật không dán vào hội thoại mà đặt vào kho bí mật. Dữ liệu người mua được ẩn danh bằng script chạy cục bộ trước khi vào repo. Claude Code không chạy lệnh ghi vào SAP thật; lệnh đó do chủ dự án chạy.

## Cổng chuyển giai đoạn

| Cổng | Điều kiện đo được |
|------|-------------------|
| G1 – Gom đơn chạy thật (sau phase 5) | 10 ngày làm việc liên tiếp, số đơn trong database khớp 100% với trang quản lý từng sàn; sales admin không còn xuất Excel tay; kho in vận đơn hàng loạt. |
| G2 – Ghi SO thật (trong phase 7) | Toàn bộ đơn mẫu tạo đúng trên QA. Mỗi sàn: ít nhất 30 đơn liên tiếp và tối thiểu 2 tuần shadow, đề xuất của robot khớp 100% với SO sales admin tạo tay; không có lỗi robot chưa giải thích. |
| G3 – Ghi DO/PGI thật (trong phase 8) | 30 đơn liên tiếp robot tạo SO thật không trùng, không lệch; đối chiếu hằng ngày sàn ↔ database ↔ SAP bằng 0. |
| G4 – Hóa đơn (phase 9) | File Excel robot sinh khớp từng ô với file kế toán tự làm cho 30 billing document liên tiếp. |
| G5 – Bảng kê (phase 10) | Bảng kê tự động khớp từng dòng với bảng kê tay tháng 10/2026 và hai kỳ kế tiếp. |
| G6 – Ghi nhận thanh toán tự động (phase 11) | Bảng kê khớp ba kỳ liên tiếp và kế toán trưởng ký duyệt quy tắc hạch toán. |

## Success Criteria

- [ ] Đơn hợp lệ của cả ba sàn có SO, DO, PGI, billing trong SAP mà không cần nhập tay.
- [ ] Không có mã đơn sàn nào ứng với hai SO.
- [ ] Đối chiếu hằng ngày sàn ↔ database ↔ SAP không lệch trong 30 ngày liên tiếp.
- [ ] Bảng kê đối soát tự động khớp bảng kê tay ba kỳ liên tiếp.
- [ ] Diễn tập dựng lại máy và khôi phục database từ bản sao lưu thành công.
- [ ] Người vận hành xử lý được mọi tình huống trong sổ tay mà không cần lập trình viên.

## Rủi ro chính

- **Mục [Xác nhận] chưa có câu trả lời** (13 mục, V2 mục 12). Phase 2 gom lại thành sổ quyết định; phase 7 trở đi không bắt đầu khi mục liên quan chưa chốt.
- **Robot ghi nhầm hệ thống.** Vì có cả QA lẫn hệ thống thật, mỗi việc SAP mang tên hệ thống đích và robot kiểm tra phiên đang mở đúng hệ thống đó trước khi làm (phase 6).
- **Một máy là điểm hỏng duy nhất.** Sao lưu hằng ngày ra ngoài máy từ phase 5; quy trình dựng lại máy được diễn tập ở phase 12; sổ tay ghi cách làm tay khi máy dừng.
- **Ngày cao điểm 100 đơn sát năng lực một phiên GUI.** Giảm số thao tác mỗi đơn (đệm kết quả đọc tồn kho theo mã vật tư), robot chạy cả ngoài giờ làm việc, đơn sắp quá hạn được ưu tiên. Nếu phép đo ở phase 8 cho thấy vẫn không đủ thì phần vượt được sales admin làm tay từ file Excel, và chủ dự án quyết định có xin thêm phiên SAP không.
- **Giao diện SAP hoặc API sàn thay đổi.** ID màn hình và popup nằm trong cấu hình; mỗi connector có bộ dữ liệu mẫu đã ghi lại để phát hiện thay đổi.
- **Chưa có bảng kê Shopee.** Phase 2 lấy bảng kê Shopee; đây là sàn lớn nhất nên là chuẩn so sánh quan trọng nhất của phase 10.

<!-- slug: ecommerce-sap-automation -->
