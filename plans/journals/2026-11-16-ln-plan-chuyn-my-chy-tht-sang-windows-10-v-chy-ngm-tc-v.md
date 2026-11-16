---
title: Lên plan chuyển máy chạy thật sang Windows 10 và chạy ngầm tác vụ
date: 2026-11-16
summary: "Plan 3 phase: chạy ngầm bằng conhost --headless, script dựng máy Win10, chuyển máy; đã chứng minh nguyên nhân 3 cửa sổ PowerShell"
---

# Lên plan chuyển máy chạy thật sang Windows 10 và chạy ngầm tác vụ

## Chuyện gì đã xảy ra
Chủ dự án muốn chuyển máy chạy thật sang một máy Windows 10 64-bit, tự deploy khi push `main` giống `Alkana_IT`. Khi kiểm tra thì thấy cơ chế này đã có sẵn: runner `ALKANA_IT-shoponline` nhãn `shoponline-prod` cùng `update-production.ps1`. Phần còn thiếu là dựng máy mới và chuyển máy an toàn.

Plan: `plans/261116-0944-win10-production-machine-hidden-tasks/` (3 phase).

## Nguyên nhân 3 cửa sổ PowerShell (đã chứng minh)
- Các tác vụ đã chạy `pwsh -WindowStyle Hidden`. `Alkana_IT` là Windows 11 chưa chọn terminal mặc định, nên console được giao cho Windows Terminal 1.24, và Windows Terminal bỏ qua `-WindowStyle Hidden`.
- Thử bằng tác vụ tạm kiểu Interactive:
  - cách hiện tại hiện cửa sổ `WindowsTerminal`;
  - `uvw.exe run` và `conhost.exe --headless <.cmd>` chạy không cửa sổ.
- `conhost --headless` không trả mã thoát của tiến trình con (luôn 0), nên bài kiểm tra phải dùng file đánh dấu.
- Tác vụ thử đầu tiên nằm ở trạng thái Queued vì mặc định "không chạy khi dùng pin". `Alkana_IT` là laptop, và mọi tác vụ thật cũng đang dừng khi rút sạc.

## Quyết định
- Chủ dự án:
  - robot chạy trên máy mới;
  - chuyển dữ liệu cũ sang;
  - một tài khoản tự đăng nhập;
  - Windows 10 tiếng Anh, không ESU (chấp nhận rủi ro);
  - sao lưu giống `Alkana_IT`;
  - báo admin IP mới;
  - `Alkana_IT` chỉ tắt tác vụ, giữ lại;
  - chép dữ liệu qua thư mục chia sẻ.
- Kiến trúc sư:
  - một kiểu khởi chạy `conhost --headless`, quay về cách cũ nếu bài kiểm tra trượt;
  - `-OnlyMissing` thành "thiếu hoặc lệch" để push tự sửa tác vụ cũ, giữ `--apply` của retention;
  - thêm `web.log`;
  - cho phép chạy khi dùng pin;
  - script dựng máy có chế độ `-Prepare` (không runner, robot Disabled) để tránh hai robot cùng `AL17016`.

## Bước tiếp theo
`/ak-cook` phase 1 (sửa ngay `Alkana_IT`), rồi phase 2, rồi phase 3 chạy thật trên máy mới.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
