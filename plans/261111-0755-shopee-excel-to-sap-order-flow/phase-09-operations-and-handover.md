---
title: "Phase 9: Vận hành và bàn giao"
status: in-progress
priority: P1
effort: 3d
dependencies: [1, 2, 3, 4, 5]
---

# Phase 9: Vận hành và bàn giao

## Overview

Hoàn thiện những gì cần để hệ thống chạy lâu dài mà không phụ thuộc lập trình viên: diễn tập dựng lại máy, thời hạn lưu dữ liệu khách, rà soát quyền, sổ tay vận hành, đào tạo. Sao lưu và cảnh báo cơ bản đã có từ phase 4 và 5; phase này kiểm chứng và khóa chúng lại. Robot chỉ đọc báo cáo trên Production, nên mọi buổi diễn tập liên quan tới SAP chạy trên Production và chỉ đọc.

## Requirements

- Dựng lại được toàn bộ hệ thống trên máy mới từ bản sao lưu, chỉ theo tài liệu.
- Tên và địa chỉ khách, file tải lên, file xuất ra và ảnh chụp màn hình có thời hạn lưu và được xóa tự động.
- Sổ tay cho từng tình huống vận hành, viết cho người không lập trình.
- Tài liệu dự án phản ánh hệ thống đã xây.

## Related Code Files

- Create: `src/shoponline/maintenance/retention.py`, `tests/maintenance/test_retention.py`
- Create: `scripts/windows/restore-db.ps1`
- Create: `docs/operations-runbook.md`, `docs/system-architecture.md`, `docs/security-and-data-retention.md`
- Modify: `README.md`, `docs/deployment-guide.md`, `docs/robot-runbook.md`, `docs/daily-operations.md`

## Implementation Steps

1. **Diễn tập dựng lại máy.** Trên một máy Windows trống, làm theo `deployment-guide.md`: cài PostgreSQL, SAP GUI, Python, gói `shoponline[robot]`, cấu hình theo `robot-machine-setup.md`, khôi phục database bằng `restore-db.ps1` một lần từ ổ mạng công ty và một lần từ Google Drive, đăng ký tác vụ. Kiểm tra đơn, hàng đợi, và robot đọc được `zrsd001` trên Production. Ghi thời gian thực tế.
2. **Kế hoạch khi máy hỏng.** Chốt với chủ dự án: máy thay thế lấy ở đâu, ai dựng lại, và trong lúc chờ admin làm Excel tay thế nào.
3. **Thời hạn lưu.** Viết `retention.py` theo thời hạn công ty chốt. Chạy ở chế độ chỉ liệt kê trong tuần đầu, có người xem danh sách trước khi bật xóa thật.
4. **Rà soát quyền.** PostgreSQL chỉ nghe trên `localhost`; tường lửa chỉ mở cổng web cho mạng nội bộ; tài khoản Windows của robot không dùng cho việc khác; rà vai trò người dùng web và quyền T-code của user robot; chạy lại test lớp chặn T-code và xác nhận danh sách T-code được phép vẫn chỉ gồm `ZRSD001`, `ZRSD004`, màn hình đăng nhập và menu chính. User robot `AL17016` có quyền sửa SO (chủ dự án chọn giữ nguyên ngày 2026-11-12), nên phải bảo vệ máy robot: mật khẩu SAP chỉ nằm trong kho bí mật Windows của tài khoản `saprobot`; tài khoản `saprobot` không dùng cho việc khác và không có quyền admin Windows; không ai đăng nhập SAP bằng tay với `AL17016`; Remote Desktop vào máy chỉ cho người quản trị; máy đặt nơi có kiểm soát người ra vào.
5. **Rà soát bí mật.** Quét lịch sử git; `AL17016` là user Service nên mật khẩu không hết hạn; vẫn đổi mật khẩu khi có người rời vai trò vận hành hoặc nghi lộ mật khẩu (hệ thống nhớ 5 mật khẩu gần nhất nên không dùng lại được); định kỳ xem nhật ký đăng nhập của `AL17016` (`RSUSR200` hoặc `SM20`) để phát hiện đăng nhập không phải từ máy robot.
6. **Sổ tay vận hành.** Một mục cho mỗi tình huống: robot dừng, robot tự tạm dừng vì gặp T-code ngoài danh sách, popup lạ, phiên SAP bị đăng xuất, việc ở `NEED_REVIEW`, đơn thiếu ánh xạ, SO gõ sai mã đơn, đơn hủy sau khi có chứng từ, sàn đổi mẫu file, tải báo cáo tay khi robot dừng, làm tay khi máy dừng. Mỗi mục có dấu hiệu, việc cần làm, và khi nào gọi lập trình viên.
7. **Diễn tập sự cố.** Cùng người vận hành thử ba tình huống trên Production, chỉ đọc: tắt robot giữa lượt, rút mạng khi robot đang đọc báo cáo, tải lên file sàn thiếu cột. Sửa sổ tay ở chỗ họ vướng.
8. **Tài liệu.** Viết kiến trúc, bảo mật và lưu dữ liệu; cập nhật `README.md`. Đối chiếu từng lệnh và đường dẫn trong tài liệu với mã thật.
9. **Bàn giao.** Đào tạo admin shop online, sales admin và người quản trị; chốt người nhận từng loại cảnh báo; ghi cách thêm một sàn mới (một bộ đọc file, một dòng `platform_setting`, bảng ánh xạ của sàn).

## Todo

- [ ] Chuyển web, sao lưu, runner deploy và robot từ máy phát triển (`C:\shoponline`) sang máy chạy thật riêng; dùng chính bước dựng lại máy làm lần chuyển
- [ ] Diễn tập dựng lại máy từ cả hai nơi sao lưu
- [ ] Kế hoạch khi máy hỏng (khung trong `docs/operations-runbook.md`; chờ chủ dự án điền máy thay thế, người dựng, thời gian chấp nhận)
- [x] Xóa dữ liệu theo thời hạn: `shoponline retention`, 90 ngày (chốt 2026-11-13), giữ đơn và chỉ xóa tên, địa chỉ, file; không xóa tên, địa chỉ của đơn chưa có trong `zrsd004` và chưa hủy; tác vụ `shoponline-retention` mặc định chỉ liệt kê
- [ ] Tuần liệt kê của tác vụ xóa theo thời hạn, rồi đăng ký lại với `-RetentionApply`
- [ ] Rà soát quyền và bí mật (danh sách kiểm trong `docs/security-and-data-retention.md`; chưa chạy trên máy thật, chưa quét lịch sử git)
- [x] Sổ tay vận hành (`docs/operations-runbook.md`; sửa lại sau diễn tập)
- [ ] Diễn tập ba sự cố
- [x] Tài liệu kiến trúc, bảo mật (`docs/system-architecture.md`, `docs/security-and-data-retention.md`, README)
- [ ] Đào tạo và phân công

## Success Criteria

- Dựng lại trên máy trống thành công trong thời gian công ty chấp nhận, chỉ dùng tài liệu.
- Người vận hành xử lý được ba sự cố diễn tập mà không cần lập trình viên.
- Không còn dữ liệu khách quá thời hạn lưu trong database và thư mục file.

## Verification

- `uv run pytest` toàn bộ thoát mã 0.
- Biên bản diễn tập lưu trong `docs/operations-runbook.md`.
- Mọi liên kết và lệnh trong `docs/` được mở thử hoặc chạy thử.

## Risk Assessment

- **Sao lưu có nhưng không khôi phục được.** Tiêu chí là diễn tập thật trên máy trống.
- **Phụ thuộc một người.** Sổ tay và đào tạo cho ít nhất hai người vận hành.
- **Xóa nhầm dữ liệu còn cần.** Chế độ chỉ liệt kê trong tuần đầu; test chắc không xóa đơn chưa xuất file gửi kế toán.

## Rollback

Phase này không đổi luồng nghiệp vụ. Việc xóa theo thời hạn không đảo được, nên chỉ bật sau tuần liệt kê.

## Security Considerations

- Bản sao lưu được mã hóa và lưu ngoài máy.
- Khi một người rời vai trò vận hành: thu quyền web, đổi bí mật họ từng biết.

## Next Steps

Bộ đọc Lazada đã xong ngày 2026-11-13. Robot ghi SO và DO (phase 6–8 đã bỏ) chỉ mở lại thành dự án riêng nếu sản lượng tăng tới mức sales admin không làm kịp.
