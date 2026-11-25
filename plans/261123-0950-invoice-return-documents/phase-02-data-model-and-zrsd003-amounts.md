---
phase: 2
title: "Dữ liệu và tiền zrsd003"
status: completed
priority: P1
effort: "4h"
dependencies: [1]
---

# Phase 2: Dữ liệu và tiền zrsd003

## Goal

Schema cho master tên trên hóa đơn, phiếu trả hàng, bộ đếm số biên bản; zrsd003 lưu thêm tiền hàng và thuế; lệnh CLI nhập số bắt đầu một lần.

## Context

- `sap_tax_invoice` (khóa `delivery`) chưa lưu tiền: [models.py](../../src/shoponline/db/models.py), [sap_reports.py](../../src/shoponline/importers/sap_reports.py) `read_zrsd003`, [report_ingest.py](../../src/shoponline/reconcile/report_ingest.py) `ingest_zrsd003` (upsert `on_conflict_do_update`).
- zrsd003 có cột `Net Value (VND)`, `Tax (VND)` (đã kiểm với file thật).
- Migration mới nhất: `0011_drive_connection`. Bảng mới ở schema `public` (dữ liệu nghiệp vụ). Sao lưu `db` hằng ngày chỉ chép file kind `accounting_file` (`backup/archive.py`); file phiếu xử lý ở phase 5.
- Giờ Việt Nam lấy từ `shoponline.clock.today_vn`; mọi ngày phát hành dùng hàm này, không dùng `now()` của UTC.

## Files to Create / Modify

- Create: `migrations/versions/0012_sales_return.py`
- Modify: `src/shoponline/db/models.py`
- Modify: `src/shoponline/importers/sap_reports.py` (`TaxInvoiceRow`, `read_zrsd003`)
- Modify: `src/shoponline/reconcile/report_ingest.py` (`ingest_zrsd003`)
- Create: `src/shoponline/returns/__init__.py`, `src/shoponline/returns/numbering.py`
- Modify: `src/shoponline/cli.py` (lệnh `return-number`)
- Modify: `src/shoponline/config.py`, `.env.example`, `tests/test_config.py` (mẫu ký hiệu hóa đơn `SHOPONLINE_INVOICE_SYMBOL_PATTERN`, mặc định `1C{yy}TAL`, `yy` = hai số cuối năm của `billing_date`; mẫu hỏng hoặc rỗng thì ứng dụng báo lỗi khi khởi động)
- Modify: `tests/importers/test_zrsd003.py`; Create: `tests/returns/test_numbering.py`, `tests/returns/conftest.py` (fixture commit thật cho test song song)

## Tasks & Steps

1. Sao lưu trước khi đổi schema trên database dev: `uv run shoponline backup run --kind db --no-drive`.
2. Migration `0012_sales_return`:
   - `sap_tax_invoice`: thêm `net_value_vnd bigint NULL`, `tax_vnd bigint NULL`.
   - `invoice_item_text`: `material_number varchar(20) PK`, `invoice_name text NOT NULL`, `invoice_unit text NOT NULL`, `stock_unit varchar(10) NOT NULL DEFAULT 'PC'`, `source varchar(40) NOT NULL` (số hóa đơn PDF hoặc `manual`), `updated_by`, `updated_at`.
   - `document_counter`: `doc_type varchar(30)`, `year integer`, `next_seq integer NOT NULL`, PK `(doc_type, year)`.
   - `sales_return`: `id`, `sales_order_id` FK, `reason_kind` (`CANCEL`/`RETURN`), `status` (`ISSUED`/`VOID`), `doc_year`, `doc_seq`, `doc_no` (unique), `full_return bool`, bản chụp hóa đơn (`delivery` (DO), `tax_invoice_doc`, `invoice_symbol`, `billing_date`, `invoice_net`, `invoice_tax`, `vat_rate`), `returned_net`, `returned_tax`, bản chụp `buyer_name`, `buyer_address`, `platform_name`, `docx_file_id`, `xlsx_file_id` (FK `generated_file`), `issued_by`, `issued_at`, `voided_by`, `voided_at`, `void_reason`. `UNIQUE (doc_year, doc_seq)`; partial unique index `sales_order_id WHERE status = 'ISSUED'`.
   - `sales_return_line`: `return_id` FK cascade, `line_no`, `so_item_no`, `material_number`, `sap_name` (tên SAP cho Excel) <!-- Updated: Validation Session 2 - Excel D14 dùng tên SAP -->, `invoice_name`, `invoice_unit`, `stock_unit`, `invoice_qty numeric(15,3)`, `return_qty numeric(15,3)`, `unit_price bigint`, `amount_before bigint`, `amount_returned bigint`. PK `(return_id, line_no)`. Phiếu lưu **mọi dòng hóa đơn**, kể cả dòng có `return_qty = 0`, vì bảng "trước điều chỉnh" vẽ lại từ bản chụp.
3. Model SQLAlchemy cho bốn bảng mới và hai cột mới.
4. `read_zrsd003`: đọc thêm `Net Value (VND)`, `Tax (VND)` bằng `parse_money` ([excel_table.py](../../src/shoponline/importers/excel_table.py)). Hai cột này **không** vào `ZRSD003_REQUIRED` (`read_table` chỉ biết cột bắt buộc): kiểm tra tên cột có trong `table.columns` trước khi đọc; file thiếu cột vẫn nhập được, giá trị là `None` (giữ tương thích với file tải tay cũ). `ingest_zrsd003` ghi hai cột trong `set_` bằng `func.coalesce(stmt.excluded.net_value_vnd, SapTaxInvoice.net_value_vnd)` (tương tự `tax_vnd`), để file cũ không có cột tiền không ghi đè tiền đã lưu bằng `NULL`. Hai nơi gọi `ingest_zrsd003` (`web/routes/sap_reports.py`, `saprobot/worker.py`) giữ nguyên chữ ký.
5. `returns/numbering.py`:
   - `DOC_TYPE = "invoice_adjustment"`.
   - `set_start(session, year, start)`: lấy `pg_advisory_xact_lock` của loại tài liệu (cùng cách `backup/trigger.py`), rồi chỉ chạy được khi chưa có dòng `document_counter` nào của loại này và chưa có `sales_return` nào; nếu không thì báo lỗi (một lần duy nhất).
   - `next_number(session, issued_on) -> (year, seq, doc_no)`: `issued_on` luôn là `today_vn()`. Tạo dòng của năm bằng `INSERT … ON CONFLICT (doc_type, year) DO NOTHING`, rồi `SELECT … FOR UPDATE` dòng đó (`FOR UPDATE` trên dòng chưa tồn tại không khóa gì). Dòng năm mới chỉ được tạo khi đã có dòng của năm trước (`next_seq = 1`); không có dòng nào thì ném `NumberingNotConfigured`. Lỗi trùng khóa của bộ đếm không bao giờ được dịch thành "đơn đã có phiếu". Định dạng `f"{seq:03d}/{month:02d}.{year} ALK-KH.STMĐT"` (phần đuôi là hằng số trong mã; `doc_no` lưu cả chuỗi).
6. CLI: `shoponline return-number start <N> [--year YYYY]` và `shoponline return-number show`. Ghi `event_log`. Thêm `shoponline return-number repair`: đặt `next_seq = max(doc_seq) + 1` của năm, dùng sau khi khôi phục bản sao lưu cũ (bộ đếm có thể lùi về dưới số đã in).
7. Migration `0012` ghi chú trong chính file và trong `docs/deployment-guide.md` (phase 6): **không `downgrade` trên máy chạy thật** sau khi đã có phiếu (giống ghi chú của `0009`), vì xóa `sales_return` và `document_counter` làm số đã in bị cấp lại.

## Verification

- `uv run alembic upgrade head` rồi `downgrade -1` rồi `upgrade head` trên database test.
- `uv run pytest tests/importers/test_zrsd003.py tests/returns/test_numbering.py`
- Test numbering: chưa cấu hình thì lỗi; `start 80` → `080/11.2026 …`, rồi `081`; gọi `start` lần hai bị từ chối; sang năm 2027 về `001`; hai phiên song song (hai connection) không nhận trùng số, **kể cả khi cả hai cùng là lần cấp số đầu tiên của năm mới**; `issued_on` lấy theo giờ Việt Nam (00:30 ngày 1/12 giờ VN ra tháng `12`); `repair` đưa bộ đếm về `max + 1`.
- Test song song cần fixture riêng commit thật (không dùng savepoint của `db`) và dọn `sales_return_line`, `sales_return`, `document_counter` trước danh sách xóa trong `tests/accounting/conftest.py`, nếu không sẽ làm hỏng test khác (khóa ngoại tới `generated_file`, `sales_order`).
- Test zrsd003: file có hai cột tiền lưu đúng 111111 / 8889; file thiếu hai cột vẫn nhập với `None`; **nhập file có tiền rồi nhập lại file thiếu cột thì tiền cũ được giữ**.

## Risk Assessment

- Hóa đơn đã nhập trước đây có tiền `NULL`; phase 5 chặn và cho xếp robot đọc lại tháng đó. Không backfill trong migration.
- `ops` không bị đụng, nên không cần viết migration idempotent theo quy tắc của `ops`.
