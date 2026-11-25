---
phase: 2
title: "Bộ đọc PDF phiếu vận đơn"
status: done
priority: P1
effort: "5h"
dependencies: []
---

# Phase 2: Bộ đọc PDF phiếu vận đơn

## Goal

Hàm thuần `read_label_pdf(data: bytes) -> LabelRead` trả về các nhãn đọc được
`(platform, order_id, name, address, pages)` và danh sách số trang không đọc được, cho mẫu SPX (Shopee) và
J&T (TikTok).

## Files

- Create: `src/shoponline/importers/shipping_label_pdf.py`
- Create: `tests/importers/test_shipping_label_pdf.py`
- Modify: `.gitignore` (thêm `docs/**/*.pdf`; hiện chỉ có `docs/*.pdf` nên `docs/tenkhach/` lộ ra trong `git status`)

## Thiết kế

Hai lớp để test được mà không cần thư viện tạo PDF:

1. **Lớp PDF → dòng chữ:** `_page_lines(page) -> list[TextLine]`, `TextLine(text, x0, x1, top, size, bold)`
   lấy từ `page.extract_text_lines(return_chars=True)`, chữ chuẩn hóa NFC, `bold` = tên font chứa `Bold`.
   Với nhãn TikTok cần cắt vùng trái đường kẻ dọc (x < 190) trước khi gom dòng để tên không dính mã phân loại.
2. **Lớp dòng chữ → nhãn:** `parse_spx(lines)`, `parse_jt(lines)` thuần, nhận `TextLine`, trả `Label | None`.

Kiểm file theo khuôn `invoice_pdf.py`: chữ ký `%PDF-`, `MAX_BYTES = 40 MB`, `MAX_PAGES = 500`; lỗi ném
`FileRejected` với thông báo chỉ nêu số trang/trường.

Nhận mẫu theo từng trang (chữ đã NFC):

- **SPX Shopee:** có `Mã vận đơn:` và `Mã đơn hàng:` và `Đến:`. Mã đơn: chữ sau `Mã đơn hàng:`. Các dòng cùng cột
  với `Đến:` (x0 ≥ x0 nhãn − 2, nằm dưới nhãn, trong nửa trái trang ≈ x < 0,58 × width): dòng đầu là **tên**;
  các dòng chữ thường tiếp theo là **địa chỉ**, dừng ở dòng chữ đậm đầu tiên (mã tuyến như `MBD-28-12-TN02-N`);
  nối bằng dấu cách.
- **J&T TikTok:** có `Order ID:` và `Người nhận`. Mã đơn: số sau `Order ID:`. **Tên** = chữ đậm cùng dòng nhãn
  `Người nhận`, trái x≈190. **Địa chỉ** = các dòng đậm trong vùng địa chỉ (x 15–190, dưới dòng SĐT `(+84)`,
  trên ô `Trọng lượng`): dòng đường (cỡ chữ lớn nhất), rồi dòng xã, rồi dòng tỉnh; bỏ chữ thường
  `ĐƯỢC ĐỒNG KIÊM` và mã nhỏ cỡ < 5.
- Ghép dòng đường TikTok bị ngắt theo ký tự: mảnh cuối dòng trước + mảnh đầu dòng sau, nếu kết quả có đúng một
  cụm nguyên âm thì nối liền, ngược lại chèn dấu cách (`Lon|g` → `Long`, `hu|yện` → `huyện`, `lược|huyện` →
  `lược huyện`).
- Chuẩn hóa địa chỉ: gộp khoảng trắng, bỏ `,` thừa cuối mỗi phần, nối các phần bằng `, ` và thêm `, Việt Nam`
  (cùng định dạng với `domain.order.default_address`, để `province_of`/`place_key` đọc đúng tỉnh mới ở cuối).
- Trang không khớp mẫu nào, hoặc khớp mà thiếu mã đơn/tên: đưa số trang vào `unreadable`.
- Gộp các trang cùng `(platform, order_id)`; nếu tên hoặc địa chỉ giữa các trang khác nhau thì đánh dấu
  `conflicting=True` để phase 3 đưa vào nhóm chờ xác nhận.

## Todo

- [ ] Thêm `docs/**/*.pdf` vào `.gitignore`
- [ ] Kiểm file + giới hạn
- [ ] `_page_lines` và nhận mẫu
- [ ] `parse_spx`, `parse_jt`, ghép dòng ngắt ký tự, chuẩn hóa địa chỉ
- [ ] Gộp trang cùng mã đơn
- [ ] Test

## Verification

- Test thuần với `TextLine` dựng tay (tên, địa chỉ giả, tọa độ lấy theo mẫu thật): đọc đúng SPX, J&T; tên TikTok
  `user…` giữ nguyên; bỏ `ĐƯỢC ĐỒNG KIÊM`, bỏ dòng đậm mã tuyến SPX; 3 trường hợp ngắt dòng ở trên; trang lạ vào
  `unreadable`; hai trang cùng mã đơn gộp làm một; hai trang mâu thuẫn bị đánh dấu.
- Test kiểm file: không phải PDF, quá dung lượng, quá số trang đều ném `FileRejected`.
- Test với file thật, bỏ qua khi không có biến môi trường (theo `test_invoice_pdf.py:150`):
  `SHOPONLINE_SAMPLE_SPX_LABEL_PDF` cho 16 nhãn, `SHOPONLINE_SAMPLE_JT_LABEL_PDF` cho 7 nhãn, mọi địa chỉ có
  `province_of(...)` khác `None`. Không commit file thật.
- `uv run pytest tests/importers/test_shipping_label_pdf.py -q`; `git status` không còn hiện `docs/tenkhach/`.

## Risks

- Sàn đổi bố cục: trang rơi vào `unreadable`, admin nhập tay. Bộ đọc mẫu mới chỉ thêm một hàm `parse_*`.
- Tên SPX rất dài xuống dòng sẽ lẫn vào địa chỉ; mẫu hiện tại không có, admin sửa được trên trang.
