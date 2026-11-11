---
title: "Phase 12: Vận hành, bảo mật, bàn giao"
status: todo
priority: P1
effort: 4d
dependencies: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
---

# Phase 12: Vận hành, bảo mật, bàn giao

## Overview

Hoàn thiện những gì cần để hệ thống chạy lâu dài mà không phụ thuộc lập trình viên: diễn tập khôi phục, thời hạn lưu dữ liệu cá nhân, rà soát quyền, cảnh báo phân cấp, sổ tay vận hành, tài liệu và đào tạo. Sao lưu, cảnh báo cơ bản và đối chiếu hằng ngày đã có từ phase 5 và 7; phase này kiểm chứng và khóa chúng lại.

Ứng với V2 mục 10.

## Requirements

- Khôi phục được toàn bộ hệ thống từ bản sao lưu trên máy mới, theo tài liệu.
- Dữ liệu cá nhân người mua, file vận đơn và ảnh chụp màn hình có thời hạn lưu và được xóa tự động.
- Cảnh báo phân cấp: lỗi tạm thời tự thử lại không báo; lỗi cần người thì báo ngay; còn lại gom theo giờ.
- Theo dõi giới hạn tần suất API của từng sàn.
- Vết kiểm toán đủ: mọi thao tác SAP và API, người duyệt, ảnh lỗi.
- Sổ tay cho từng tình huống vận hành, viết cho người không lập trình.
- Tài liệu dự án phản ánh hệ thống đã xây.

## Related Code Files

- Create: `src/shoponline/maintenance/retention.py`
- Modify: `src/shoponline/alerts/notifier.py` (phân cấp, gom tin)
- Create: `scripts/windows/restore-db.ps1`
- Create: `docs/operations-runbook.md`, `docs/system-architecture.md`, `docs/deployment-guide.md`, `docs/security-and-data-retention.md`
- Modify: `README.md`, `docs/robot-runbook.md`
- Create: `tests/maintenance/test_retention.py`, `tests/alerts/test_severity.py`

## Implementation Steps

1. **Diễn tập dựng lại máy.** Toàn bộ hệ thống nằm trên một máy, nên đây là bài diễn tập quan trọng nhất. Trên một máy Windows trống, làm theo `deployment-guide.md`: cài PostgreSQL, SAP GUI, Python, gói `shoponline[robot]`, cấu hình theo `robot-machine-setup.md`, khôi phục database bằng `restore-db.ps1` một lần từ bản trên ổ mạng công ty và một lần từ bản trên Google Drive (gồm cả bước giải mã), đăng ký tác vụ bằng `register-tasks.ps1`. Kiểm tra đơn, trạng thái hàng đợi, và robot đọc được một SO trên QA. Ghi thời gian thực tế.
2. **Kế hoạch khi máy hỏng.** Chốt với chủ dự án: máy thay thế lấy ở đâu, ai dựng lại, và trong lúc chờ thì sales admin và kho làm tay thế nào. Ghi vào sổ tay vận hành.
3. **Thời hạn lưu.** Viết `retention.py` xóa hoặc ẩn danh dữ liệu cá nhân người mua, file vận đơn và ảnh lỗi sau thời hạn công ty chốt; test để chắc không xóa dữ liệu kế toán cần giữ.
4. **Rà soát quyền.** PostgreSQL chỉ nghe trên `localhost`; tường lửa Windows chỉ mở cổng web cho mạng nội bộ; tài khoản Windows của robot không dùng cho việc khác; mỗi tiến trình dùng một tài khoản database có quyền tối thiểu; rà vai trò người dùng web; rà quyền T-code của user robot.
5. **Rà soát bí mật.** Quét lịch sử git tìm bí mật; lập lịch đổi mật khẩu SAP robot và khóa ứng dụng sàn; ghi cách đổi khóa mã hóa token.
6. **Cảnh báo.** Phân loại mọi cảnh báo hiện có vào ba mức; gom tin theo giờ; thêm cảnh báo cho giới hạn tần suất API, quyền kết nối shop sắp hết hạn, mật khẩu robot sắp hết hạn, sao lưu lỗi, robot dừng.
7. **Sổ tay vận hành.** Một mục cho mỗi tình huống: robot dừng khẩn cấp, popup lạ, phiên SAP bị đăng xuất, token hết hạn phải cấp quyền lại, đơn ở `NEED_REVIEW`, đơn hủy sau khi có chứng từ, sàn đổi API, đối chiếu hằng ngày lệch, làm tay khi hệ thống dừng. Mỗi mục có dấu hiệu, việc cần làm, và khi nào gọi lập trình viên.
8. **Diễn tập sự cố.** Cùng người vận hành thử ba tình huống: tắt robot giữa ca, rút mạng máy robot khi đang tạo SO ở hệ thống thử hoặc với việc đọc, làm hết hạn token. Người vận hành xử lý theo sổ tay; sửa sổ tay ở chỗ họ vướng.
9. **Năng lực.** Ghi số đơn mỗi ngày mà một phiên xử lý được theo đo thực tế, và ngưỡng cần tính tới nhiều phiên hoặc BAPI/RFC như V2 nêu.
10. **Tài liệu.** Viết kiến trúc, triển khai, bảo mật và lưu dữ liệu; cập nhật `README.md`. Đối chiếu từng lệnh và đường dẫn trong tài liệu với mã thật.
11. **Bàn giao.** Đào tạo sales admin, kho, kế toán, người quản trị; chốt người chịu trách nhiệm từng loại cảnh báo; chốt quy trình thay đổi cấu hình popup và màn hình SAP.

## Todo

- [ ] Diễn tập dựng lại toàn bộ máy từ bản sao lưu ngoài máy
- [ ] Kế hoạch khi máy hỏng đã chốt với chủ dự án
- [ ] Xóa dữ liệu theo thời hạn
- [ ] Rà soát quyền database, web, SAP
- [ ] Rà soát và lịch đổi bí mật
- [ ] Cảnh báo phân cấp và gom tin
- [ ] Sổ tay vận hành
- [ ] Diễn tập ba sự cố với người vận hành
- [ ] Ghi nhận năng lực và ngưỡng mở rộng
- [ ] Tài liệu kiến trúc, triển khai, bảo mật
- [ ] Đào tạo và phân công trách nhiệm

## Success Criteria

- Khôi phục trên máy trống thành công trong thời gian công ty chấp nhận, chỉ dùng tài liệu.
- Người vận hành xử lý được ba sự cố diễn tập mà không cần lập trình viên.
- Đối chiếu hằng ngày sàn ↔ database ↔ SAP không lệch trong 30 ngày liên tiếp.
- Không còn dữ liệu cá nhân nào quá thời hạn lưu trong database và thư mục file.
- Mỗi loại cảnh báo có người chịu trách nhiệm được ghi tên.

## Verification

- `uv run pytest` toàn bộ thoát mã 0.
- Biên bản diễn tập khôi phục và diễn tập sự cố lưu trong `docs/operations-runbook.md`.
- Mọi liên kết và lệnh trong `docs/` được chạy thử hoặc mở thử.

## Risk Assessment

- **Sao lưu có nhưng không khôi phục được.** Vì vậy tiêu chí là diễn tập thật trên máy trống, lặp lại định kỳ.
- **Tràn cảnh báo khiến người nhận bỏ qua.** Phân cấp, gom tin, và rà lại số cảnh báo mỗi tuần trong tháng đầu.
- **Phụ thuộc một người.** Sổ tay và đào tạo cho ít nhất hai người vận hành.

## Rollback

Phase này không đổi luồng nghiệp vụ. Việc xóa dữ liệu theo thời hạn là không đảo được, nên `retention.py` chạy ở chế độ chỉ liệt kê trong tuần đầu, có người xem danh sách trước khi bật xóa thật.

## Security Considerations

- Database chứa thông tin người mua: hạn chế người truy cập, có nhật ký truy cập quản trị.
- Bản sao lưu được mã hóa và lưu ngoài máy chủ chính.
- Khi một người rời vai trò vận hành: thu quyền web, đổi bí mật họ từng biết.

## Next Steps

Sau bàn giao, thay đổi lớn tiếp theo cần cân nhắc là mở rộng năng lực (nhiều phiên SAP hoặc BAPI/RFC) khi sản lượng vượt ngưỡng đã ghi ở bước 9.
