---
phase: 1
title: "Mẫu biểu và thư viện"
status: completed
priority: P1
effort: "5h"
dependencies: []
---

# Phase 1: Mẫu biểu và thư viện

## Goal

Có hai file mẫu sạch trong repo (Word có chỗ giữ chỗ Jinja, Excel `.xlsx` một sheet) cùng hai thư viện mới, và chứng minh bằng kiểm tra tự động rằng file điền xong giống mẫu gốc 100% về định dạng.

<!-- Updated: Validation Session 2 - file xuất giống 100% mẫu về bố cục và định dạng -->
**Yêu cầu định dạng.** File xuất ra giống mẫu trong `docs/bbdchd/` ở: font, cỡ chữ, đậm/nghiêng/gạch chân, căn lề, khoảng cách đoạn, tab, viền và nền ô, gộp ô, độ rộng cột, chiều cao dòng, khổ giấy, hướng giấy, lề in, vùng in, tỷ lệ in, và hình trong Word (nếu có). Chỉ được khác: văn bản trường động, màu chữ trường động (đen), Excel là `.xlsx` chỉ còn sheet `RRG ENGLISH` và **không có logo hay hình nào** (người dùng xác nhận không cần logo; các sheet khác bỏ hẳn). Vì vậy mẫu phải được tạo **bằng cách sửa tại chỗ file gốc**, không dựng lại.

## Context

- Mẫu gốc `docs/bbdchd/BBDC_shopee.docx`, `docs/bbdchd/FM-LG-Q004.01_shopee.xls` chứa tên, địa chỉ khách thật. Thư mục này đang untracked; không commit.
- Trường đỏ Word và ô động Excel: xem bảng "Ánh xạ trường" trong [brainstorm report](../reports/brainstorm-261123-1630-invoice-return-documents.md).
- Máy phát triển có cả Microsoft Office và LibreOffice; chuyển đổi chỉ làm một lần ở đây, lúc chạy không cần Office.

## Files to Create / Modify

- Modify: `pyproject.toml`, `uv.lock` (thêm `docxtpl`, `pdfplumber`, `python-docx`, và ghim `pdfminer.six>=20251230`)
- Modify: `.gitignore` (thêm `docs/bbdchd/`) — **commit đầu tiên, trước mọi commit plan hoặc mẫu**
- Create: `src/shoponline/exports/templates/invoice_adjustment.docx`
- Create: `src/shoponline/exports/templates/return_request.xlsx`
- Create: `tests/support/__init__.py`, `tests/support/format_compare.py`, `tests/support/template_baseline.json` (ảnh chụp định dạng của mẫu gốc, sinh một lần, không chứa dữ liệu khách), `tests/exports/test_template_format.py` (mẫu và file sinh ra so với `template_baseline.json`; quét mọi phần của file zip tìm chữ đỏ, metadata, thumbnail và chuỗi dữ liệu khách)
- Modify: `pyproject.toml` `[tool.hatch.build]` nếu cần để gói kèm file mẫu (kiểm tra wheel có `templates/`)

## Tasks & Steps

1. `uv add docxtpl pdfplumber python-docx "pdfminer.six>=20251230"` (bản cũ của `pdfminer.six` có lỗ hổng giải pickle qua CMap; phải kiểm `uv.lock` đã giải ra bản mới). Ghi giấy phép (docxtpl LGPL-2.1, pdfplumber MIT) vào mô tả commit.
2. Thêm `docs/bbdchd/` vào `.gitignore` và commit riêng **trước** mọi thứ khác (repo GitHub là công khai; thư mục này và `plans/` đều đang untracked). Trước khi commit thư mục `plans/261123-0950-…` và các test, bảo đảm không còn **tên, địa chỉ, số điện thoại khách** (plan này đã được làm sạch; test dùng giá trị tổng hợp như `Nguyen Van A`); giá trị thật chỉ nằm trong `docs/bbdchd/` và biến môi trường. Mã đơn sàn và số hóa đơn của hai đơn mẫu giữ nguyên trong `plan.md` (Success Criteria): người dùng đã đồng ý giữ như hiện tại vì đây là mã nghiệp vụ, không phải thông tin cá nhân.
3. Mẫu Word, từ `BBDC_shopee.docx`, sửa trong Word:
   - Thay mỗi cụm chữ đỏ bằng một chỗ giữ chỗ gõ liền một lần (để Word giữ trong một run): `{{ doc_no }}`, `{{ buyer_name }}`, `{{ buyer_address }}`, `{{ platform_name }}`, `{{ invoice_symbol }}`, `{{ invoice_no }}`, `{{ invoice_date }}`, `{{ platform_order_id }}`, `{{ reason_text }}`, `{{ order_ref_text }}`. Câu chữ đã chốt <!-- Updated: Validation Session 1 - câu chữ lý do trả hàng -->:
     - Hủy đơn (giữ như mẫu): "Do người mua hủy đơn hàng đã đặt trên sàn thương mại điện tử {Sàn} …" và "… đơn hàng đã bị hủy số: {Mã đơn}".
     - Trả hàng: "Do người mua trả lại hàng đã mua trên sàn thương mại điện tử {Sàn} …" và "… đơn hàng bị trả lại số: {Mã đơn}".
   - Năm cứng `2026` ở dòng "Hôm nay" → `{{ year }}`; ngày, tháng để trống như mẫu.
   - `Thuế suất GTGT: 8%` (hai chỗ) → `{{ vat_rate }}%`.
   - Hai bảng hàng: một dòng dữ liệu bọc bằng `{%tr for l in before_lines %}` … `{%tr endfor %}` và `after_lines`; các ô `{{ l.name }}`, `{{ l.unit }}`, `{{ l.qty }}`, `{{ l.unit_price }}`, `{{ l.amount }}`. Dòng tổng: `{{ before.net }}`, `{{ before.tax }}`, `{{ before.total }}`, `{{ after.net }}` …
   - Đổi màu chữ chỗ giữ chỗ sang đen (file in ra không có chữ đỏ).
   - Chỉ thay chữ trong các run đỏ; không đổi style đoạn, bảng, độ rộng cột hay khoảng cách. Chỗ giữ chỗ thừa hưởng định dạng của run đỏ nó thay (trừ màu).
   - **Làm sạch trước khi commit** (file mẫu đi vào repo công khai): giải nén `.docx`, tìm trong mọi phần XML (`document.xml`, header/footer, text box, comment, revision, `customXml`) từng giá trị trường đỏ, số điện thoại, địa chỉ; xóa `docProps/thumbnail.*`; xóa tác giả, `lastModifiedBy`, công ty trong `core.xml` và `app.xml`; chấp nhận mọi thay đổi tracked rồi tắt theo dõi.
4. Mẫu Excel: mở `FM-LG-Q004.01_shopee.xls` bằng Microsoft Excel, xóa mọi sheet trừ `RRG ENGLISH`, xóa giá trị động (`H6`, `C14`, `D14`, `N14`, `P14`, `AL14`), đổi màu chữ `H6`, `D14` sang đen, **Lưu thành `.xlsx` bằng chính Excel** (Excel giữ hình, thiết lập trang, vùng in khi chuyển). **Xóa mọi hình, logo và drawing** (người dùng xác nhận không cần logo), nên không phải giữ ảnh và luồng 1,7 MB trong file gốc không đi vào mẫu; kiểm bằng cách mở file zip rằng không còn `xl/drawings`, `xl/media`, VML. Làm sạch như Word: xóa thumbnail, tên tác giả, công ty, tên đã định nghĩa (`definedNames`) và liên kết ngoài sót từ các sheet đã xóa.
5. Viết công cụ so định dạng `tests/support/format_compare.py` (dùng lại ở phase 4 và 6):
   - Word: duyệt song song mọi đoạn và ô bảng của hai file `.docx`; so `pPr` (căn lề, khoảng cách, tab, thụt lề), `rPr` trừ `color` (font, cỡ, đậm, nghiêng, gạch chân), `tblPr`/`tcPr` (viền, nền, độ rộng), `sectPr` (khổ, hướng, lề), số hình. Dòng bảng sinh thêm phải có định dạng y hệt dòng mẫu.
   - Excel: so trực tiếp các phần OOXML trong file zip, **không** chỉ qua đối tượng `openpyxl` (cùng thư viện với bên ghi nên không thấy thứ nó làm rơi): `<row ht=…>`, `<cols>`, `mergeCells`, `headerFooter`, `pageSetup`, `pageMargins`, `printOptions`, `definedNames` (vùng in), kiểu từng ô; đồng thời khẳng định file không có phần `drawing`, `media`, VML nào.
   - Sinh một lần `tests/support/template_baseline.json` từ file gốc (không chứa dữ liệu khách). Test so mẫu đã commit và file sinh ra với baseline này, vì `docs/bbdchd/` không có trong checkout sạch. Không viết test "mẫu so với chính nó" (luôn đạt, không chứng minh gì). Phạm vi so sánh chỉ gồm các thuộc tính liệt kê ở "Yêu cầu định dạng".
   - Trả về danh sách khác biệt.
6. Thử (script trong scratchpad, không commit):
   - Render Word bằng `docxtpl` với **đúng giá trị của mẫu gốc** (đọc từ các run đỏ của `docs/bbdchd/`, không chép vào plan hay test) rồi chạy `format_compare` với `BBDC_shopee.docx`: chỉ được khác màu chữ. Lặp lại với hai dòng hàng: dòng thêm có định dạng y hệt.
   - Điền Excel bằng `openpyxl` (load, ghi ô, chèn một dòng, save) rồi `format_compare` với mẫu `.xlsx` vừa lưu bằng Excel.
   - Xuất PDF cả bản gốc và bản điền bằng Word/Excel (chỉ trên máy dev), đặt cạnh nhau để soát mắt; ghi kết quả vào báo cáo phase.
7. Kiểm tra `uv build` có gói `exports/templates/*.docx|xlsx` vào wheel.

## Verification

- `uv run python -c "import docxtpl, pdfplumber"` chạy được.
- `format_compare` của bản Word điền giá trị mẫu so với `BBDC_shopee.docx` chỉ báo khác màu chữ; bản Excel điền xong so với mẫu `.xlsx` không báo khác biệt nào ngoài giá trị và màu ô động.
- Ảnh PDF gốc và bản điền đặt cạnh nhau giống nhau, trừ logo của Excel đã bỏ theo yêu cầu (ghi trong báo cáo phase).
- `git status` không có file nào dưới `docs/bbdchd/`.
- `test_template_format.py` quét **mọi phần** của hai file mẫu (không chỉ đoạn thân bài): không còn chữ đỏ, không còn thumbnail, `core.xml`/`app.xml` không có tên người; các chuỗi dữ liệu khách (tên, địa chỉ, số điện thoại của mẫu gốc) được đọc lúc chạy từ `docs/bbdchd/` và test bỏ qua phần này khi thư mục không có. Test không chứa chuỗi dữ liệu khách nào.

## Risk Assessment

- **Excel mất thiết lập in hoặc định dạng khi `openpyxl` lưu lại.** Dấu hiệu: so các phần OOXML báo khác thiết lập trang, vùng in hay kiểu ô. Xử lý trong phase: sửa thiết lập bằng `openpyxl`; vẫn không giống 100% thì **dừng và hỏi người dùng** (phương án đã biết: điền bằng Excel COM, cần Excel trên máy chạy web).
- **`docxtpl` chèn dòng bảng làm lệch định dạng** (ví dụ dòng có viền dưới riêng). Dấu hiệu: `format_compare` báo khác ở dòng thêm. Xử lý: đặt vòng lặp trên đúng dòng dữ liệu mẫu, giữ dòng tổng ngoài vòng lặp.
- **Word tách chỗ giữ chỗ thành nhiều run.** Dấu hiệu: file render còn `{{`. Xử lý: gõ lại chỗ giữ chỗ trong một lần, tắt kiểm tra chính tả trước khi lưu.
