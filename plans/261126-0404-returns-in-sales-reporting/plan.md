---
title: "Đơn hủy, trả hàng trong file Shop Online, báo cáo và các module"
description: "Mỗi phiếu trả hàng sinh dòng âm trong file Shop Online và trong báo cáo, để tổng cộng là giá trị bán thật; mọi module có liên quan hiện nhãn đơn đã hủy hoặc trả."
status: completed
priority: P1
effort: 4d
branch: main
tags: [feature, backend, database, frontend]
blockedBy: []
blocks: []
created: 2026-11-26
---

# Đơn hủy, trả hàng trong file Shop Online, báo cáo và các module

## Overview

Hiện nay lập phiếu trả hàng không ảnh hưởng gì ngoài phiếu. Đơn vẫn `DELIVERED`, file Shop Online vẫn ra dòng dương, báo cáo vẫn tính đủ. Plan này biến file Shop Online thành sổ cái chỉ ghi thêm: phiếu trả hàng sinh dòng âm (theo giá sàn, mang ngày đặt đơn gốc), hủy phiếu sinh dòng đảo. Báo cáo dùng cùng các dòng đó nên ra số ròng. Các module có liên quan hiện nhãn đơn đã hủy hoặc trả. Đơn có DO bị hủy trước khi xuất hóa đơn sẽ đánh dấu hủy được.

Thiết kế, bằng chứng và quyết định: [brainstorm report](../reports/brainstorm-261126-1057-returns-in-sales-reporting.md). Nền tảng: [plan phiếu trả hàng](../261123-0950-invoice-return-documents/plan.md).

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Dữ liệu: dòng trừ theo giá sàn](./phase-01-start.md) | Completed |
| 2 | [Nhãn đơn và hủy đơn chưa có hóa đơn](./phase-02-order-flags-and-cancel-without-invoice.md) | Completed |
| 3 | [File Shop Online: dòng âm và dòng đảo](./phase-03-shop-online-file-return-rows.md) | Completed |
| 4 | [View báo cáo trừ hàng trả](./phase-04-report-views-net-of-returns.md) | Completed |
| 5 | [Nhãn ở các module khác](./phase-05-markers-in-other-modules.md) | Completed |
| 6 | [Tài liệu và nghiệm thu](./phase-06-docs-and-acceptance.md) | Completed |

Thứ tự: 1 → 2 → 3 → 4 → 5 → 6. Phase 3 và 4 cùng đọc bảng của phase 1; phase 5 dùng hàm nhãn của phase 2.

## Quyết định đã chốt

- File Shop Online là sổ cái chỉ ghi thêm: phiếu sinh dòng âm, hủy phiếu sau khi dòng âm đã dán sinh dòng đảo. Không sửa dòng đã dán.
- Dòng âm tính theo giá sàn (`(unit_price − unit_subsidy) × số lượng trả`), cùng cơ sở với `Customer paid`, không theo tiền hóa đơn.
- Dòng âm và dòng đảo mang ngày đặt đơn gốc (`createTime`, `month`, `year`).
- Cột `Transaction` (I) ở dòng âm và dòng đảo ghi hằng số: −1 (hoặc +1 khi đảo) ở dòng đầu của phiếu trả cả đơn, 0 ở các dòng khác. Dòng bán thường giữ công thức.
- Dòng âm chỉ ra khi dòng gốc của đơn đã dán hoặc nằm cùng file, để file không bao giờ có dòng âm của một đơn chưa dán.
- Không thêm trạng thái đơn. Nhãn "Hủy sau HĐ", "Trả hàng", "Trả một phần" suy ra từ phiếu `ISSUED`.
- Cho phép `DELIVERED → CANCELLED` chỉ khi DO chưa có hóa đơn trong zrsd003, kèm lý do bắt buộc.
- Giá trị trả trong báo cáo có hai số: theo giá sàn (để trừ doanh số) và theo hóa đơn có thuế (để tính tỷ lệ trả).

## Ngoài phạm vi

Hóa đơn điều chỉnh trên Bkav, chứng từ SAP, dữ liệu lịch sử trước 11/11/2026, tự điều chỉnh `Tiền Vô` khi sàn hoàn tiền, sửa các đợt gửi kế toán đã chốt, đổi cách nạp file lịch sử vào báo cáo.

## Success Criteria

- [x] Đơn A trả cả đơn trước khi dán, đơn B trả một phần sau khi dán: SUM `Customer paid` và SUM `Transaction` của các dòng đã dán bằng giá trị bán thật và số đơn thật.
- [x] Hủy phiếu B sau khi dòng âm đã dán: lần xuất sau có dòng đảo, tổng quay lại như trước khi trả. Hủy phiếu khi dòng âm chưa dán: không sinh dòng.
- [x] Báo cáo Tổng quan, Theo sàn, Theo sản phẩm, Theo tỉnh từ 11/11/2026 khớp với tổng của file Shop Online theo tháng đặt đơn; đơn trả cả đơn không còn được đếm.
- [x] Tỷ lệ trả tính trên cùng cơ sở có thuế với doanh thu hóa đơn.
- [x] Nhãn hiện ở chi tiết đơn, danh sách đơn của lô, Tiền về Lazada, đợt gửi kế toán, file NHÁP và TẤT CẢ ĐƠN; mất khi phiếu bị hủy.
- [x] Đơn có DO, chưa có hóa đơn: đánh dấu hủy được và rời báo cáo; đã có hóa đơn: vẫn bị chặn.
- [x] Phiếu đã phát hành trước khi triển khai được bổ sung dòng trừ bằng lệnh một lần.
- [x] `uv run pytest` và `uv run ruff check` đạt.

## Rủi ro chính

- Quy đổi dòng SAP sang dòng sàn theo mã vật tư: đơn kit và đơn có hai dòng cùng mã khác giá. Không ghép được thì chặn phát hành, không đoán.
- Kế toán có thể có pivot giả định số lượng dương. Báo kế toán trước lần dán đầu tiên (phase 6).
- Mở `DELIVERED → CANCELLED` trong máy trạng thái: mọi chỗ gọi hủy phải qua hàm có kiểm tra hóa đơn.

## Validation Log

### Session 1 — 2026-11-26

Kiểm chứng trên mã:
- các file và template được nêu trong phase đều tồn tại;
- migration mới nhất là `0017`;
- `so_link.py:326` ghép dòng chính SAP với dòng sàn theo mã và số lượng;
- xác nhận dán dùng `sales_history_file_order` và `sales_history_exported`;
- `accounting_sent_delivery` có sẵn để cảnh báo DO đã gửi kế toán;
- lệnh CLI theo mẫu `return-number`;
- `ak plan validate` đạt.

Failed: 0.

| Câu hỏi | Trả lời | Ảnh hưởng |
|---|---|---|
| Lazada: đơn đã hủy hoặc trả cả đơn | Hiện nhãn, cảnh báo, vẫn cho lưu | Phase 5 bước 3 (đã có) |
| File TẤT CẢ ĐƠN có dòng âm | Có, kèm đánh dấu đã dán hay chưa | Phase 3 bước 8 (đã có) |

Quyết định từ brainstorm: dòng âm mang ngày đặt đơn gốc; cột I ghi −1, 0 hoặc +1; làm luôn phần hủy đơn có DO nhưng chưa có hóa đơn.

### Whole-Plan Consistency Sweep

- Đã đọc lại plan.md và phase 1 đến 6.
- Bảng mới chỉ được tạo ở phase 1 (migration 0018); view chỉ được đổi ở phase 4 (migration 0019); nhãn dùng chung `returns.flags` (phase 2), được phase 3 và 5 dùng lại.
- Mâu thuẫn chưa giải quyết: 0.

Câu hỏi mở: không còn.
