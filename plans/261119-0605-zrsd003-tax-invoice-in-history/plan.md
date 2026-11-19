---
title: "Thêm Tax Invoice Doc. từ zrsd003 vào file Shop Online 2022-2026"
description: "Robot và upload tay đọc zrsd003, lưu số hóa đơn theo DO của sàn; file lịch sử Shop Online có cột 19 Tax Invoice Doc. và chặn đơn chưa có hóa đơn."
status: in-progress
priority: P2
effort: 2d
branch: main
tags: [feature, backend, database, web, robot]
blockedBy: []
blocks: []
created: 2026-11-19
---

# Thêm Tax Invoice Doc. từ zrsd003 vào file Shop Online 2022-2026

## Overview

Kế toán cần số hóa đơn (Tax Invoice Doc.) cho mỗi dòng trong file lịch sử Shop Online. SAP báo cáo hóa đơn ở ZRSD003; mỗi DO có đúng một hóa đơn (`OD Doc.` = `Delivery` của zrsd004 = `sales_order.do_number`). Kế hoạch thêm bảng lưu hóa đơn của các sàn, bộ nhập zrsd003 dùng chung cho upload tay và robot, job robot đọc ZRSD003, rồi thêm lý do chặn và cột 19 vào file lịch sử.

Nguồn quyết định: [brainstorm-261119-1208-zrsd003-tax-invoice-in-history.md](../reports/brainstorm-261119-1208-zrsd003-tax-invoice-in-history.md). Bản ghi SAP: `docs/sap-recordings/zrsd003/` (gitignore).

## Hợp đồng

- **Kết quả:** admin bấm "Robot đọc zrsd003" (hoặc tải file zrsd003 lên); trang File Shop Online xuất file có cột 19 `Tax Invoice Doc.` sau `Mã đơn`; đơn đã có DO mà chưa có hóa đơn nằm ở **Đơn bị chặn**.
- **Ràng buộc:** job robot chỉ đọc (`writes=False`), tcode `ZRSD003` thêm vào allowlist của guard; một migration `0008_sap_tax_invoice`, sao lưu DB trước khi chạy trên production; chỉ lưu dòng có Bill-to là khách SAP của sàn; file zrsd003 gốc bị xóa ngay sau khi nhập.
- **Ngoài phạm vi:** cột hóa đơn trong file kế toán zrsd004; sửa lại file lịch sử đã xác nhận; hóa đơn khác `ZBA1` (hủy, điều chỉnh); SO tách nhiều DO.

## Quyết định đã chốt (2026-11-19, chủ dự án)

1. Robot đọc ZRSD003 **và** có ô upload tay dự phòng ở trang Báo cáo SAP.
2. Đơn có DO mà chưa có hóa đơn: chặn đơn. Hóa đơn luôn xuất sau DO nên đây là trạng thái chờ bình thường.
3. Cột 19, sau `Mã đơn`; 17 cột gốc và cột 18 giữ nguyên.
4. ZRSD003 không lọc được Bill-to: đọc cả Sales Org 1000, Sales Office 1401 theo Billing Date; bộ nhập lọc Bill-to. Một job cho mọi sàn, khóa theo khoảng ngày.

## Luồng

```
DO có (zrsd004) ──► (sau đó) SAP xuất hóa đơn
        ▼
Trang File Shop Online: đơn chờ hóa đơn bị chặn ──► nút "Robot đọc zrsd003"
        ▼                                            (từ ngày đặt sớm nhất đang chờ → hôm nay)
Robot: ZRSD003, 1000/1401, Billing Date ──► Excel ──► ingest_zrsd003
        ▲                                                ▼
Upload tay ở Báo cáo SAP ───────────────────────► lọc Bill-to sàn, upsert sap_tax_invoice, xóa file gốc
        ▼
collect_rows tra theo do_number ──► đủ thì xuất, cột 19 = Tax Invoice Doc.
```

## Phases

| # | Phase | Trạng thái | Phụ thuộc |
|---|---|---|---|
| 1 | [Bảng hóa đơn và bộ nhập zrsd003](phase-01-tax-invoice-store.md) | completed | — |
| 2 | [Ô upload tay zrsd003](phase-02-manual-upload.md) | completed | 1 |
| 3 | [Job robot đọc ZRSD003](phase-03-robot-read-zrsd003.md) | completed | 1 |
| 4 | [Chặn đơn chờ hóa đơn, cột 19, nút đọc](phase-04-history-file-column.md) | completed | 1, 3 |
| 5 | [Tài liệu và chạy thử production](phase-05-docs-and-live-check.md) | in-progress (tài liệu xong; chờ deploy và chạy thử production) | 2, 3, 4 |

Phase 2 và 3 sửa file khác nhau, làm song song được sau phase 1. Phase 4 dùng hàm xếp job của phase 3.

## Tiêu chí hoàn thành

1. Nhập `docs/zrsd003.XLSX`: giữ 243 dòng có Bill-to `1200001145` (Shopee, 179), `1200001146` (TikTok, 39), `1200001118` (Lazada, 25), bỏ qua 407 dòng khách khác; nhập lại cùng file không đổi số dòng; DO `1910061168` → `7914`.
2. File thiếu `OD Doc.`, `Tax Invoice Doc.`, `Bill-to` hoặc `Billing Date` bị từ chối, không ghi gì.
3. Upload tay và robot cho cùng kết quả (cùng hàm `ingest_zrsd003`); file gốc không còn trong `uploads/` sau khi nhập.
4. Robot điền đúng `P_VKORG`, `P_VKBUR-LOW`, `P_FKDAT-LOW`, `P_FKDAT-HIGH`, xuất từ cột `TAXSR`; test với fake SAP qua.
5. Trang File Shop Online: đơn `DELIVERED` chưa có hóa đơn bị chặn với lý do "DO … chưa có Tax Invoice Doc."; có nút xếp job zrsd003 với khoảng ngày đúng; viewer không xếp được job.
6. File tải về có 19 cột, cột 19 header `Tax Invoice Doc.`, giá trị dạng text đúng theo DO.
7. `uv run pytest` và `uv run ruff check` thoát mã 0.

## Rủi ro chính

- **Enter sau Sales Org/Sales Office:** bản ghi gửi Enter sau hai ô này (màn hình nạp lại). Robot phải làm theo; phase 3 kiểm helper hiện có và test fake SAP.
- **Câu "không có dữ liệu" của ZRSD003 chưa được chụp.** Nếu khác "no data to display", job FAILED chứ không nhập sai; phase 5 ghi lại nếu gặp.
- **Variant mặc định đổi** (Exist/SD): robot không chạm radio; tài liệu robot ghi rõ điều kiện này.
- **SO tách nhiều DO:** chỉ DO đầu được tra; chưa thấy trên production.
