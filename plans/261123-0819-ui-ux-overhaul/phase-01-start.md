---
phase: 1
title: "Design system và khung trang"
status: completed
priority: P1
effort: "1d"
dependencies: []
---

# Phase 1: Design system và khung trang

## Goal

Tách CSS ra file tĩnh dựa trên token, dựng khung trang mới có sidebar nhóm theo quy trình, và bộ component dùng chung mà phase 2–5 sẽ áp vào.

## Context

- CSS hiện có khoảng 50 dòng viết thẳng trong [base.html](../../src/shoponline/web/templates/base.html#L8-L57). Các class đang dùng nhiều nhất là `muted` (81 chỗ), `box` (36), `bad` (31), `secondary` (29), `row` (22), `inline`, `num`, `tag`, `flash`, `banner`, `scroll`, `danger`, cùng các class `tt-*` của table_tools.
- Context chung của template được dựng trong `render()` ở [app.py](../../src/shoponline/web/app.py#L160-L177): `user`, `messages`, `backup_warning`, `robot_warning`, `robot_enabled`, `robot_verified`.
- Chưa có thư mục static. Hatch mặc định đóng gói mọi file trong `src/shoponline/`.

## Files

- Create: `src/shoponline/web/static/app.css` (token, base, layout, component)
- Create: `src/shoponline/web/static/app.js` (chuyển script autosave từ base.html sang, thêm nút mở/đóng sidebar)
- Modify: `src/shoponline/web/app.py` (mount `StaticFiles` tại `/static`; thêm `nav_section`/`request.url.path` vào context để đánh dấu mục đang mở)
- Modify: `src/shoponline/web/templates/base.html` (khung mới; giữ `{% include "table_tools.html" %}`)
- Create: `src/shoponline/web/templates/_nav.html` (sidebar, dữ liệu menu khai báo một lần)
- Create: `src/shoponline/web/templates/_macros.html` (macro: `page_header`, `card`, `stat`, `status_badge`, `empty_state`, `action_bar`)
- Modify: `tests/web/` thêm test cho sidebar (`aria-current`, nhóm Hệ thống, chấm cảnh báo)

## Steps

1. Chạy `python C:\Users\luanh\.claude\skills\ak-ui-ux-pro-max\scripts\design_system.py` (đọc `--help` trước) với yêu cầu "internal operations admin tool, data-dense tables, Vietnamese, light". Đọc `references/quick-reference-rules.md` §1, §5, §6, §8, §9. Nạp skill `ak-frontend-design` để định hướng thẩm mỹ. Ghi các lựa chọn token vào đầu `app.css` dưới dạng comment ngắn.
2. Token trên `:root`: thang màu trung tính, một màu nhấn, màu ngữ nghĩa `ok`/`warn`/`bad`/`info` (mỗi màu có nền nhạt và chữ đạt 4.5:1), khoảng cách theo bậc 4px, bo góc, bóng, chữ `"Segoe UI", system-ui`, body 14px cho bảng dày và 15px cho văn bản, `font-variant-numeric: tabular-nums` cho số.
3. Component, giữ nguyên tên class cũ để template chưa đổi vẫn hiển thị đúng: `button` / `.button` có các biến thể `secondary`, `danger`, `ghost`, cỡ `sm`, `:disabled`; `.box` thành card; `.flash` thành alert có biểu tượng SVG nội tuyến; `.tag` thành badge; ánh xạ các class `.s-*` và `.j-*` sang màu ngữ nghĩa; bảng có header dính, dòng kẻ ngang, hover, bảng `.scroll` cuộn trong khung; form có nhãn phía trên và trạng thái focus/invalid; `.banner` thành thanh cảnh báo.
4. Layout: lưới `sidebar 232px | main`. Sidebar cố định, có tên sản phẩm, 4 nhóm theo bảng trong brainstorm, người dùng và vai trò, nút đăng xuất ở chân. Dưới 1024px sidebar thu thành ngăn kéo mở bằng nút ☰ (`aria-expanded`, Esc để đóng, bẫy focus không bắt buộc). Main rộng tối đa 1440px. Trang lỗi và trang chưa đăng nhập dùng layout một cột.
5. `_nav.html`: một danh sách Python-literal trong Jinja gồm (nhóm, nhãn, href, tiền tố khớp). Mục đang mở là mục có tiền tố đường dẫn dài nhất khớp với đường dẫn hiện tại, để `/robot/sap-connection` sáng mục Kết nối SAP chứ không phải Robot SAP. Gắn `aria-current="page"`. Nhóm Hệ thống có chấm khi có `robot_warning` hoặc `backup_warning`. Mục Việc hôm nay trỏ `/`, nhưng phase 2 mới bật trang đó; tới lúc đó giữ `/` chuyển hướng như cũ.
6. Chuyển script autosave sang `app.js` nguyên văn (không đổi hành vi), nạp bằng `<script src="/static/app.js" defer>`. Thêm `?v=<mtime hoặc hash>` vào URL CSS/JS để cache được làm mới sau deploy.
7. Giữ `{% block head %}` trong `<head>` (trang đợt kế toán dùng nó cho thẻ meta refresh). <!-- Updated: Validation Session 1 -->
8. Giữ nguyên chữ của banner và flash (test kiểm tra "Robot SAP đang dừng", "chưa được xác nhận").

## Verification

- `uv run pytest tests/web -q` xanh.
- Test mới: GET `/robot/sap-connection` thì chỉ mục Kết nối SAP có `aria-current="page"`; GET `/static/app.css` trả 200.
- Mở `/batches` ở 1366px và 390px (phase 6 dùng cùng cách chụp màn hình); bảng cũ hiển thị đúng chỉ nhờ class giữ tên cũ.

## Risks

- Đổi tên class sẽ làm vỡ các trang chưa làm lại. Biện pháp: giữ class cũ làm alias trong phase này, phase 6 mới gỡ alias thừa.
- `StaticFiles` cần route không bị middleware đăng nhập chặn. Kiểm tra trang `/login` tải được CSS khi chưa đăng nhập.
