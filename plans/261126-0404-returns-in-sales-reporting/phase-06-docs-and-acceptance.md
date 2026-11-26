---
phase: 6
title: "Tài liệu và nghiệm thu"
status: completed
priority: P2
effort: "0.5d"
dependencies: [3, 4, 5]
---

# Phase 6: Tài liệu và nghiệm thu

## Goal

Tài liệu nói đúng hành vi mới, phiếu cũ có dòng trừ, và kịch bản nghiệm thu chạy đạt trên dữ liệu dev.

## Files to Create / Modify

- Modify: `docs/daily-operations.md` (mục "Khách hủy hoặc trả đơn đã có hóa đơn", mục File Shop Online)
- Modify: `docs/operations-runbook.md` (mục "Đơn hủy sau khi đã có SO hoặc DO": bỏ câu "web không cho hủy", thêm luồng hủy khi DO đã hủy trước hóa đơn)
- Modify: `docs/system-architecture.md` (bảng mới, view báo cáo, quy tắc sổ cái)
- Modify: `docs/deployment-guide.md` (chạy migration, rồi `shoponline return-sale-lines backfill` một lần)
- Create: `plans/reports/acceptance-261126-returns-in-sales-reporting.md`

## Tasks & Steps

1. Cập nhật tài liệu. Ghi rõ cho kế toán:
   - dòng âm có `Quantity` và `Customer paid` âm, mang ngày đặt đơn gốc;
   - cột I của dòng trả là hằng số −1, 0 hoặc +1;
   - dòng đảo xuất hiện khi hủy phiếu sau khi đã dán;
   - SUM cả file là giá trị bán thật.
2. Ghi chú trên trang Báo cáo hoặc trong tài liệu: từ bản này, giá trị trên sàn và số đơn đã trừ hàng trả; tỷ lệ trả tính theo hóa đơn có thuế.
3. Chạy migration và backfill trên database dev (đã sao lưu); ghi số phiếu được bổ sung và số phiếu bị chặn.
4. Nghiệm thu với hai đơn mẫu (cả đơn trước khi dán, một phần sau khi dán), một lần hủy phiếu sau khi dán, một đơn có DO hủy chưa có hóa đơn. Đối chiếu SUM file với báo cáo theo tháng. Xóa dữ liệu nghiệm thu khỏi dev.
5. Báo người dùng gửi mô tả cách ghi mới cho kế toán trước lần dán đầu tiên.

## Verification

- `uv run pytest` và `uv run ruff check` đạt.
- Báo cáo nghiệm thu có bảng kết quả từng tiêu chí trong `plan.md`.
- Liên kết trong tài liệu trỏ đúng file và mục.
