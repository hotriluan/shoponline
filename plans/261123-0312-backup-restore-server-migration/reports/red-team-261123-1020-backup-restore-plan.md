# Red-team: plan sao lưu, khôi phục và chuyển máy

Ngày 2026-11-23. Bốn reviewer độc lập (Security Adversary, Failure Mode Analyst, Assumption Destroyer, Scope & Complexity Critic) đưa ra 40 phát hiện. Sau khi gộp các phát hiện trùng còn 15 mục: 4 Critical, 7 High, 4 Medium. Mình chấp nhận cả 15; ba mục có chỉnh sửa và hai đề xuất con bị bác (ghi ở cuối). Mọi phát hiện đều có dẫn chứng `file:line` do reviewer kiểm.

| # | Phát hiện | Mức | Reviewer | Quyết định | Áp vào |
|---|---|---|---|---|---|
| 1 | Phục hồi bản cũ hơn migration mới nhất luôn lỗi ở `migrate`: `pg_restore --clean` chỉ xóa đối tượng có trong dump, bảng mới còn lại trong khi `alembic_version` lùi về | Critical | FMA, Sec | Chấp nhận | Phase 3 |
| 2 | Khóa đang bận thì sao lưu thoát mã 0; deploy, xuất gói chuyển máy và bản an toàn khi phục hồi đều đi tiếp mà không có bản sao lưu. Bản an toàn mở kết nối mới nên không lấy được khóa mà chính lần phục hồi đang giữ | Critical | cả bốn | Chấp nhận | Phase 1, 3, 6 |
| 3 | `-Bundle drive:latest` không chạy được: kết nối Drive cần bảng đã migrate, còn nhập gói đòi database trống | Critical | AD | Chấp nhận (giải bằng mục 5 và 6) | Phase 2, 6 |
| 4 | Phục hồi đưa `app_user` và sequence của nó về cũ: cookie còn hạn của một người có thể trỏ sang tài khoản mới tạo lại cùng id (leo quyền); tài khoản đã khóa hoặc mật khẩu đã đổi sống lại | Critical | Sec | Chấp nhận (chỉnh: hủy mọi phiên sau phục hồi và cảnh báo trong hộp thoại; hỏi chủ dự án có giữ tài khoản hiện tại không) | Phase 3, 5 |
| 5 | Xuất các bảng sổ sách ra JSON rồi nạp lại là cơ chế tự chế, dễ vỡ: sequence không đặt lại, `restore_request` bị xóa giữa chừng nên phục hồi tự lùi lại, schema đổi làm hỏng lần nạp | High | cả bốn | Chấp nhận: thay bằng schema riêng `ops`, `pg_dump -N ops`; phục hồi không bao giờ đụng tới nó; `restore_request` gộp vào `backup_request` | Phase 1, 2, 3, 5 |
| 6 | Wrapper `restore-db.ps1` làm hỏng `setup-production-machine.ps1 -Archive` (database trống, chưa migrate) và bỏ `-TargetSetting`; mọi bản sao lưu cũ không có manifest bị từ chối | High | cả bốn | Chấp nhận: giữ nguyên `restore-db.ps1`; Python nhận bản cũ qua đường "legacy" | Phase 3, 6 |
| 7 | Deploy và phục hồi có thể chạy chồng: deploy migrate, bật web và robot giữa lúc `pg_restore` | High | FMA, AD | Chấp nhận: file đánh dấu bảo trì mà cả hai kiểm | Phase 3, plan |
| 8 | Vòng đời tác vụ: dòng "đang chạy" mồ côi khóa nút mãi; `IgnoreNew` nuốt `/Run`; yêu cầu phục hồi cũ chạy nhiều ngày sau; `-OnlyMissing` không đổi trigger; giới hạn 1 giờ; rollback để lại trigger 15 phút | High | FMA, Scope, AD, Sec | Chấp nhận | Phase 1, 3, 4, 5, 7 |
| 9 | Tác vụ sao lưu Python mới giữ file venv và pywin32 lúc deploy chạy `uv sync`; web và tác vụ không khai báo `--extra robot` | High | AD | Chấp nhận | Phase 1, 2 |
| 10 | Số dòng trong manifest không cùng thời điểm với dump nên diễn tập báo lệch giả | High | AD | Chấp nhận: `pg_export_snapshot` + `pg_dump --snapshot` | Phase 1 |
| 11 | Tải lên và Kiểm tra chấp nhận `.7z` không mã hóa (7z bỏ qua `-p`), manifest do chính kẻ tạo file viết; giải nén không giới hạn tên file | High | Sec | Chấp nhận (bác phần ghim 7-Zip ≥ 25.00 vì chưa kiểm chứng) | Phase 1, 3, 5 |
| 12 | Dump và `.env` đã giải mã nằm dạng rõ trong `%TEMP%`, không có yêu cầu dọn dẹp | High | Sec | Chấp nhận | Phase 1, 3 |
| 13 | Xoay vòng đưa lại quy tắc "giữ mọi bản hôm nay" mà chủ dự án đã bỏ | High | Scope | Chấp nhận | Phase 1 |
| 14 | Lỗ hổng web: GET Tải về và poll Drive chưa quy định quyền admin (mẫu hiện có dùng `current_user`); giới hạn 1 GB chỉ kiểm sau khi Starlette đã ghi cả body; banner gọi nhiều truy vấn mỗi trang; cache Drive tạo dòng trùng; kiểm "người dùng hoạt động 5 phút" không có dữ liệu; mật khẩu 7z có thể lọt vào log nằm trong bản `full` | Medium | Sec, FMA, AD | Chấp nhận | Phase 1, 3, 4, 5 |
| 15 | Phình phạm vi và lặp code: logic dừng/bật web và robot viết lại lần 2 và 3; tách credentials ba lớp làm vỡ chỗ monkeypatch trong test; biến `SHOPONLINE_PG_BIN`/`SHOPONLINE_7ZIP`, shim `KEEP_DAYS`, `backup list`, đường dev chạy `pg_dump` từ web, `-DryRun`, `import-bundle`/`verify-counts` tách riêng; mục Rollback giả định downgrade; tài liệu thiếu `.env.example`, `system-architecture.md`; đổi thư mục dữ liệu khi phục hồi sai thứ tự | Medium | Scope, FMA | Chấp nhận | Phase 1–7 |

## Bị bác

- Ghim 7-Zip ≥ 25.00 vì CVE: reviewer không dẫn được nguồn; thay bằng danh sách tên được phép giải nén và chặn đường dẫn tuyệt đối hoặc `..`.
- Gộp `0011_drive_connection` vào `0010`: các phase merge độc lập nên mỗi phase giữ migration riêng.

## Câu hỏi cho chủ dự án

1. Phục hồi có đưa tài khoản người dùng web về thời điểm của bản sao lưu không?
2. Bản sao lưu tạo trước mỗi lần deploy có lên Google Drive không?
