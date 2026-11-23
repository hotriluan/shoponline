---
title: "Phase 4: Gói D — zrsd003 còn lại"
status: completed
priority: P2
effort: 0.5d
dependencies: [1]
---

# Phase 4: Gói D — zrsd003 còn lại

## Overview

Hai lỗi zrsd003 mức High và Medium đã sửa (hóa đơn trùng DO giữ hóa đơn mới nhất; file cũ không ghi đè hóa đơn mới). Gói này làm nốt phần còn lại: một dòng lỗi của khách khác làm hỏng cả file, và khoảng đọc không có trần.

Bằng chứng: [báo cáo hóa đơn](../reports/data-integrity-audit-261123-1320-tax-invoice.md), mục 3, 5, 7.

## Phát hiện trong gói

| Mã | Mức | Vấn đề | Mã nguồn | Sửa đề xuất |
|---|---|---|---|---|
| 3 | Medium | Một dòng lỗi của khách ngoài ba sàn từ chối cả file, nên hóa đơn của sàn không vào | `importers/sap_reports.py:165-166,178-179`, `reconcile/report_ingest.py:81` | Lọc theo Bill-to của ba sàn **trước** khi kiểm lỗi từng dòng: `read_zrsd003` nhận tập khách sàn (tham số tùy chọn); dòng lỗi của khách khác bị bỏ, không từ chối file |
| 7 | Medium | Chọn một tháng cũ làm khoảng đọc rất dài, không có trần; robot hết giờ chờ thì việc FAILED | `web/routes/sales_history.py:105-112` | Cảnh báo khi khoảng dài hơn 62 ngày và cắt thành các việc đọc theo tháng (mỗi việc ≤ 31 ngày) |
| 5 | Low | Đơn không bao giờ có hóa đơn kéo khoảng đọc lùi mãi và nằm vĩnh viễn ở "Đơn bị chặn" | `web/routes/sales_history.py:105-112` | Giới hạn bởi trần của mục 7; ghi sổ tay cách xử lý đơn không có hóa đơn |
| 4 | Medium | SO nhiều DO: DO thứ hai không kiểm hóa đơn | `reconcile/so_link.py:306,314` | **Ngoài phạm vi** (xem plan.md); chờ kiểm production |

## Files

- Sửa: `src/shoponline/importers/sap_reports.py`, `src/shoponline/reconcile/report_ingest.py`, `src/shoponline/web/routes/sales_history.py`, và nơi gọi `read_zrsd003` (web upload và robot)
- Test: `tests/importers/test_zrsd003.py`, `tests/web/test_sales_history_routes.py`, `tests/saprobot/test_report_reads.py`
- Tài liệu: `docs/robot-runbook.md` (cách đọc theo tháng, trần khoảng)

## Implementation Steps

1. Test tái hiện cho 3 (file có một dòng lỗi của khách ngoài ba sàn cùng dòng hợp lệ của sàn: hiện bị từ chối) và 7 (khoảng nhiều tháng tạo một việc đọc dài).
2. Sửa 3: thêm tham số lọc vào `read_zrsd003`; các nơi gọi truyền tập khách sàn; giữ hành vi cũ khi không truyền (tương thích).
3. Sửa 7: chia khoảng và cảnh báo; kiểm chiều chia không phá khóa chống trùng việc (`dedupe_key`).
4. Test từng bộ một; `ruff` sạch; bảng theo dõi; commit.

## Todo

- [x] Test tái hiện 3, 7
- [x] Sửa 3 (lọc Bill-to trước khi kiểm dòng)
- [x] Sửa 7 (cảnh báo và chia theo tháng)
- [x] Ghi 5 là theo dõi, 4 là ngoài phạm vi
- [x] Test, `ruff`, bảng theo dõi, commit

## Success Criteria

- File zrsd003 có dòng lỗi của khách ngoài ba sàn vẫn nhập được hóa đơn của sàn.
- Khoảng đọc dài hơn 62 ngày hiện cảnh báo và tách thành các việc nhỏ.
- Bộ test zrsd003 và đọc theo tháng pass.

## Risk

- **Đổi chữ ký `read_zrsd003`:** tham số mới tùy chọn, mặc định giữ hành vi cũ; kiểm mọi nơi gọi.
- **Chia việc đọc theo tháng:** kiểm `dedupe_key` để không tạo việc trùng hoặc đọc sót ngày biên.

## Rollback

Revert commit; không có thay đổi schema.
