---
phase: 6
title: "Kiểm tra trực quan và tài liệu"
status: completed
priority: P1
effort: "4h"
dependencies: [2, 3, 4, 5]
---

# Phase 6: Kiểm tra trực quan và tài liệu

## Goal

Chứng minh cả 24 trang đạt tiêu chí trên hai cỡ màn hình, gỡ các alias CSS thừa, và cập nhật tài liệu vận hành.

## Files

- Modify: `src/shoponline/web/static/app.css` (gỡ alias không còn dùng)
- Modify: `docs/daily-operations.md` (trang Việc hôm nay; câu "Sao lưu (mục trên cùng của menu)" ở mục Khi có sự cố thành "nhóm Hệ thống trên menu bên trái")
- Report: `plans/261123-0819-ui-ux-overhaul/reports/visual-check.md`

## Steps

1. Chạy web dev trên một cổng cố định với database dev có dữ liệu thật đã nhập. Trước khi chạy, kiểm tra cổng đó đã có tiến trình chiếm chưa; sau khi xong thì dừng đúng tiến trình mình đã bật.
2. Dùng `ak-agent-browser` chụp từng trang ở 1366×768 và 390×844, với cả admin và viewer. Kiểm tra: không cuộn ngang ở cấp trang, focus nhìn thấy được khi dùng Tab, sidebar dạng ngăn kéo mở và đóng được trên màn hẹp, không có chữ tràn.
3. Rà theo `ak-ui-ux-pro-max` `references/quick-reference-rules.md` §1, §5, §6, §8, §9 và ghi kết quả vào report.
4. Gỡ alias CSS không còn template nào dùng (grep từng class).
5. Cập nhật tài liệu; kiểm tra lại link và chữ trên giao diện khớp với tài liệu.
6. Chạy `uv run pytest -q` toàn bộ và lint dự án đang dùng (`uv run ruff check` nếu có trong `pyproject.toml`).

## Verification

- Đạt toàn bộ Success Criteria trong [plan.md](./plan.md).
- Report có ảnh chụp hoặc danh sách trang kèm kết quả đạt hoặc lỗi.

## Risks

- Database dev thiếu dữ liệu cho một số trạng thái (đợt `OPEN`, robot lỗi). Ghi rõ trong report những trạng thái chưa kiểm được thay vì tự dựng dữ liệu giả.
