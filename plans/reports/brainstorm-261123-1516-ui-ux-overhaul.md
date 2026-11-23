# Brainstorm: đại tu giao diện và trải nghiệm web

Ngày: 2026-11-23. Người quyết định: chủ dự án. Bước tiếp theo: lập plan rồi `/ak-cook`.

## Hiện trạng (đã kiểm tra)

- FastAPI + Jinja2 render phía máy chủ; 24 template, khoảng 1.900 dòng ([templates/](../../src/shoponline/web/templates/)).
- Toàn bộ CSS là khoảng 50 dòng nội tuyến trong [base.html](../../src/shoponline/web/templates/base.html); không có thư mục static, không có bước build, không có CDN.
- Menu: 11 link phẳng trên thanh ngang, trộn việc hằng ngày, dữ liệu gốc và quản trị hệ thống; thứ tự không theo quy trình ở [daily-operations.md](../../docs/daily-operations.md).
- Trang lô dồn 5–7 nút có điều kiện vào một hàng, không cho biết đang ở bước nào. 30 thuộc tính `style=""` rải ở 6 template; bảng dùng viền ô dày.
- Hai vai trò `admin` và `viewer`; viewer bị ẩn hoặc chặn nút ghi.
- Test web (`tests/web/`) kiểm tra theo chữ nghiệp vụ, banner và mã trạng thái, không theo cấu trúc HTML.

## Quyết định của người dùng

1. Phạm vi: design system mới, sidebar mới, làm lại cả 24 trang, **thêm trang chủ "Việc hôm nay"** và thanh bước trên trang lô.
2. Điều hướng: sidebar trái, nhóm theo quy trình, đánh dấu trang đang mở, thu gọn trên màn hẹp.
3. Phong cách: công cụ vận hành gọn, nền sáng, một màu nhấn, chữ hệ thống; không dark mode.

## Hợp đồng

**Outcome:** người vận hành mở web là thấy ngay việc cần làm hôm nay, tìm mọi trang qua sidebar 4 nhóm theo quy trình, và mọi trang dùng chung một bộ component nhất quán, dễ quét.

**Constraints:**
- Giữ nguyên route, method, `action` của form, tên trường, mã trạng thái và chữ nghiệp vụ mà test đang kiểm tra.
- Giữ hợp đồng JS hiện có: `data-autosave*`, `data-server`, `table_tools.html` (sắp xếp, lọc, phân trang).
- Không thêm bước build, framework JS, CDN hay font ngoài (máy chạy thật trên Windows, có thể chỉ trong mạng nội bộ). CSS và JS tĩnh phục vụ qua `StaticFiles` của FastAPI.
- Giữ phân quyền admin/viewer như hiện tại; trang "Việc hôm nay" chỉ đọc, viewer xem được.
- Tiếng Việt; khả năng truy cập: tương phản WCAG AA, `:focus-visible`, `aria-current` cho mục menu, vùng bấm ≥ 32px.

**Sidebar đề xuất:**

| Nhóm | Mục |
|---|---|
| (đầu) | Việc hôm nay (`/`) |
| Hằng ngày | Tải file sàn, Lô đơn, Báo cáo SAP |
| Kế toán | Gửi kế toán, File Shop Online |
| Dữ liệu gốc | Ánh xạ SAP, Tên báo cáo, Khách hàng |
| Hệ thống | Robot SAP, Kết nối SAP, Sao lưu (chấm cảnh báo khi có `robot_warning`/`backup_warning`) |

**Trang "Việc hôm nay" (`/`):** chỉ dùng dữ liệu đã có, không thêm bảng hay migration. Thẻ: đơn Thiếu ánh xạ / Cần kiểm tra (link Ánh xạ SAP), lô chưa xác nhận SO/DO, đợt gửi kế toán đang `OPEN`, đơn chờ hóa đơn / tiền vô của File Shop Online (nếu lấy được với chi phí truy vấn thấp), trạng thái robot và sao lưu. Mỗi thẻ có một hành động chính.

**Trang lô:** thanh bước Tải file → Ánh xạ → Gửi sales admin → Xác nhận SO/DO → Đối chiếu → Gửi kế toán, suy ra từ trạng thái hiện có; gom nút thành một hành động chính và các hành động phụ.

**Non-goals:** không đổi logic nghiệp vụ, schema, route hiện có hay nội dung file xuất; không dark mode; không viết lại bằng SPA/Tailwind/HTMX; không đổi tài liệu vận hành ngoài tên menu và trang chủ mới.

**Acceptance criteria:**
- `uv run pytest` xanh, không sửa yếu test; thêm test cho `/` (admin và viewer, có số liệu đúng) và cho mục menu đang mở.
- Không còn `style=""` nội tuyến trong template; CSS nằm ở một file tĩnh dùng token.
- Mỗi trang trong 24 template render đúng trên 1366px và 390px, không cuộn ngang ở cấp trang (bảng rộng cuộn trong khung riêng).
- Sidebar có 4 nhóm, đúng mục, `aria-current="page"` ở trang đang mở.
- Tài liệu: cập nhật [daily-operations.md](../../docs/daily-operations.md) chỗ nhắc vị trí menu ("mục trên cùng của menu" cho Sao lưu) và nêu trang Việc hôm nay.

## Trade-offs

- **Làm lại giao diện bằng CSS tĩnh và template (đã chọn):** dựa vào giả định là các test và người dùng phụ thuộc vào chữ, không vào markup. Nếu có công cụ ngoài nào cào HTML (chưa thấy bằng chứng) thì sẽ hỏng đầu tiên.
- **Viết lại bằng framework (đã loại):** dựa vào giả định là cần tương tác phong phú phía client. Hỏng đầu tiên ở khâu deploy Windows (thêm Node và bước build vào `update-production.ps1`), trong khi 1.900 dòng template không đáng để thêm chuỗi build đó.
- **Menu thả xuống trên thanh ngang (đã loại):** giữ chiều ngang cho bảng rộng nhưng mỗi lần chuyển trang phải bấm thêm một lần, và không có chỗ cho chấm cảnh báo hệ thống.

Better approaches: none, the requested direction is kept. Evidence: SSR + Jinja đã đủ cho các luồng hiện có, và trang hôm nay dùng lại truy vấn sẵn có.

## Rủi ro chưa đóng

- Chi phí truy vấn cho thẻ "chờ hóa đơn / tiền vô": `collect_rows` của sales history có thể nặng. Nếu nặng thì chỉ hiện link, không hiện số.
- Bảng rộng (đối chiếu, đợt kế toán) trên màn 1366px khi có sidebar: cần cho sidebar thu gọn được.
