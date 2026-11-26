# Nghiệm thu: đơn hủy, trả hàng trong file Shop Online, báo cáo và các module

Ngày: 26/11/2026. Plan: [plan.md](../261126-0404-returns-in-sales-reporting/plan.md).

## Kết quả theo tiêu chí

| Tiêu chí | Kết quả | Bằng chứng |
|---|---|---|
| Đơn A trả cả đơn trước khi dán, đơn B trả một phần sau khi dán: SUM `Customer paid` và SUM `Transaction` bằng giá trị bán thật và số đơn thật | Đạt (test) | `tests/exports/test_sales_history_returns.py`: `test_a_return_issued_before_pasting_sits_in_the_same_file_and_nets_to_zero` (SUM J = 0, cột I của dòng âm là −1, dòng bán giữ công thức), `test_a_partial_return_after_pasting_comes_alone_with_zero_transactions` (cột I = 0) |
| Hủy phiếu sau khi dòng âm đã dán: có dòng đảo; hủy khi chưa dán: không sinh dòng | Đạt (test) | `test_cancelling_a_return_after_its_rows_were_pasted_adds_the_reversal` (+1, dương), `test_a_return_cancelled_before_its_rows_were_pasted_adds_nothing`; qua route: `tests/web/test_sales_history_return_routes.py::test_unconfirming_negative_rows_whose_reversal_was_confirmed_later_is_refused` |
| Báo cáo từ 11/11/2026 khớp file Shop Online theo tháng đặt đơn; đơn trả cả đơn không còn được đếm | Đạt (test) | `tests/reports/test_report_views.py::test_the_report_matches_the_shop_online_file_month_by_month`, `tests/reports/test_queries.py::test_an_order_returned_whole_is_no_longer_counted` (Tổng quan, Theo sàn, Theo tỉnh, Theo sản phẩm) |
| Tỷ lệ trả tính trên cùng cơ sở có thuế với doanh thu hóa đơn | Đạt (test) | `test_return_rate_is_returns_over_invoice_revenue_including_vat`, `test_returns_count_issued_documents_only_at_invoice_value_with_vat` |
| Nhãn ở chi tiết đơn, danh sách đơn của lô, Tiền về Lazada, đợt gửi kế toán, file NHÁP và TẤT CẢ ĐƠN; mất khi hủy phiếu | Đạt (test) | `tests/web/test_return_flags_pages.py` (lô, nhãn mất khi hủy phiếu, Lazada có cảnh báo khi trả cả đơn, đợt kế toán), `tests/web/test_web_flow.py::test_the_order_page_shows_the_return_label_and_links_it_for_admins_only`, `test_the_draft_labels_return_rows`, `test_the_all_orders_file_labels_the_order_and_adds_its_return_rows` |
| Đơn có DO, chưa có hóa đơn: hủy được và rời báo cáo; đã có hóa đơn: bị chặn | Đạt (test) | `tests/domain/test_cancel_order.py` (từ chối khi có hóa đơn, hủy được và rời hai hàng chờ, cảnh báo khi DO đã gửi kế toán, `transition` một mình bị từ chối), route trong `tests/web/test_web_flow.py` |
| Phiếu phát hành trước khi triển khai được bổ sung dòng trừ bằng lệnh một lần | Đạt | `tests/returns/test_sale_lines.py::test_backfill_writes_missing_sale_lines_once_and_reports_what_it_cannot`; trên dev: `shoponline return-sale-lines backfill` chạy được, bổ sung 0 phiếu (dev chưa có phiếu nào) |
| `uv run pytest` và `uv run ruff check` đạt | Đạt | 1109 passed, 3 skipped (cần PDF thật); `ruff check` sạch |

## Migration trên database dev

- Sao lưu trước khi đổi schema bằng `pg_dump` (dev chưa cấu hình `SHOPONLINE_BACKUP_DIRS` nên `shoponline backup run` không chạy được): `backups-local/shoponline_dev-before-0018-261126.dump`, nằm ngoài git (`*.dump`).
- `shoponline migrate`: 0017 → 0019. `downgrade -2` rồi `upgrade head` đều chạy được, trên dev và trên database test.
- Backfill: 0 phiếu bổ sung, 0 phiếu bị chặn (dev chưa có phiếu nào).

## Chạy tay trên dev (26/11/2026)

Chạy bằng web thật (đăng nhập admin, tải file, xác nhận dán) và dịch vụ lập/hủy phiếu trên `shoponline_dev`, trong một transaction rồi rollback, nên dev không còn dữ liệu mẫu và số biên bản kế tiếp vẫn là 080. File sinh ra trên đĩa đã xóa.

| Bước | Kết quả |
|---|---|
| Đơn C (đã có DO, chưa có hóa đơn): hủy bằng `cancel_order` | Hủy được; không có trong file |
| Đơn A trả cả đơn trước khi dán | File 1 gồm dòng bán, dòng âm (−1, −120.000), cột I của dòng âm = −1; tổng `Customer paid` và số lượng của A = 0 |
| Đơn B trả một phần sau khi dán | File 2 chỉ có một dòng âm (−1, −30.000), cột I = 0 |
| Hủy phiếu của B sau khi dòng âm đã dán | File 3 chỉ có dòng đảo (+1, +30.000), cột I = 0 |
| Sau khi xác nhận cả ba file | Không còn dòng nào của ba đơn chờ dán |
| So file với view báo cáo, theo từng đơn | A: 0 đồng, 0 sản phẩm; B: 120.000 đồng, 3 sản phẩm; C: không có ở cả hai; file và báo cáo khớp |

## Chưa làm

- Gửi kế toán mô tả cách ghi mới trước lần dán đầu tiên: việc của người dùng (xem [deployment-guide.md](../../docs/deployment-guide.md)).

## Ghi chú

- Plan giả định trang phiếu chỉ admin xem; thực tế `/returns/{id}` mở cho mọi người đăng nhập. Nhãn mới vẫn theo plan (viewer không có liên kết), còn ô "Trả hàng" sẵn có ở trang đơn vẫn có liên kết cho viewer như trước.
