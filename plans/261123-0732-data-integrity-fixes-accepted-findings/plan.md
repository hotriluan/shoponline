---
title: "Sửa các phát hiện Medium và Low của đợt rà soát toàn vẹn dữ liệu"
description: "Sáu gói sửa, làm lần lượt từng gói: dọn file an toàn, file lịch sử, nhập đơn im lặng, zrsd003 còn lại, robot và đọc lại, tài liệu và trạng thái plan."
status: completed
priority: P1
effort: 5d
branch: main
tags: [fix, data-integrity, audit]
blockedBy: []
blocks: []
created: 2026-11-23
---

# Sửa các phát hiện Medium và Low của đợt rà soát toàn vẹn dữ liệu

## Overview

Đợt rà soát [261123-0556](../261123-0556-red-team-validate-data-integrity-audit/plan.md) đã duyệt (Accept) khoảng 44 phát hiện. Hai lỗi High đã được sửa riêng bằng `/ak-fix` (hóa đơn trùng DO giữ hóa đơn mới nhất và không bị file cũ ghi đè; cảnh báo đơn đã hủy còn SO) và đang chờ commit, nên **không làm lại** ở đây. Plan này xử lý phần Medium và Low còn lại, gom theo vùng mã.

Nguồn bằng chứng (có `file:dòng`): [báo cáo tổng hợp](../reports/data-integrity-audit-261123-1410-final.md) và các báo cáo theo vùng `data-integrity-audit-261123-1320-{deletion-machine,history-file,orders-sap,tax-invoice,robot-on-demand}.md` trong `plans/reports/`, cộng bảng `## Red Team Review` trong plan.md của từng plan gốc.

## Hợp đồng

- **Kết quả:** mỗi phát hiện đã duyệt có trạng thái cuối trong bảng theo dõi: `đã sửa`, `chấp nhận rủi ro` (ghi vào tài liệu) hoặc `loại vì không tái hiện`.
- **Ràng buộc:**
  - Mỗi phát hiện bắt đầu bằng một test tái hiện fail. Không tái hiện được thì loại kèm bằng chứng, không sửa.
  - Không ghi vào production. Giữ hợp đồng công khai (cột file, tên route, schema), trừ chỗ phase ghi rõ.
  - Commit theo kiểu conventional, không nhắc AI, mỗi gói một commit hoặc một chuỗi commit riêng.
  - Làm lần lượt từng gói và chạy test từng bộ một: DB test dùng chung, chạy song song gây `DeadlockDetected`.
- **Ngoài phạm vi:**
  - Đơn tách nhiều DO trên một SO (`do_number` một cột, chỉ DO đầu được lưu): cần kiểm trên production trước, làm plan riêng.
  - Chặn cứng DO của đơn đã hủy (hiện chỉ cảnh báo, chủ dự án chưa quyết).
  - Phần lớn mức Low không làm mất hay trùng dữ liệu: đóng bằng "chấp nhận rủi ro" trong tài liệu, trừ khi sửa mất dưới 30 phút.

## Bảng gói và thứ tự

| # | Gói | Phase | Mức cao nhất | Ghi chú |
|---|---|---|---|---|
| A | Dọn file an toàn | [phase 1](./phase-01-start.md) | Medium | **Phải xong trước khi chạy tác vụ xóa đêm với `--apply` trên production** |
| B | File lịch sử | [phase 2](./phase-02-package-b-history-file.md) | Medium | Chống file chồng đơn cần chọn thiết kế (có phương án) |
| C | Nhập đơn im lặng | [phase 3](./phase-03-package-c-silent-order-import-skips.md) | Medium | Cảnh báo, không đổi dữ liệu đơn đã có SO |
| D | zrsd003 còn lại | [phase 4](./phase-04-package-d-zrsd003-remaining.md) | Medium | Đổi chữ ký hàm đọc zrsd003 (nội bộ) |
| E | Robot và đọc lại | [phase 5](./phase-05-package-e-robot-and-reread.md) | Medium | Một quyết định sản phẩm: khoảng ngày của "Đọc lại zrsd001" |
| F | Tài liệu và trạng thái plan | [phase 6](./phase-06-package-f-docs-and-plan-state.md) | Low | Ghi nhận rủi ro đã chấp nhận, hoàn thiện bảng theo dõi |

Phụ thuộc: gói A đứng đầu vì chặn việc bật dọn file tự động. B đến E độc lập về mã nhưng **không chạy song song** (test dùng chung DB). F làm cuối để ghi trạng thái thật.

## Quy trình mỗi gói

1. Với mỗi phát hiện: viết test tái hiện, chạy, xác nhận fail. Không fail thì ghi `loại vì không tái hiện` kèm lý do.
2. Sửa tối thiểu cho tới khi test qua; chạy bộ test hẹp, rồi bộ rộng của vùng bị đụng (từng bộ một).
3. `uv run ruff check` và `ruff format --check` sạch.
4. Cập nhật cột "Trạng thái" trong [bảng theo dõi](../reports/data-integrity-audit-261123-1410-final.md) và tài liệu chỉ ở chỗ hành vi đổi.
5. Commit gói.

## Quyết định đã chốt (2026-11-23, chủ dự án chọn theo đề xuất)

1. **Phase 1, D3:** thêm file kế toán đã chốt vào sao lưu hằng ngày (phương án 1); cập nhật tài liệu sao lưu.
2. **Phase 2, H1:** khi xác nhận một file, xóa các file chưa xác nhận khác chứa đơn đó và cảnh báo lúc tải khi đã có file chưa xác nhận chứa cùng đơn (phương án 1); không đổi route.
3. **Phase 5:** "Đọc lại zrsd001" đọc từ ngày của lô đến hôm nay (`today_vn()`), mỗi lô vẫn một việc (phương án 1).

## Tiêu chí hoàn thành

1. Bảng theo dõi trong báo cáo tổng hợp có cột "Trạng thái", mọi phát hiện Accept đều có trạng thái cuối.
2. Phase 1 xong và được ghi nhận trước khi bật `--apply`.
3. Mỗi gói pass test, từng bộ một, và `ruff` sạch.
4. Tài liệu chỉ đổi ở chỗ hành vi đổi; mức Low không sửa được ghi thành rủi ro chấp nhận trong tài liệu vận hành.
5. Không có ghi nào vào production trong quá trình làm.

## Rủi ro chính

- **Một số phát hiện chưa từng tái hiện** (đọc từ mã). Giảm thiểu: test fail trước; loại nếu không tái hiện.
- **Gói A đụng tới xóa file và sao lưu**: sửa sai có thể làm xóa nhiều hơn. Giảm thiểu: mọi thay đổi thiên về giữ lại và dừng sớm; kiểm trên thư mục thử, không chạy `--apply` thật.
- **DB test dùng chung**: chạy từng bộ một, không nhờ agent chạy song song.
