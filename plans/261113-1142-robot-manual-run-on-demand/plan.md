---
title: "Ra lệnh cho robot đọc báo cáo SAP khi cần"
description: "Admin bảo robot đọc zrsd001 của một lô đã xác nhận, hoặc zrsd004 của một sàn và một ngày GI, kể cả đọc lại lần đã xong; cách chạy tự động giữ nguyên."
status: pending
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
