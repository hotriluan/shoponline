---
title: "Chuyển máy chạy thật sang Windows 10 và chạy ngầm mọi tác vụ"
description: "Máy Windows 10 mới thành máy chạy thật duy nhất, tự deploy khi push main như Alkana_IT; mọi tác vụ chạy không hiện cửa sổ."
status: in-progress
priority: P2
effort: 2d
branch: main
tags: [infra, docs]
blockedBy: []
blocks: []
created: 2026-11-16
---

# Chuyển máy chạy thật sang Windows 10 và chạy ngầm mọi tác vụ

## Overview

Cơ chế "push `main` → máy chạy thật tự lấy code và deploy" đã chạy trên `Alkana_IT`:
- [deploy.yml](../../.github/workflows/deploy.yml) chạy test trên GitHub rồi giao job cho runner nhãn `shoponline-prod`;
- runner gọi [update-production.ps1](../../scripts/windows/update-production.ps1) trong `C:\shoponline`.

Kế hoạch này không đổi cơ chế đó. Nó làm ba việc:
1. **Chạy ngầm:** web, robot, runner, sao lưu, retention không còn hiện cửa sổ PowerShell. Áp dụng cho cả `Alkana_IT` (Windows 11) lẫn máy mới.
2. **Script dựng máy:** một lệnh dựng máy Windows 10 trắng thành máy chạy thật, chỉ dừng ở những bước bắt buộc làm tay.
3. **Chuyển máy:** dữ liệu và nhãn `shoponline-prod` chuyển sang máy mới; `Alkana_IT` chỉ còn là máy phát triển.

Phương án và bằng chứng: [brainstorm-261116-0932-win10-production-machine-github-deploy.md](../reports/brainstorm-261116-0932-win10-production-machine-github-deploy.md).

## Hợp đồng

- **Kết quả:**
  - Máy Windows 10 mới chạy web, PostgreSQL, sao lưu, retention và robot SAP.
  - Mỗi push `main` được test rồi tự deploy lên máy mới.
  - Không tác vụ nào hiện cửa sổ.
- **Ràng buộc:**
  - Giữ nguyên workflow, nhãn `shoponline-prod` và đường dẫn chuẩn (`C:\shoponline`, `C:\Program Files\PostgreSQL\16\bin`, `C:\Program Files\7-Zip\7z.exe`).
  - Tại mỗi thời điểm chỉ có một runner `shoponline-prod` và một robot dùng `AL17016`.
  - Bí mật không đi qua GitHub.
  - Máy mới dùng một tài khoản Windows tự đăng nhập, và mọi tác vụ chạy `-AtLogOn`.
  - Máy mới chạy Windows 10 bản tiếng Anh, không có ESU.
- **Ngoài phạm vi:**
  - Docker hoặc cloud, đổi cấu trúc workflow, nhiều máy chạy thật.
  - Tự động cài SAP GUI hoặc Excel, tự động bật scripting phía SAP.
  - Chuyển repo sang private (để chủ dự án quyết riêng).

## Quyết định đã chốt (2026-11-16, chủ dự án)

1. Máy mới chạy cả robot SAP.
2. Chuyển dữ liệu hiện tại sang máy mới, gồm database và thư mục dữ liệu.
3. Dùng một tài khoản Windows tự đăng nhập.
4. Windows 10 bản tiếng Anh, không ESU. Bù lại, máy chỉ mở web cho mạng nội bộ và không dùng để duyệt web hay đọc mail.
5. Chạy ngầm mọi tác vụ.
6. Thư mục sao lưu trên máy mới giống `Alkana_IT`. Nếu có thư mục Google Drive thì cài Google Drive for desktop.
7. Gửi admin địa chỉ web mới theo IP máy mới; IT đặt IP cố định cho máy mới.
8. Sau khi chuyển, trên `Alkana_IT` chỉ tắt các tác vụ; mã, runner và database cũ giữ lại để lùi lại khi cần.
9. Dữ liệu chép qua thư mục chia sẻ của công ty; thư mục tạm được xóa sau khi so khớp.

## Mặc định do kiến trúc sư chọn (đổi được khi duyệt)

- **Khởi chạy ẩn bằng `conhost.exe --headless`** cho cả 6 tác vụ: chỉ một kiểu khởi chạy.
  - Đã thử trên `Alkana_IT`: `uv run`, file `.cmd` và Python con đều chạy, không có cửa sổ.
  - Cờ này không có trong tài liệu chính thức của Windows, và `conhost` không trả lại mã thoát của tiến trình con. Vì vậy script kiểm tra bằng một file đánh dấu.
  - Máy không qua được bài kiểm tra thì quay về cách cũ (`pwsh -WindowStyle Hidden`): vẫn chạy được, chỉ hiện cửa sổ.
- **Tác vụ đã đăng ký mà lệnh chạy khác bản mong muốn thì được đăng ký lại khi deploy.** Script giữ nguyên trigger, tài khoản và tùy chọn `--apply` của retention. Nhờ vậy chỉ cần push là `Alkana_IT` được sửa.
- **Cho phép chạy khi dùng pin.** `Alkana_IT` là laptop (ASUS Battery), và mọi tác vụ đang dừng khi rút sạc.
- **`web.log` ghi log ứng dụng và lỗi; truy cập (access log) chỉ ghi từ mức WARNING**, để file không đầy vì mỗi lần tải trang.

## Luồng sau khi xong

```
Máy phát triển (Alkana_IT)              GitHub                         Máy chạy thật (Windows 10)
  git push main  ───────────────▶  deploy.yml: test (ubuntu, PG16)
                                        │ xanh
                                        ▼
                                   job deploy ─ nhãn shoponline-prod ─▶ runner (conhost --headless)
                                                                          │
                                                                          ▼
                                                     update-production.ps1: dừng robot/web → sao lưu
                                                     → fast-forward → uv sync → migrate
                                                     → đăng ký tác vụ thiếu hoặc lệch → bật web, robot (ẩn)
```

## Phases

| # | Phase | Trạng thái | Phụ thuộc |
|---|---|---|---|
| 1 | [Chạy ngầm mọi tác vụ, log web, chạy khi dùng pin](phase-01-hidden-tasks-and-web-log.md) | mã xong 2026-11-16; chờ kiểm tra sau deploy và đăng nhập lại | — |
| 2 | [Script dựng máy chạy thật Windows 10](phase-02-production-machine-setup-script.md) | mã xong 2026-11-16; chưa chạy trên máy mới (bước đầu phase 3) | 1 |
| 3 | [Chuyển máy chạy thật và tài liệu](phase-03-cutover-and-docs.md) | in-progress: A.4 xong 2026-11-16 trên `AlkanaDuongPC` (192.168.18.123), chạy `-Prepare`, web trả lời từ LAN, 21 bảng khớp số dòng với `Alkana_IT`. A.5 (mật khẩu SAP) xong, A.2 (scripting) đã bật. Chuyển máy 2026-11-16 11:36–11:45: B.1–B.8 xong (Alkana_IT Disabled cả 5 tác vụ, runner cũ gỡ, 21 bảng khớp, runner `ALKANADUONGPC-shoponline` online, web và robot chạy). Tài liệu phần C commit `ee54cc1`. B.9 xong: push `ee54cc1`, job deploy xanh trên runner Win10. B.7 Kiểm tra SAP thành công, A.1 Autologon xong; khởi động lại 12:06 thì tự đăng nhập, web/robot/runner tự chạy không cửa sổ, robot làm xong việc #26. Còn: chạy tay `shoponline-backup` và diễn tập khôi phục trên máy mới, gửi admin địa chỉ mới, xóa `C:\shoponline-migrate`, đổi mật khẩu sao lưu đã lộ | 2 |

Phase 1 push riêng được và sửa ngay `Alkana_IT`.

## Tiêu chí hoàn thành

1. Sau khi deploy và đăng nhập lại, `Alkana_IT` (khi còn là máy chạy thật) và máy mới không có cửa sổ nào của web, robot, runner, sao lưu, retention. Web trả lời `/login`, robot hiện "đang chạy", runner online.
2. Lỗi của web ghi vào `<SHOPONLINE_DATA_DIR>\logs\web.log`.
3. Push lên `main` tự chuyển các tác vụ cũ trên máy chạy thật sang cách chạy ẩn, không phải đăng ký tay, và `--apply` của retention được giữ.
4. Rút sạc laptop thì web và robot vẫn chạy.
5. Trên máy Windows 10 trắng, `setup-production-machine.ps1` cài đủ phần mềm, lấy mã, tạo database, khôi phục bản sao lưu, đăng ký tác vụ và runner. Chạy lại lần hai không làm hỏng gì và bỏ qua bước đã xong.
6. Sau khi chuyển máy, GitHub chỉ còn runner của máy mới mang nhãn `shoponline-prod`, và trên `Alkana_IT` các tác vụ `shoponline-*` ở trạng thái Disabled.
7. Push một commit lên `main` thì job `deploy` chạy xanh trên runner máy mới.
8. Từ máy admin mở được `http://<IP máy mới>:8750/login`, đăng nhập bằng tài khoản cũ, và số lô, số đơn, bảng ánh xạ khớp với `Alkana_IT` trước khi chuyển.
9. Trang **Kết nối SAP** báo robot chạy trên máy mới, mật khẩu "đã có", và nút Kiểm tra thành công với `AEP/300`.
10. Chạy tay `shoponline-backup` tạo được file `.7z` ở các thư mục đích; diễn tập khôi phục thành công.
11. `uv run pytest` và `uv run ruff check` thoát mã 0.

## Rủi ro chính

- **Hai runner cùng nhãn.** GitHub giao job cho runner nào rảnh. Phải gỡ runner cũ trong cùng lúc chuyển máy, trước khi push thử (phase 3).
- **Hai robot cùng `AL17016`.** Khóa robot nằm trong database của từng máy, nên hai robot không chặn nhau. Phải tắt robot cũ trước khi bật robot mới.
- **`conhost --headless` trên bản Windows 10 cũ.** Có bài kiểm tra và đường quay về cách cũ (phase 1). Script dựng máy báo rõ kết quả kiểm tra.
- **Runner đang chạy job không tự đổi cách khởi chạy.** Định nghĩa tác vụ runner được cập nhật, nhưng runner đang chạy giữ cửa sổ tới lần đăng nhập hoặc khởi động lại kế tiếp.
- **Windows 10 không có bản vá.** Chủ dự án đã chấp nhận rủi ro; tài liệu ghi các biện pháp bù.
