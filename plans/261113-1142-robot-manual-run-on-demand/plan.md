---
title: "Ra lệnh cho robot đọc báo cáo SAP khi cần"
description: "Admin bảo robot đọc zrsd001 của một lô đã xác nhận, hoặc zrsd004 của một sàn và một ngày GI, kể cả đọc lại lần đã xong; cách chạy tự động giữ nguyên."
status: in-progress
priority: P2
effort: 1d
branch: main
tags: [feature, web, robot]
blockedBy: []
blocks: []
created: 2026-11-13
---

# Ra lệnh cho robot đọc báo cáo SAP khi cần

## Overview

> **Cập nhật 2026-11-23** (sửa chữ lệch mã, không đổi hợp đồng gốc): (1) "ngày không có dữ liệu thành Lỗi và tính vào bộ đếm lỗi liên tiếp" không còn đúng với bất kỳ báo cáo nào: zrsd001, zrsd003 và zrsd004 đều kết thúc `Xong` và trung tính khi SAP không có dữ liệu. (2) "Hôm nay" lấy từ `today_vn()`, không phải `date.today()`. (3) Form còn có `zrsd003` (khoảng ngày lập hóa đơn), thêm bởi plan [261119-0854](../261119-0854-month-pick-zrsd003-read/plan.md). (4) "Đọc lại zrsd001" nay đọc từ ngày của lô đến hôm nay, không còn đúng một ngày.

Hiện việc cho robot chỉ được tạo khi admin bấm nút trong quy trình của lô. Việc đọc `zrsd001` chỉ được tạo một lần, lúc xác nhận lô ([batches.py:153](../../src/shoponline/web/routes/batches.py)). Nút "Chạy lại" chỉ nhận việc Lỗi, Chưa rõ hoặc Cần kiểm tra ([queue.py:177](../../src/shoponline/sapjobs/queue.py)). Vì vậy, nếu lần đọc đầu thiếu dữ liệu, không có cách nào bảo robot đọc lại.

Kế hoạch này thêm hai lối ra lệnh:

- form "Ra lệnh cho robot" trên trang **Robot SAP**;
- nút "Đọc lại zrsd001" trên trang lô đã xác nhận.

Cả hai đi qua hàm xếp việc, hàng đợi và cơ chế chống trùng việc có sẵn. Robot, lớp chặn T-code và database không đổi.

Bản chốt và các phương án đã so sánh: [brainstorm-261113-1142-robot-manual-run-on-demand.md](../reports/brainstorm-261113-1142-robot-manual-run-on-demand.md).

## Hợp đồng

- **Kết quả:** admin chủ động bảo robot đọc báo cáo khi cần, kể cả đọc lại một lần đã xong. Có hai loại lệnh:
  - đọc `zrsd001` cho một lô đã xác nhận;
  - đọc `zrsd004` cho một sàn và một ngày GI.

  Các nút tự động hiện có giữ nguyên hành vi.
- **Ràng buộc:**
  - Robot vẫn chỉ đọc SAP; `guard.py` không đổi.
  - Lệnh mới dùng chung `request_zrsd001` và `request_zrsd004`, chung khóa chống trùng việc.
  - Vẫn chặn khi kết nối chưa được kiểm tra. Khi robot tạm dừng, việc vẫn được xếp và nằm chờ.
  - Chỉ vai trò admin được ra lệnh.
  - Không cần migration.
- **Ngoài phạm vi:** công tắc tự động/thủ công, đặt lịch chạy, bật/tắt tiến trình robot từ web, ghi vào SAP, đọc `zrsd001` tự do theo sàn và ngày.

## Quyết định đã chốt (2026-11-13, chủ dự án)

1. Chọn phương án A: thêm lối ra lệnh, giữ cách chạy tự động.
2. Lệnh `zrsd004` chọn theo sàn và ngày GI, không theo lô.

## Mặc định do kiến trúc sư chọn (đổi được khi duyệt)

- **Ngày GI sau hôm nay bị từ chối ngay trên web.** SAP sẽ trả "No data to display"; với `zrsd004` việc kết thúc `Xong` là "SAP chưa có DO" và không tính vào bộ đếm lỗi liên tiếp, với `zrsd001` việc chuyển Lỗi ([robot-runbook.md](../../docs/robot-runbook.md#robot-tự-dừng)).
- **Danh sách lô trong form chỉ gồm 60 lô đã xác nhận gần nhất**, xếp theo ngày xử lý giảm dần. Lô cũ hơn vẫn đọc lại được từ trang của lô.
- **Nhật ký sự kiện dùng sự kiện `sap_job_enqueued` có sẵn**, đã ghi người ra lệnh ([queue.py:110](../../src/shoponline/sapjobs/queue.py)). Không thêm loại sự kiện mới.

## Luồng

```
Trang Robot SAP ── form "Ra lệnh cho robot" ──┐
Trang lô ── nút "Đọc lại zrsd001" ────────────┤
Nút tự động hiện có ──────────────────────────┤
                                              ▼
            kiểm tra: admin, hệ thống đích đã đặt, kết nối đã được kiểm tra
                                              ▼
              request_zrsd001(lô) / request_zrsd004(sàn, ngày GI)
                                              ▼
                 queue.enqueue (khóa chống trùng, ghi nhật ký sự kiện)
                                              ▼
                      robot nhận và chạy như việc thường
```

## Phases

| # | Phase | Trạng thái | Phụ thuộc |
|---|---|---|---|
| 1 | [Lệnh đọc báo cáo trên web](phase-01-web-on-demand-reads.md) | pending | — |
| 2 | [Tài liệu và chạy thử trên Production](phase-02-docs-and-live-check.md) | pending | 1 |

## Tiêu chí hoàn thành

1. Admin tạo được việc `read_zrsd001` cho một lô đã xác nhận, cả từ trang Robot SAP lẫn từ trang lô, kể cả khi việc trước của lô đã Xong.
2. Admin tạo được việc `read_zrsd004` cho một sàn và một ngày GI không quá hôm nay, kể cả ngày không có lô. Dữ liệu việc giống hệt việc do nút "Xuất file gửi kế toán" tạo cho cùng sàn và ngày.
3. Có việc cùng khóa đang mở thì lệnh bị từ chối, và trang báo số việc đang mở.
4. Từ chối khi lô chưa xác nhận, lô không tồn tại, sàn không tồn tại hoặc ngày GI sau hôm nay.
5. Kết nối chưa được kiểm tra thì bị từ chối, cùng thông báo với nút tự động. Robot chưa bật (chưa đặt hệ thống đích) thì form không hiện.
6. Tài khoản viewer nhận 403 ở cả hai route và không thấy form hay nút.
7. Đọc lại `zrsd001` hai lần cho cùng lô không tạo SO hay liên kết trùng (test qua `Worker`).
8. `uv run pytest` và `uv run ruff check` thoát mã 0.
9. `docs/robot-runbook.md` có mục ra lệnh; chạy thử một lệnh `zrsd004` trên `AEP`/300 thành công.

## Rủi ro chính

- **Đọc ngày không có dữ liệu.** Từ khi có [gộp 3 sàn thành một file gửi kế toán](../261113-1230-merged-accounting-file/plan.md), việc `read_zrsd004` gặp "No data" kết thúc `Xong` với kết quả "SAP chưa có DO" và không đổi bộ đếm lỗi liên tiếp. Việc `read_zrsd001` không có dữ liệu vẫn là lỗi.
- **Đổi chữ ký `request_zrsd004`.** Có hai nơi gọi: [batches.py:196](../../src/shoponline/web/routes/batches.py) và [test_worker.py:120](../../tests/saprobot/test_worker.py). `ruff` và `pytest` sẽ bắt chỗ sót.

## Red Team Review

### Session — 2026-11-23 (rà soát đối chiếu mã, plan đã được làm)

**Phương pháp:** ba lens (bảo mật, giả định, trùng/sót dữ liệu) do một người thực hiện trên mã hiện có; không có reviewer riêng. Chi tiết: [báo cáo](../reports/data-integrity-audit-261123-1320-robot-on-demand.md). Số liệu lấy từ dev DB, 2026-11-23.
**Findings:** 7 accepted (đề xuất), 5 bác có nguồn kiểm chứng. **Severity:** 2 Medium, 5 Low.

| # | Finding | Severity | Disposition | Applied To |
|---|---|---|---|---|
| 1 | Trạng thái `pending` sai: mã `5a4ac9c` và tài liệu `0ed5301` đã xong; chỉ thiếu biên bản chạy thử production | Medium | Accept (chủ dự án duyệt 2026-11-23) | plan.md frontmatter |
| 2 | Đọc lại `zrsd001` vẫn lọc một ngày (`report_requests.py:18,28-29`): SO tạo vào ngày sau không bao giờ được đọc, kể cả khi bấm đọc lại | Medium | Accept (chủ dự án duyệt 2026-11-23) | Rủi ro chính; runbook |
| 3 | Lệnh tay `zrsd004` đang chờ bị đợt gửi kế toán đóng thầm khi khác hệ thống đích (`accounting/runs.py:290-297`) | Low | Accept (chủ dự án duyệt 2026-11-23) | Ghi chú runbook |
| 4 | Đọc lại `zrsd004` chỉ ghi DO đầu của SO đang `SO_LINKED` (`so_link.py:303-313`), không bắt DO thứ hai | Low | Accept (chủ dự án duyệt 2026-11-23) | Chuyển plan `261113-1230`, phase 7 |
| 5 | Phase 2 viết sai: ngày không có dữ liệu "thành Lỗi" chỉ đúng với `zrsd001`; `zrsd004`, `zrsd003` kết thúc Xong và trung tính (`worker.py:436-444`) | Low | Accept (chủ dự án duyệt 2026-11-23) | Phase 2 |
| 6 | Plan dùng `date.today()`, mã dùng `today_vn()` (`robot.py:147,168`) | Low | Accept (chủ dự án duyệt 2026-11-23) | Phase 1 |
| 7 | Phạm vi thiếu `zrsd003`, form thực tế đã có (`robot.py:128`) | Low | Accept (chủ dự án duyệt 2026-11-23) | Overview |
| 8 | Hai admin bấm cùng lúc tạo việc trùng | n/a | Reject: chỉ mục duy nhất từng phần `0004_sap_job.py:47-53` và `queue.py:98-101` | — |
| 9 | Đọc lại `zrsd001` tạo SO hoặc liên kết trùng | n/a | Reject: `test_worker.py:128` | — |
| 10 | Đọc lại `zrsd004` làm lùi trạng thái hoặc gửi kế toán trùng | n/a | Reject: `so_link.py:309-312`, sổ `models.py:381` | — |
| 11 | Tiêm dữ liệu qua form | n/a | Reject: danh sách cho phép `robot.py:130`, kiểm kiểu, khóa ngoại `models.py:96` | — |
| 12 | Viewer ra lệnh được | n/a | Reject: `require_admin` ở `robot.py:120`, `batches.py:219`, có test | — |

Quyết định thuộc chủ dự án: đóng plan hay giữ `in-progress` tới khi có biên bản chạy thử; chấp nhận hay xử lý rủi ro 2. Không sửa mã hay phase file trong đợt này.

## Validation Log

### Session 1 — 2026-11-23 (đối chiếu mã, không hỏi trực tiếp)

| # | Tiêu chí hoàn thành | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | Admin tạo `read_zrsd001` từ trang Robot SAP và trang lô, kể cả khi việc trước đã Xong | VERIFIED | `robot.py:134-141`, `batches.py:214-239`; `test_robot_web.py:137-150` |
| 2 | `read_zrsd004` theo sàn và ngày GI không quá hôm nay, dữ liệu giống nút của đợt | VERIFIED | `report_requests.py:38-60`; `test_robot_web.py:158-183` |
| 3 | Việc cùng khóa đang mở bị từ chối, trang báo số việc | VERIFIED | `queue.py:85-90`; `test_robot_web.py:141-143` |
| 4 | Từ chối lô chưa xác nhận, lô hoặc sàn không có, ngày sau hôm nay | VERIFIED | `robot.py:136-148`; `test_robot_web.py:152-156,172-183,206` |
| 5 | Chưa kiểm tra kết nối thì từ chối; chưa có hệ thống đích thì không hiện form | VERIFIED | `app.py:120-125`; `test_robot_web.py:220-231,251` |
| 6 | Viewer 403 và không thấy form | VERIFIED | `robot.py:120`; `test_robot_web.py:234-248` |
| 7 | Đọc lại `zrsd001` hai lần không tạo SO hay liên kết trùng | VERIFIED | `test_worker.py:128` |
| 8 | `pytest` và `ruff check` thoát 0 | VERIFIED một phần | hai file test liên quan 36 passed, ruff sạch (2026-11-23); chưa chạy toàn bộ bộ test |
| 9 | Runbook có mục ra lệnh; chạy thử một lệnh `zrsd004` trên `AEP`/300 | Runbook VERIFIED (`robot-runbook.md:32-39`); chạy thử UNVERIFIED | không có journal chạy thử; dev DB không chứng minh production |

Giả định kiểm thêm: "ngày không có dữ liệu thành Lỗi" (phase 2) FAILED với `zrsd004` và `zrsd003` (`worker.py:436-444`); "hôm nay bằng `date.today()`" lệch mã (mã dùng `today_vn()`).

**Câu hỏi cho chủ dự án**

1. Đóng plan này thành `completed` hay giữ `in-progress` tới khi có biên bản chạy thử production (tiêu chí 9)?
2. Đã chạy thử lệnh `zrsd004` và nút "Đọc lại zrsd001" trên production chưa? Nếu rồi, ghi journal ngày nào?
3. Có chấp nhận việc "Đọc lại zrsd001" chỉ đọc đúng ngày xử lý của lô (SO tạo ngày sau phải tải tay), hay cần plan mới đọc theo khoảng ngày?
