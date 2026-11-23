---
title: "Phase 5: Gói E — robot và đọc lại"
status: completed
priority: P2
effort: 1d
dependencies: [1]
---

# Phase 5: Gói E — robot và đọc lại

## Overview

Sửa các điểm robot có thể chạy khi không còn khóa, đọc bằng user kém quyền mà không báo, hoặc tự dừng vì "No data" bình thường; và quyết định khoảng ngày của "Đọc lại zrsd001".

Bằng chứng: [báo cáo robot đọc khi cần](../reports/data-integrity-audit-261123-1320-robot-on-demand.md), [báo cáo dọn file và máy chạy thật](../reports/data-integrity-audit-261123-1320-deletion-machine.md) (D9, D10) và mục 11 của [báo cáo đơn hàng và SAP](../reports/data-integrity-audit-261123-1320-orders-sap.md).

## Phát hiện trong gói

| Mã | Mức | Vấn đề | Mã nguồn | Sửa đề xuất |
|---|---|---|---|---|
| D9 | Low | Khóa robot là khóa tư vấn gắn với một kết nối giữ mở và không kiểm tra lại; nếu kết nối rụng, robot vẫn chạy và robot thứ hai lấy được khóa | `saprobot/worker.py:484-495,504-526` | Kiểm lại khóa định kỳ trong vòng lặp (ví dụ mỗi lượt lấy việc); mất khóa thì dừng robot và ghi log |
| D10 | Low | Đổi user SAP không xóa trạng thái "đã kiểm tra kết nối", nên robot có thể đọc bằng user kém quyền và SAP trả ít dòng không báo lỗi | `sapjobs/sap_settings.py:225-227` | Xóa trạng thái đã kiểm tra khi `sap_user` đổi, như khi `system`/`client` đổi |
| robot-2 | Medium | "Đọc lại zrsd001" chỉ lọc đúng ngày của lô (`date_from = date_to = processing_date`); SO sales admin tạo ngày sau không bao giờ được đọc | `sapjobs/report_requests.py:18,28-29` | **Quyết định chủ dự án** (xem dưới) |
| 11 | Low | zrsd001 "No data" tính như lỗi robot và dồn vào bộ đếm lỗi liên tiếp: vài lô chưa có SO liên tiếp có thể tự dừng robot | `saprobot/worker.py:363-368,462`, `sapjobs/queue.py:287-299` | Coi "No data" của zrsd001 là kết quả trung tính (như zrsd004 và zrsd003), không tính vào bộ đếm |
| robot-3 | Low | Lệnh tay `zrsd004` đang chờ cho hệ thống khác bị đợt kế toán đóng, admin không được báo | `accounting/runs.py:290-297` | Chấp nhận rủi ro: bị thay đúng chủ ý, còn dấu vết trong nhật ký sự kiện |

### Quyết định robot-2 (chủ dự án chọn phương án 1, 2026-11-23)

- **Phương án 1 (đề xuất):** "Đọc lại zrsd001" đọc từ `processing_date` đến hôm nay (`today_vn()`), vẫn cho mỗi lô một việc (`dedupe_key` giữ nguyên). Cứu SO tạo ngày sau; đọc một khoảng ngắn nên chi phí nhỏ. Đổi một chút phạm vi đã loại trừ của plan `261113-1142`.
- **Phương án 2:** giữ một ngày, ghi sổ tay rằng SO tạo muộn phải tải tay. Không đổi mã.
- Phương án 1 phụ thuộc giả định SO muộn thường xuất hiện trong vài ngày; hết đúng nếu bán hàng tạo SO sau hàng tuần. Production cho thấy lô 1, 3 đã đọc ba lần, nên nhu cầu đọc lại có thật.

## Files

- Sửa: `src/shoponline/saprobot/worker.py`, `src/shoponline/sapjobs/sap_settings.py`, `src/shoponline/sapjobs/report_requests.py`, `src/shoponline/sapjobs/queue.py` (nếu cần cho mục 11)
- Test: `tests/saprobot/test_worker.py`, `tests/saprobot/test_report_reads.py`, `tests/web/test_robot_web.py`, `tests/sapjobs/test_queue.py`
- Tài liệu: `docs/robot-runbook.md` (đọc lại, "No data")

## Implementation Steps

1. Test tái hiện: D10 (đổi `sap_user` giữ nguyên trạng thái đã kiểm tra), mục 11 (vài việc zrsd001 "No data" liên tiếp làm robot tự dừng), D9 (khóa mất mà vòng lặp vẫn chạy; nếu không dựng được kết nối rụng trong test, dùng đối tượng giả cho kết nối khóa và ghi giới hạn).
2. Sửa D10, 11, D9.
3. Chốt phương án robot-2 với chủ dự án rồi làm.
4. Ghi robot-3 là rủi ro chấp nhận.
5. Test từng bộ một; `ruff` sạch; bảng theo dõi; commit.

## Todo

- [x] Test tái hiện D10, 11, D9
- [x] Sửa D10, 11, D9
- [x] Chốt robot-2 và làm
- [x] Ghi robot-3 là rủi ro chấp nhận
- [x] Test, `ruff`, bảng theo dõi, commit

## Success Criteria

- Đổi `sap_user` buộc kiểm tra lại kết nối trước khi robot đọc.
- Robot dừng khi mất khóa, không chạy tiếp.
- "No data" của zrsd001 không đẩy robot tới tự dừng.
- "Đọc lại zrsd001" theo đúng phương án đã chọn, có test.

## Risk

- **Không dựng được lỗi thật của kết nối rụng (D9):** test bằng đối tượng giả; ghi rõ giới hạn.
- **Mục 11 ẩn lỗi thật:** chỉ trung tính khi lô chưa có SO; các lỗi khác vẫn tính.
- **Cần SAP thật để kiểm D10 đầy đủ:** chỉ test phần logic trạng thái; không chạy robot thật.

## Rollback

Revert commit; không có thay đổi schema.
