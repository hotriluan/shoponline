---
title: "Phase 4: Xác nhận lô, báo cáo SAP và file gửi kế toán"
status: in-progress
priority: P1
effort: 4d
dependencies: [3]
---

# Phase 4: Xác nhận lô, báo cáo SAP và file gửi kế toán

## Overview

Hoàn tất chế độ thủ công. Sau khi sales admin báo đã tạo SO và DO, admin shop online xác nhận lô và tải hai file báo cáo SAP lên. Hệ thống lưu số SO, chỉ ra các điểm lệch, và xuất file gửi kế toán. Đây là lần đầu hệ thống được dùng thật, nên triển khai lên máy chạy thật và sao lưu cũng bắt đầu từ đây.

## Key Insights

- `zrsd001` với lựa chọn "Complete" trả về SO đã có DO kèm `PO No` (`docs/zrsd001complete.XLSX`), nên không còn phải lấy báo cáo trước khi làm DO.
- Chuỗi ghép `zrsd004` → `zrsd001` qua số SO → khách hàng qua mã đơn đã được dựng lại và khớp 15/15 dòng với `docs/SHOP ONLINE 111126.XLSX`.
- File tay chèn ba cột `mã đơn hàng`, `tên khách hàng`, `địa chỉ` ngay sau cột `SO Reference`, giữ nguyên các cột còn lại và cả hai dòng tổng cuối file.
- `zrsd004` và `zrsd001` chứa đơn của cả ba sàn. `PO No` của TikTok là chuỗi 18 chữ số.
- SO của bộ sản phẩm có dòng phụ giá 0; so giá trị theo tổng cả SO.
- Đơn đã hủy DO không còn trong `zrsd004`, nên tự rơi khỏi file gửi kế toán.

## Requirements

- Nút "Sales admin đã tạo SO và DO" trên màn hình lô, ghi người và thời điểm.
- Tải file `zrsd001` lên: hệ thống lưu mọi cặp số SO ↔ `PO No` (của mọi sàn) và chuyển đơn khớp sang `SO_LINKED`.
- Báo cáo lệch của lô, bốn loại:
  1. Đơn `READY` chưa có SO.
  2. SO của khách hàng SAP của sàn, trong ngày, có `PO No` không khớp đơn nào. Admin nối tay SO đó với một đơn.
  3. Một `PO No` có hai SO.
  4. Tổng `Net Value (Incl)` của SO khác giá trị mong đợi, hoặc mã vật tư và số lượng khác đơn.
- Tải file `zrsd004` lên: hệ thống xuất `SHOP ONLINE ddmmyy.xlsx` với ba cột chèn sau `SO Reference`. Mọi cột và mọi dòng khác giữ nguyên thứ tự và giá trị.
- Trước khi xuất, hiện danh sách dòng thiếu mã đơn, thiếu tên hoặc thiếu địa chỉ. Admin vẫn xuất được sau khi xem cảnh báo.
- Đơn có DO trong `zrsd004` chuyển sang `DELIVERED` và lưu số DO.
- Nhập lại cùng file báo cáo không đổi dữ liệu.
- Sao lưu database hằng ngày, mã hóa, ra ổ mạng công ty và Google Drive.

## Architecture

```
importers/zrsd001_report.py   đọc file, bỏ dòng không có số SO
importers/zrsd004_report.py   đọc file, giữ cả dòng tổng để ghi lại nguyên vẹn
reconcile/so_link.py          lưu sap_so_ref, nối đơn, sinh báo cáo lệch
exports/accounting_workbook.py  zrsd004 + ba cột
web/routes/batches.py         nút xác nhận, tải báo cáo, báo cáo lệch, tải file kế toán
scripts/windows/backup-db.ps1, register-tasks.ps1
```

Bảng mới `sap_so_ref`: số SO, `PO No`, khách hàng SAP, ngày chứng từ, tổng giá trị gồm thuế, và các dòng (mã vật tư, số lượng) ở bảng con `sap_so_ref_item`. Khóa chính là số SO.

Ghép khi xuất: mỗi dòng `zrsd004` lấy `SO Reference` → `sap_so_ref.po_no` → `customer_info` theo mã đơn.

## Related Code Files

- Create: `src/shoponline/importers/zrsd001_report.py`, `zrsd004_report.py`
- Create: `src/shoponline/reconcile/so_link.py`, `src/shoponline/exports/accounting_workbook.py`
- Create: `migrations/versions/<rev>_sap_so_ref.py`
- Modify: `src/shoponline/web/routes/batches.py`, `web/templates/`
- Create: `scripts/windows/backup-db.ps1`, `scripts/windows/register-tasks.ps1`
- Create: `tests/importers/test_sap_reports.py`, `tests/reconcile/test_so_link.py`, `tests/exports/test_accounting_workbook.py`
- Create: `docs/deployment-guide.md`, `docs/daily-operations.md`

## Implementation Steps

1. Thêm vào `build_fixtures.py` file `zrsd001` và `zrsd004` tự dựng, đúng toàn bộ tiêu đề cột của file thật, có dòng tổng, có SO ba dòng của bộ sản phẩm, có `PO No` 18 chữ số.
2. Viết hai bộ đọc báo cáo, dùng lại `excel_table.py`.
3. Viết `so_link.py`. Test từng loại lệch, test nối tay, test nhập lại không đổi.
4. Viết `accounting_workbook.py`. Test: ba cột ở đúng vị trí, các ô khác giống hệt file vào, dòng tổng còn nguyên.
5. Trên máy phát triển, chạy với `docs/zrsd001.XLSX`, `docs/zrsd004.XLSX`, `docs/NOTE TT KH T11.XLSX` và so từng ô với `docs/SHOP ONLINE 111126.XLSX`.
6. Thêm nút xác nhận, màn hình tải báo cáo, báo cáo lệch và tải file kế toán.
7. Viết `backup-db.ps1`: `pg_dump`, mã hóa, chép ra hai nơi, xóa bản cũ theo số ngày giữ; cảnh báo trên web khi bản sao lưu gần nhất quá 36 giờ.
8. Viết `register-tasks.ps1` đăng ký `shoponline web` chạy khi máy khởi động và tác vụ sao lưu hằng ngày. Kiểm tra trước là chưa có tiến trình `web` nào đang giữ cổng.
9. Triển khai lên máy chạy thật theo `deployment-guide.md`; nhập bảng ánh xạ; tạo tài khoản.
10. Chạy song song 10 ngày làm việc: admin vẫn làm file tay, so từng ô với file hệ thống mỗi ngày. Mỗi khác biệt được sửa và thêm thành ca test.

## Todo

- [x] File báo cáo test tự dựng
- [x] Bộ đọc `zrsd001` và `zrsd004`
- [x] Nối số SO và bốn loại lệch
- [x] File gửi kế toán
- [x] Khớp từng ô với `SHOP ONLINE 111126.XLSX` (18 × 37, 0 ô khác)
- [x] Nút xác nhận và các màn hình
- [x] Sao lưu mã hóa ra hai nơi (script và diễn tập khôi phục trên máy phát triển; chưa cấu hình ổ mạng và Google Drive thật)
- [ ] Tác vụ `web` và sao lưu trong Task Scheduler (script đã viết, chưa chạy trên máy thật)
- [ ] Triển khai máy chạy thật
- [ ] 10 ngày chạy song song (cổng G1)

## Success Criteria (cổng G1)

- 10 ngày làm việc liên tiếp, file gửi kế toán khớp từng ô với file admin tự làm.
- Một SO cố ý gõ sai mã đơn trên QA hoặc trong ca test được liệt kê ở loại lệch số 2.
- Khôi phục thử một bản sao lưu vào database tạm thành công.

## Verification

- `uv run pytest tests/importers tests/reconcile tests/exports` thoát mã 0.
- Biên bản 10 ngày chạy song song ghi trong `docs/daily-operations.md`.

## Risk Assessment

- **Admin chạy báo cáo sai bộ lọc.** Hệ thống so ngày chứng từ và khách hàng SAP trong file với lô đang xác nhận; không có dòng nào của lô thì báo rõ.
- **Xuất file trước khi nhập đủ tên khách.** Cảnh báo liệt kê dòng thiếu trước khi xuất.
- **Máy chạy thật hỏng.** Admin quay lại làm Excel tay; dữ liệu khôi phục từ bản sao lưu.

## Rollback

Hệ thống không ghi gì vào SAP. Dừng dùng là quay lại quy trình Excel tay.

## Security Considerations

- File gửi kế toán có tên và địa chỉ khách; lưu trong thư mục giới hạn quyền.
- Bản sao lưu được mã hóa trước khi rời máy; khóa mã hóa nằm trong kho bí mật, không nằm cạnh bản sao lưu.

## Next Steps

Phase 5 thay việc tải hai file báo cáo bằng robot tự đọc SAP.
