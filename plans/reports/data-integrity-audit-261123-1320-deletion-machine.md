# Rà soát toàn vẹn dữ liệu: dọn file và máy chạy thật

Phạm vi: plan `261116-1520-delete-spent-files` (đầy đủ), `261113-1012-sap-connection-settings-web` và `261116-0944-win10-production-machine-hidden-tasks` (nhẹ: chỉ mất/trùng dữ liệu). Quyết định 2026-11-23 của chủ dự án.

Mọi số đếm là **dev DB, 2026-11-23** (production không mở được). Dev DB có `robot_control.robot_host = AlkanaDuongPC` và `last_seen_at` 2026-11-23 08:56, tức là nó là bản sao dữ liệu của máy chạy thật, nhưng thư mục dữ liệu trên máy dev (`C:\shoponline-data`) dừng ở 2026-11-16 nên **không dùng được để kiểm file có còn trên đĩa** (xem mục "Giới hạn").

Không có file nào bị xóa hay sửa; lệnh `shoponline retention` không được chạy. Test tái hiện nằm ở scratchpad, không commit.

## Trả lời 5 câu hỏi

1. **Retention 90 ngày xóa gì?** Hai việc riêng. (a) Dòng `customer_info` (tên, địa chỉ) có `updated_at` quá hạn, chỉ khi đơn không còn cần: không có `sales_order`, đã hủy, hoặc **vừa** có DO trong `accounting_sent_delivery` **vừa** có dòng `sales_history_exported` ([retention.py:102-108](../../src/shoponline/maintenance/retention.py#L102-L108)). Đơn, dòng hàng, SO, DO không bị xóa. Đơn READY, chưa có DO, chưa gửi kế toán hoặc chưa xác nhận vào file Shop Online đều được giữ; test `tests/maintenance/test_retention.py:160`. Dev: 129 dòng `customer_info`, 0 dòng quá 90 ngày; phân loại: 117 DELIVERED (đã gửi kế toán, chưa xác nhận lịch sử), 10 READY, 2 CANCELLED, 0 không có đơn. Nếu hôm nay là hạn, chỉ 2 đơn hủy bị xóa. (b) File: xem câu 2 và 3. Phần (a) chỉ chạy với `--apply`; `retention.log` trên máy dev ghi chế độ liệt kê.
2. **Nhập lỗi giữa chừng, file gốc có còn?** Web: file mới ghi chỉ bị xóa sau khi rollback (`discard_unused(db, settings, [new_file])`, ví dụ [imports.py:60-62](../../src/shoponline/web/routes/imports.py#L60-L62)), và người dùng còn file gốc của mình; file đã nhập xong bị xóa sau commit ([imports.py:65](../../src/shoponline/web/routes/imports.py#L65)). Robot: việc FAILED giữ thư mục `robot-work/job-N` tới `evidence_keep_days` ([retention.py:267-269](../../src/shoponline/maintenance/retention.py#L267-L269), test `:280`); chỉ bản chép ở `uploads/` bị quét sau 1 giờ. File gốc zrsd001/zrsd003/quyết toán/file sàn **không** được giữ để gỡ một lần nhập sai: đó là quyết định 1 của chủ dự án; dòng `import_batch` còn `sha256` và `file_name` nhưng không đọc lại được. Dev: 9 giá trị `sha256` xuất hiện ở hơn một lô nhập (nhập lại cùng file), nên nhập lại sau khi file bị xóa là đường đang dùng.
3. **Quét đêm có xóa file Shop Online chưa xác nhận?** Không. Quy tắc `unconfirmed` giữ file còn ít nhất một đơn chưa vào `sales_history_exported` ([retention.py:158-166](../../src/shoponline/maintenance/retention.py#L158-L166)); test `:244`. File nháp không lưu trên đĩa ([sales_history.py:259](../../src/shoponline/web/routes/sales_history.py#L259)).
4. **Hai bản chạy cùng lúc, hai máy cùng ghi một DB?** Cùng một máy và một DB: robot dùng khóa tư vấn Postgres ([worker.py:484-495](../../src/shoponline/saprobot/worker.py#L484-L495)) và việc nhận theo `FOR UPDATE SKIP LOCKED` ([queue.py:119](../../src/shoponline/sapjobs/queue.py#L119)); tác vụ robot `IgnoreNew` ([register-tasks.ps1:81](../../scripts/windows/register-tasks.ps1#L81)). Hai máy: mỗi máy có DB riêng nên **không có hai máy ghi một DB**; rủi ro là hai DB phân kỳ. Bằng chứng trên `Alkana_IT`, 2026-11-23: 5 tác vụ `shoponline-*` đều `Disabled`; không dịch vụ runner; không ai nghe cổng 8750; PostgreSQL vẫn chạy, nghe `0.0.0.0:5432`, còn database `shoponline` cũ (9 MB). `robot_control.robot_host` trong DB đã chép là `AlkanaDuongPC`. Máy cũ vì vậy không nhận việc; khóa chỉ có ý nghĩa trong từng DB.
5. **Chuyển máy có đủ `ops` và thư mục dữ liệu?** Ngày 2026-11-16 (cắt máy) schema `ops` chưa có; 21 bảng `public` khớp số dòng. Thư mục dữ liệu chép bằng `robocopy /E /COPY:DAT` ([phase-03](../../plans/261116-0944-win10-production-machine-hidden-tasks/phase-03-cutover-and-docs.md), dòng 36 và 63-65), **không có bước so số file hoặc hash**: UNVERIFIED. Từ 2026-11-23, luồng máy mới của plan sao lưu chép `ops` (`copy_ops_from_bundle`, [restore.py:312](../../src/shoponline/backup/restore.py#L312)) và thư mục dữ liệu trừ `robot-work`, `backup-work`, `logs` ([archive.py:33-41](../../src/shoponline/backup/archive.py#L33-L41)); migration 0010 chuyển `app_user` sang `ops` có xử lý trùng ([0010_backup.py:30-35](../../migrations/versions/0010_backup.py#L30-L35)). Dev: `ops.app_user` 2, `ops.backup_run` 6, `ops.drive_connection` 1, `ops.backup_settings` 1, `ops.system_state` 1.

## Phát hiện (đã phân xử, mỗi dòng có file:dòng)

Ghi chú mức độ: High = mất hoặc trùng dữ liệu nghiệp vụ trong vận hành bình thường; Medium = cần điều kiện; Low = hiếm hoặc dễ phục hồi. Không có phát hiện Critical hoặc High ở phase này.

| # | Phát hiện | Mức | Luồng | Plan gốc | Bằng chứng | Hướng sửa đề xuất | Đề xuất |
|---|-----------|-----|-------|----------|------------|-------------------|---------|
| D1 | Đường dẫn file trong DB là tuyệt đối; quét đêm so với gốc `SHOPONLINE_DATA_DIR` hiện tại. Nếu DB được khôi phục lên máy có thư mục dữ liệu khác (tham số `-DataDir`), quy tắc giữ không khớp file nào và **mọi file quá 1 giờ trong `uploads/`, `exports/` bị xóa**, gồm file kế toán đã chốt. Chưa tái hiện bằng test (xem Giới hạn); suy ra trực tiếp từ mã | Medium (xác suất thấp, hậu quả lớn) | xóa/khôi phục; file kế toán | 261116-1520 | [retention.py:169](../../src/shoponline/maintenance/retention.py#L169), [:226-235](../../src/shoponline/maintenance/retention.py#L226-L235); [uploads.py:48,59,73](../../src/shoponline/web/uploads.py#L48); `src/shoponline/backup/` không có đoạn nào sửa `stored_path` (grep rỗng). Dev: 125/125 dòng `stored_path` nằm dưới `C:\shoponline-data`, nên hiện chưa kích hoạt. Test viết sẵn nhưng chưa chạy được: `test_repro_phase5.py::test_stored_paths_under_another_data_root_get_everything_swept` | Quét từ chối chạy (và ghi cảnh báo) khi có dòng `stored_path` mà không dòng nào nằm dưới gốc hiện tại; hoặc lưu đường dẫn tương đối | `/ak-fix` |
| D2 | File kế toán cũ không thuộc đợt nào (sinh trước khi có đợt, `generated_file.kind = accounting_file` mà không `accounting_run` nào trỏ tới) không có quy tắc giữ, nên lượt quét đầu tiên xóa chúng. Chúng là bản đã gửi kế toán của sổ nền | Medium | file kế toán; xóa | 261116-1520 | [retention.py:155-157](../../src/shoponline/maintenance/retention.py#L155-L157) chỉ giữ file mà đợt trỏ tới. Dev: 7 dòng như vậy (ngày 13/11, id 3, 4, 8, 9, 10, 16, 17); sổ nền có 12 DO, 105 DO thuộc 5 đợt. Test viết sẵn nhưng chưa chạy được: `test_repro_phase5.py::test_legacy_accounting_file_without_a_run_is_swept` | Hỏi chủ dự án có cần giữ; nếu có thì thêm quy tắc giữ theo `kind = accounting_file` (không hạn) hoặc chép ra ngoài trước. Trên production có thể đã bị xóa từ 2026-11-16 23:30: kiểm bằng SQL S2 | chủ dự án quyết; `/ak-fix` nếu giữ |
| D3 | File kế toán đã chốt chỉ nằm trong `exports/`, không tái sinh được. Sao lưu hằng ngày (`db`) không chứa thư mục dữ liệu; chỉ bản `full` hằng tuần (và bản thủ công) chứa. Mất ổ giữa hai bản `full` thì mất tới 6 ngày file đã chốt | Medium | file kế toán; sao lưu | 261116-1520 / 261123-0312 | [schedule.py:15](../../src/shoponline/backup/schedule.py#L15) (`db`, `full`); [archive.py:3-10](../../src/shoponline/backup/archive.py#L3-L10); `docs/operations-runbook.md:116` ("khôi phục từ bản sao lưu thư mục exports, không có thì hỏi kế toán"). Dev: 5 đợt đã chốt, 5 file | Chọn: đưa `exports/` (nhẹ) vào bản `db` hằng ngày; hoặc chấp nhận rủi ro tới 6 ngày và ghi vào docs | chủ dự án quyết |
| D4 | Lệnh quét đêm không đọc `maintenance.json` và tác vụ retention không bị tạm dừng khi khôi phục hoặc deploy. Khôi phục một bản `db` (không đổi thư mục dữ liệu) trả DB về quá khứ, và lượt quét kế tiếp xóa các file mới hơn bản đó mà DB không còn trỏ tới (file kế toán của đợt bị lùi, file lịch sử của đơn bị lùi). Bản `full` an toàn tạo trước khi khôi phục vẫn chứa chúng, nên có đường lấy lại | Medium | khôi phục; xóa | 261116-1520 / 261123-0312 | [cli.py:392-408](../../src/shoponline/cli.py#L392-L408) không kiểm tra; [restore.py:557](../../src/shoponline/backup/restore.py#L557) ghi marker; [restore.py:392-393](../../src/shoponline/backup/restore.py#L392-L393) chỉ đổi thư mục dữ liệu với bản `full`; [update-production.ps1:63-70](../../scripts/windows/update-production.ps1#L63-L70) chỉ tạm dừng `backup`, `restore`. Chưa tái hiện (cần dựng quy trình khôi phục) | `retention` thoát sớm khi `maintenance.active`; ghi vào docs rằng bản `full` an toàn là nơi lấy lại file | `/ak-fix` nhỏ |
| D5 | "Gỡ xác nhận" một file lịch sử sau khi `customer_info` của đơn đã bị xóa (đơn đã xuất, đã gửi kế toán, quá 90 ngày, chạy `--apply`) đưa đơn về chờ xuất; file mới bị chặn mãi vì "Thiếu tên khách" và không còn nguồn để điền lại | Medium (điều kiện hiếm) | file lịch sử; xóa | 261116-1520 / 261116-1354 | [sales_history.py:414-432](../../src/shoponline/web/routes/sales_history.py#L414-L432) không kiểm tra; [retention.py:103-105](../../src/shoponline/maintenance/retention.py#L103-L105) xóa khi `exported`; [sales_history_workbook.py:215-217](../../src/shoponline/exports/sales_history_workbook.py#L215-L217). Chưa tái hiện; dev: 0 `sales_history_exported`, 0 dòng quá hạn | Khi gỡ xác nhận, báo số đơn đã mất tên khách (đếm `customer_info` rỗng); hoặc chặn gỡ xác nhận quá hạn dữ liệu | chấp nhận rủi ro hoặc `/ak-fix` nhỏ |
| D6 | `discard_unused` không có thời gian ân hạn như lượt quét. Hai upload cùng nội dung gần như cùng lúc dùng chung một file (`<sha256>.xlsx`): lượt này nhập xong rồi xóa file khi lượt kia đã ghi/`touch` nhưng chưa commit, lượt kia lỗi "không có file" | Low | nhập file; xóa | 261116-1520 | [retention.py:186-205](../../src/shoponline/maintenance/retention.py#L186-L205) (không dùng `GRACE`, so với `:223`); [uploads.py:49-53](../../src/shoponline/web/uploads.py#L49-L53). Không mất dữ liệu: người dùng tải lại | Chấp nhận rủi ro (hai quản trị cùng tải đúng một file trong vài mili giây) | chấp nhận |
| D7 | `sweep_files` gọi `path.stat()` sau `path.is_file()`; một file biến mất giữa hai lệnh (file đơn hàng bị `BackgroundTask` xóa, lượt 23:30 trùng giờ tải) làm cả lượt quét dừng, bỏ qua `robot-work`, ảnh robot và dòng `retention_files` | Low | xóa | 261116-1520 | [retention.py:229-231](../../src/shoponline/maintenance/retention.py#L229-L231); [batches.py:164](../../src/shoponline/web/routes/batches.py#L164). Lượt sau chạy lại; không mất dữ liệu | Bắt `FileNotFoundError` quanh `stat()` | `/ak-fix` nhỏ |
| D8 | Plan nói sao lưu "mỗi ngày một bản, giữ 14 ngày"; mã hiện giữ 15 bản `db`, 15 bản `app`, `full` theo tuổi (≤ 30 ngày) và `SHOPONLINE_BACKUP_KEEP_DAYS` không còn tác dụng | Low (plan lệch mã) | sao lưu | 261116-1520 | `plan.md:30,46,72` so với [backup/retention.py:19-24](../../src/shoponline/backup/retention.py#L19-L24), `docs/deployment-guide.md:64` | Ghi vào plan rằng quyết định 4 đã được thay bởi plan 261123-0312 | cập nhật plan |
| D9 | Khóa robot là khóa tư vấn gắn với một kết nối giữ mở và không được kiểm tra lại. Nếu kết nối đó rụng (Postgres khởi động lại, mạng), khóa mất mà robot vẫn chạy tiếp; một robot thứ hai khởi động sẽ lấy được khóa và hai robot cùng đọc SAP và ghi một DB | Low | robot; hai bản chạy | 261116-0944 (nhẹ) | [worker.py:484-495](../../src/shoponline/saprobot/worker.py#L484-L495); vòng lặp [worker.py:504-526](../../src/shoponline/saprobot/worker.py#L504-L526) không kiểm tra `lock`. Tác vụ `IgnoreNew` ([register-tasks.ps1:81](../../scripts/windows/register-tasks.ps1#L81)) chặn bản thứ hai cùng máy khi robot còn sống; Postgres khởi động lại cùng lúc với một lần đăng nhập mới mới gây ra | Trong vòng lặp, chạy `SELECT 1` trên kết nối khóa; mất thì thoát | `/ak-fix` nhỏ |
| D10 | Chỉ `system`/`client` đổi mới xóa trạng thái đã kiểm tra. Đổi user SAP không buộc kiểm tra lại, nên robot có thể đọc zrsd001/zrsd004 bằng user kém quyền (SAP trả ít dòng, không báo lỗi) và file kế toán thiếu DO | Low | báo cáo SAP; file kế toán | 261113-1012 (nhẹ) | [sap_settings.py:225-227](../../src/shoponline/sapjobs/sap_settings.py#L225-L227) chỉ reset khi `system`/`client` đổi. Chưa tái hiện (cần SAP thật) | Reset cả khi `sap_user` đổi, hoặc ghi docs rằng đổi user phải bấm Kiểm tra | chấp nhận hoặc `/ak-fix` nhỏ |

## Phát hiện bị bác (để lưu vết)

| # | Giả thuyết | Lý do bác và nguồn kiểm |
|---|------------|-------------------------|
| R1 | Retention xóa tên khách của đơn READY, chưa có DO, chưa gửi kế toán | Điều kiện xóa cần `status` rỗng/hủy hoặc `sent` và `exported` ([retention.py:102-108](../../src/shoponline/maintenance/retention.py#L102-L108)); test `tests/maintenance/test_retention.py:160`; dev: 10 READY được giữ |
| R2 | Quét đêm xóa file Shop Online chưa xác nhận | Quy tắc `unconfirmed` ([retention.py:158-166](../../src/shoponline/maintenance/retention.py#L158-L166)); test `:244` và `tests/web/test_sales_history_routes.py:59-60,178,238` |
| R3 | Thư mục `robot-work` của việc lỗi bị xóa ngay | Giữ tới `evidence_keep_days` ([retention.py:267-269](../../src/shoponline/maintenance/retention.py#L267-L269)); test `:280` |
| R4 | Hai máy cùng ghi một DB sau khi chuyển | Hai DB riêng; máy cũ `Disabled`, không web, không runner (kiểm 2026-11-23). Còn rủi ro phân kỳ nếu ai bật lại tác vụ cũ: ghi ở câu 4, không phải lỗi mã |
| R5 | Mất `ops` khi chuyển máy | Cắt máy 2026-11-16 chưa có `ops`; từ 2026-11-23 do `copy_ops_from_bundle` và migration 0010 lo; test `tests/backup/test_new_machine_restore.py` |

## SQL cần chạy trên production (chỉ đọc; phase 7 sẽ gộp)

Số trong ngoặc là kết quả trên dev DB, 2026-11-23.

```sql
-- S1. Dữ liệu khách có bị xóa nhầm không: phân loại customer_info theo trạng thái xóa được
SELECT so.status, (asd.delivery IS NOT NULL) AS da_gui_ke_toan,
       (she.sales_order_id IS NOT NULL) AS da_vao_lich_su, count(*)
FROM customer_info ci
LEFT JOIN sales_order so ON so.platform = ci.platform AND so.platform_order_id = ci.platform_order_id
LEFT JOIN accounting_sent_delivery asd ON asd.delivery = so.do_number
LEFT JOIN sales_history_exported she ON she.sales_order_id = so.id
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;
-- dev: CANCELLED/f/f 2; DELIVERED/t/f 117; READY/f/f 10

-- S2. File kế toán không thuộc đợt nào (D2)
SELECT count(*) FROM generated_file g
WHERE g.kind = 'accounting_file'
  AND NOT EXISTS (SELECT 1 FROM accounting_run r WHERE r.generated_file_id = g.id);
-- dev: 7

-- S3. Gốc đường dẫn của mọi file được ghi (D1)
SELECT left(stored_path, 18) AS goc, count(*)
FROM (SELECT stored_path FROM generated_file UNION ALL SELECT stored_path FROM import_batch) t
GROUP BY 1;
-- dev: C:\shoponline-data 125

-- S4. Đường dẫn file kế toán của các đợt đã chốt, để đối chiếu bằng lệnh liệt kê chỉ đọc
-- (Test-Path trên máy chạy thật) xem file còn trên đĩa không
SELECT r.id, r.status, g.stored_path
FROM accounting_run r JOIN generated_file g ON g.id = r.generated_file_id ORDER BY r.id;
-- dev: 5 đợt FINALIZED, 5 file; trên đĩa máy dev chỉ còn 1 (đợt 1), vì thư mục dữ liệu dev dừng ở 16/11

-- S5. Lô nhập dùng chung một file đã lưu (xóa file của lô này ảnh hưởng lô kia)
SELECT count(*) FROM (SELECT sha256 FROM import_batch GROUP BY sha256 HAVING count(*) > 1) t;
-- dev: 9

-- S6. Sổ DO: sổ nền và theo đợt
SELECT count(*) FILTER (WHERE run_id IS NULL) AS so_nen,
       count(*) FILTER (WHERE run_id IS NOT NULL) AS theo_dot FROM accounting_sent_delivery;
-- dev: 12 và 105

-- S7. Đơn đã giao nhưng chưa vào lịch sử, và đơn đã giao chưa gửi kế toán (giữ tên khách)
SELECT count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM sales_history_exported e WHERE e.sales_order_id = so.id)) AS chua_lich_su,
       count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM accounting_sent_delivery a WHERE a.delivery = so.do_number)) AS chua_gui_ke_toan
FROM sales_order so WHERE so.status = 'DELIVERED';
-- dev: 117 và 0

-- S8. Robot nào đang sống (hai máy)
SELECT robot_host, last_seen_at, paused, consecutive_failures FROM robot_control;
-- dev: AlkanaDuongPC, 2026-11-23 08:56:24, false, 0
```

Lệnh liệt kê chỉ đọc trên máy chạy thật (không xóa): `Get-ChildItem <SHOPONLINE_DATA_DIR>\exports, <SHOPONLINE_DATA_DIR>\uploads | Measure-Object` và `Get-Content <SHOPONLINE_DATA_DIR>\logs\retention.log -Tail 60` để xem lượt quét đầu tiên đã xóa gì.

## Giới hạn

- Thư mục dữ liệu trên máy dev dừng ở 2026-11-16 (27 file trong `exports/`, 34 trong `uploads/`), trong khi DB có file tới 2026-11-20. Test-Path trên máy dev: file kế toán 8/12 còn, đơn hàng 13/27, nên số "thiếu" trên dev **không phải bằng chứng mất file**. Phải chạy S4 và liệt kê trên máy chạy thật.
- `retention.log` trên máy dev chỉ có hai lượt chế độ liệt kê (2026-11-13, 2026-11-16), trước khi bản quét xóa thật chạy; lượt quét thật đầu tiên trên máy chạy thật chưa đọc được.
- Hai test tái hiện D1 và D2 nằm ở `C:\Users\luanh\AppData\Local\Temp\claude\657bf492868ad14a\d38a5670-5b61-42dd-a5e1-cb21cd4008fc\scratchpad\test_repro_phase5.py` (chạy bằng `PYTHONPATH=c:/dev/shoponline uv run pytest <đường dẫn> --rootdir c:/dev/shoponline`) nhưng **chưa chạy được**: fixture `db_engine` hạ và nâng lại `shoponline_test`, mà các phiên pytest của phase khác đang giữ khóa (`pg_stat_activity` 2026-11-23: nhiều phiên `LOCK TABLE`/`DROP TABLE` chờ nhau hơn 6 phút). D1 và D2 vì vậy là kết luận từ mã; mức Medium nên không bắt buộc tái hiện.
- Không tái hiện D4, D5, D9, D10 (cần quy trình khôi phục, dữ liệu 90 ngày, hoặc SAP thật).
