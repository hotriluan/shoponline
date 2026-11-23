---
title: "Red team, validate các plan còn thiếu và rà soát trùng/sót dữ liệu"
description: "Chạy red team và validate cho 9 plan chưa qua hai cổng này (plan đã làm thì soi mã đối chiếu plan), rồi kiểm các bất biến toàn vẹn dữ liệu bằng truy vấn chỉ đọc trên production cho đơn hàng, DO, file kế toán, file lịch sử, hóa đơn, tiền vô."
status: completed
priority: P1
effort: 3d
branch: main
tags: [audit, red-team, validate, data-integrity]
blockedBy: []
blocks: []
created: 2026-11-23
---

# Red team, validate và rà soát trùng/sót dữ liệu

## Overview

Đã có 12 plan; 9 plan còn hiệu lực chưa qua red team hoặc validate, và 8 trong số đó đã được làm thành mã. Chủ dự án muốn biết các nghiệp vụ đã đề ra có thể làm **trùng** hoặc **sót** dữ liệu ở đâu: đơn hàng, báo cáo SAP, file gửi kế toán, file lịch sử Shop Online, hóa đơn, tiền vô.

Nguồn quyết định: [brainstorm](../reports/brainstorm-261123-1254-red-team-validate-data-integrity-audit.md) (2026-11-23, chủ dự án duyệt).

## Hợp đồng

- **Kết quả:** mỗi plan trong danh sách có `## Red Team Review` và `## Validation Log`; một báo cáo rà soát toàn vẹn dữ liệu xếp theo mức độ, mỗi phát hiện có bằng chứng (mã `file:dòng`, test tái hiện, hoặc số đếm từ truy vấn chỉ đọc trên production) và hướng sửa đề xuất.
- **Ràng buộc:** plan đã làm thì soi **mã đối chiếu plan**; plan chưa làm thì soi văn bản. Production chỉ đọc. Báo cáo không chứa PII. Không sửa mã nghiệp vụ.
- **Ngoài phạm vi:** sửa lỗi (mỗi lỗi thành plan hoặc `/ak-fix` riêng sau khi duyệt); plan đã hủy `261111-0431`; chạy lại red team/validate cho `261113-1230`, `261119-0719`, `261123-0312` (mã của chúng vẫn được rà theo luồng dữ liệu ở phase 7); UI, hiệu năng, bảo mật ngoài toàn vẹn dữ liệu.

## Quyết định đã chốt (2026-11-23, chủ dự án)

1. Plan đã làm: red team đọc mã và test thật, so với hợp đồng, quyết định và tiêu chí hoàn thành trong plan. Validate là kiểm từng tiêu chí hoàn thành so với mã, test và trạng thái thật; chỉ hỏi chủ dự án khi có điểm cần quyết.
2. Được truy vấn **chỉ đọc** trên DB production. Nếu không mở được kết nối chỉ đọc, dùng bản sao lưu mới nhất phục hồi vào database diễn tập (`SHOPONLINE_RESTORE_DATABASE_URL`).
3. Chỉ tìm và báo cáo. Test tái hiện được viết trong scratchpad hoặc nhánh tạm, không commit vào `main`.
4. `261113-1012-sap-connection-settings-web` và `261116-0944-win10-production-machine-hidden-tasks` chỉ red team nhẹ, tập trung vào mất hoặc trùng dữ liệu.

## Cách áp dụng red team và validate cho plan đã làm

Quy trình gốc ở skill `ak-plan` (`red-team-workflow.md`, `validate-workflow.md`) được giữ, với ba điểm khác:

- Reviewer nhận thêm danh sách file mã và test của plan. Mỗi phát hiện phải trích `file:dòng` **trong mã**; phát hiện không có trích dẫn thì bị bác.
- "Áp dụng phát hiện được chấp nhận" nghĩa là ghi vào `## Red Team Review` của plan đó, cột "Hướng xử lý", và chép sang file phát hiện của phase. Không sửa mã, không sửa phase file đã xong.
- Lens bắt buộc cho mọi reviewer: **trùng hoặc sót dữ liệu**. Với mỗi bảng hoặc file mà plan ghi ra: khóa chống trùng là gì, cái gì xảy ra khi chạy hai lần, chạy song song, hủy giữa chừng, nhập lại, hoặc khôi phục bản cũ.

## Luồng

```
Phase 1  chuẩn bị: truy cập chỉ đọc, sửa trạng thái lệch, đếm nền
   │
   ├─► Phase 2  261111-0755 (đơn hàng, SO/DO, báo cáo SAP, file kế toán gốc)
   ├─► Phase 3  261116-1354, 261119-0828 (file lịch sử, file nháp)
   ├─► Phase 4  261119-0605, 261119-0854 (hóa đơn zrsd003, đọc theo tháng)
   ├─► Phase 5  261116-1520 đầy đủ; 261113-1012, 261116-0944 nhẹ
   ├─► Phase 6  261113-1142 (chưa làm, soi văn bản)
   └─► Phase 7  bất biến xuyên luồng, chạy SQL trên production (gồm tiền vô, file kế toán gộp)
          │
          ▼
       Phase 8  báo cáo tổng hợp và danh sách đề xuất sửa
```

Phase 2–7 chạy song song được: mỗi phase chỉ ghi vào `plan.md` của plan mình phụ trách và vào một file phát hiện riêng. Phase 7 nhận giả thuyết từ phase 2–5 nếu chúng xong trước; nếu không, nó dùng giả thuyết trong brainstorm.

## Phases

| # | Phase | Status | Phụ thuộc |
|---|-------|--------|-----------|
| 1 | [Chuẩn bị truy cập, trạng thái và số đếm nền](./phase-01-start.md) | Completed | — |
| 2 | [Đơn hàng, SO/DO và báo cáo SAP (261111-0755)](./phase-02-order-core-and-sap-reports.md) | Completed | 1 |
| 3 | [File lịch sử và file nháp (261116-1354, 261119-0828)](./phase-03-history-file-plans.md) | Completed | 1 |
| 4 | [Hóa đơn zrsd003 (261119-0605, 261119-0854)](./phase-04-tax-invoice-plans.md) | Completed | 1 |
| 5 | [Dọn file và máy chạy thật (261116-1520, 261113-1012, 261116-0944)](./phase-05-file-deletion-and-machine-plans.md) | Completed | 1 |
| 6 | [Plan chưa làm: robot đọc khi cần (261113-1142)](./phase-06-pending-plan-robot-on-demand.md) | Completed | — |
| 7 | [Bất biến xuyên luồng trên production](./phase-07-cross-flow-invariants-on-production.md) | Completed | 1 |
| 8 | [Báo cáo tổng hợp](./phase-08-final-report.md) | Completed | 2–7 |

## Tiêu chí hoàn thành

1. Chín plan có `## Red Team Review` và `## Validation Log` trong `plan.md` (riêng `261116-1354` chỉ thêm red team, vì đã có validation log). Hai plan nhẹ ghi rõ "red team nhẹ: chỉ mất/trùng dữ liệu".
2. `plans/261113-1230-merged-accounting-file/plan.md` có trạng thái khớp với mã đã commit (`1db7fdb`) và trạng thái chạy thử production.
3. Mỗi luồng trong 7 luồng (đơn hàng; SO/DO và báo cáo SAP; file kế toán; file lịch sử; hóa đơn; tiền vô; xóa/khôi phục) có danh sách bất biến. Mỗi bất biến có câu SQL chỉ đọc và số đếm đã chạy trên production (hoặc trên bản phục hồi, có ghi ngày của bản).
4. Báo cáo `plans/reports/data-integrity-audit-261123-<HHmm>-final.md` có bảng phát hiện xếp Critical → Low. Mỗi dòng có bằng chứng, luồng, plan gốc, và đề xuất (`/ak-fix`, plan mới, hoặc chấp nhận rủi ro).
5. `git diff main -- src/ migrations/ tests/` rỗng khi kết thúc plan: không có thay đổi mã.
6. Báo cáo và file phát hiện không có tên khách, số điện thoại, địa chỉ. Kiểm bằng cách grep số điện thoại (`0\d{9}`) và tên cột PII.

## Rủi ro chính

- **Không mở được kết nối chỉ đọc tới máy chạy thật** (mạng LAN, mật khẩu ở máy kia). Dự phòng: phục hồi bản sao lưu mới nhất vào database diễn tập trên máy dev rồi truy vấn ở đó; báo cáo ghi rõ số liệu tính tới thời điểm của bản.
- **Truy vấn vô tình ghi:** mọi phiên đặt `SET default_transaction_read_only = on` trước câu đầu tiên; không dùng `psql -f` với file chưa đọc lại.
- **Số câu hỏi validate quá nhiều** (9 plan × 3–8 câu). Chỉ hỏi khi có tiêu chí FAILED hoặc quyết định chưa chốt; gom tối đa 4 câu mỗi lượt, mỗi plan tối đa 8 câu.
- **Plan lệch mã:** khi plan và mã khác nhau, lấy journal trong `plans/journals/` và `docs/` làm chuẩn bổ sung, và ghi lệch đó thành phát hiện.

## Kết quả thực hiện (2026-11-23)

Hoàn thành với một lệch có chủ ý: số đếm và bất biến (phase 1 và 7) chạy trên **DB dev**, không phải production hay bản phục hồi, vì chủ dự án chọn dùng DB dev khi không mở được kết nối tới production. Tiêu chí 3 vì vậy mới đạt cho dev; cần chạy lại `invariants.sql` trên production. Báo cáo tổng hợp: [final](../reports/data-integrity-audit-261123-1410-final.md).
