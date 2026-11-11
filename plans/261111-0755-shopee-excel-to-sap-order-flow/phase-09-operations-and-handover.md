---
title: "Phase 9: Vận hành và bàn giao"
status: todo
priority: P1
effort: 3d
dependencies: [1, 2, 3, 4, 5, 6, 7, 8]
---

# Phase 9: Vận hành và bàn giao

## Overview

Hoàn thiện những gì cần để hệ thống chạy lâu dài mà không phụ thuộc lập trình viên: diễn tập dựng lại máy, thời hạn lưu dữ liệu khách, rà soát quyền, sổ tay vận hành, đào tạo. Sao lưu và cảnh báo cơ bản đã có từ phase 4 và 5; phase này kiểm chứng và khóa chúng lại.

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

1. **Diễn tập dựng lại máy.** Trên một máy Windows trống, làm theo `deployment-guide.md`: cài PostgreSQL, SAP GUI, Python, gói `shoponline[robot]`, cấu hình theo `robot-machine-setup.md`, khôi phục database bằng `restore-db.ps1` một lần từ ổ mạng công ty và một lần từ Google Drive, đăng ký tác vụ. Kiểm tra đơn, hàng đợi, và robot đọc được `zrsd001` trên QA. Ghi thời gian thực tế.
2. **Kế hoạch khi máy hỏng.** Chốt với chủ dự án: máy thay thế lấy ở đâu, ai dựng lại, và trong lúc chờ admin làm Excel tay thế nào.
3. **Thời hạn lưu.** Viết `retention.py` theo thời hạn công ty chốt. Chạy ở chế độ chỉ liệt kê trong tuần đầu, có người xem danh sách trước khi bật xóa thật.
4. **Rà soát quyền.** PostgreSQL chỉ nghe trên `localhost`; tường lửa chỉ mở cổng web cho mạng nội bộ; tài khoản Windows của robot không dùng cho việc khác; rà vai trò người dùng web và quyền T-code của user robot.
5. **Rà soát bí mật.** Quét lịch sử git; lập lịch đổi mật khẩu SAP của robot; cảnh báo khi mật khẩu sắp hết hạn.
6. **Sổ tay vận hành.** Một mục cho mỗi tình huống: robot dừng, popup lạ, phiên SAP bị đăng xuất, đơn ở `NEED_REVIEW`, đơn thiếu ánh xạ, SO gõ sai mã đơn, bản ghi `ZDI1` còn sót, đơn hủy sau khi có chứng từ, sàn đổi mẫu file, chuyển một sàn về chế độ `manual`, làm tay khi máy dừng. Mỗi mục có dấu hiệu, việc cần làm, và khi nào gọi lập trình viên.
7. **Diễn tập sự cố.** Cùng người vận hành thử ba tình huống trên QA: tắt robot giữa lượt, rút mạng khi robot đang tạo SO, tải lên file sàn thiếu cột. Sửa sổ tay ở chỗ họ vướng.
8. **Tài liệu.** Viết kiến trúc, bảo mật và lưu dữ liệu; cập nhật `README.md`. Đối chiếu từng lệnh và đường dẫn trong tài liệu với mã thật.
9. **Bàn giao.** Đào tạo admin shop online, sales admin và người quản trị; chốt người nhận từng loại cảnh báo; ghi cách thêm một sàn mới (một bộ đọc file, một dòng `platform_setting`, bảng ánh xạ của sàn).

## Todo

- [ ] Diễn tập dựng lại máy từ cả hai nơi sao lưu
- [ ] Kế hoạch khi máy hỏng
- [ ] Xóa dữ liệu theo thời hạn
- [ ] Rà soát quyền và bí mật
- [ ] Sổ tay vận hành
- [ ] Diễn tập ba sự cố
- [ ] Tài liệu kiến trúc, bảo mật
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

Việc kế tiếp có thể cân nhắc: bộ đọc Lazada khi có file mẫu, và mở robot cho TikTok nếu sản lượng tăng.
