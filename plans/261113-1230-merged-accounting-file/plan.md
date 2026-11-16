---
title: "Gộp 3 sàn thành một file gửi kế toán, có sổ DO đã gửi"
description: "Một đợt xuất đọc zrsd004 cho từng sàn và từng ngày goods issue, gộp thành một file SHOP ONLINE, loại DO đã chốt, đối chiếu để không sót đơn."
status: pending
priority: P1
effort: 4d
branch: main
tags: [feature, web, robot, accounting]
blockedBy: []
blocks: []
created: 2026-11-13
---

# Gộp 3 sàn thành một file gửi kế toán, có sổ DO đã gửi

## Overview

Đường nhập tay hiện đã ra một file chứa cả 3 sàn vì admin chạy `zrsd004` một lần cho 3 khách hàng. Đường robot đọc riêng từng sàn ([report_requests.py:35](../../src/shoponline/sapjobs/report_requests.py)) nên ra 3 file cùng tên `SHOP ONLINE ddmmyy.xlsx`, mỗi file một sàn. Màn hình SAP chỉ có một ô Sold-to và một ô ngày ([sap_screens.yaml](../../config/sap_screens.yaml)), nên không gộp được ngay từ SAP.

Kế hoạch này gộp ở tầng web và thêm sổ ghi nhận từng DO đã gửi kế toán. Sổ theo DO giải quyết ba việc: không gửi lặp DO đã chốt, không mất đơn khi một sàn đọc lỗi, và cho phép đối chiếu đơn đáng ra phải có với DO trong file.

## Hợp đồng

- **Kết quả:** mỗi lần chốt gửi kế toán là đúng một file `SHOP ONLINE ddmmyy.xlsx` chứa DO của mọi sàn và mọi ngày goods issue còn chưa gửi. DO đã chốt không bao giờ gửi lại. Mỗi đơn có SO mà chưa thấy DO được liệt kê rõ và phải được xác nhận trước khi chốt.
- **Ràng buộc:**
  - Giữ nguyên mọi cột và mọi ô của `zrsd004` cộng ba cột chèn (mã đơn, tên khách, địa chỉ).
  - Robot vẫn chỉ đọc SAP; `guard.py` không đổi và không ghi hình lại SAP.
  - Đường tải `zrsd004` lên tay vẫn dùng được, đi qua cùng bộ dựng file và cùng sổ.
  - Có migration: sao lưu database trước khi chạy.
  - Chỉ admin được bắt đầu, đọc lại, tải lên, chốt, hủy. Viewer được xem và tải file đã chốt.
- **Ngoài phạm vi:** tự gửi email cho kế toán, xử lý DO bị hủy sau khi đã chốt (vẫn báo kế toán bằng tay), ghi vào SAP.
- **Tiêu chí hoàn thành:** xem mục cuối.

## Quyết định đã chốt (2026-11-13, chủ dự án)

1. Phương án A: gộp ở web, không đổi robot đọc SAP.
2. Một sàn đọc chưa xong hoặc lỗi phải có cách xử lý rõ ràng, không im lặng xuất file thiếu.
3. Nhiều ngày goods issue gộp chung một file; đơn đã chốt gửi kế toán thì không gửi nữa.
4. Sàn không có đơn hôm đó thì vẫn xuất file bình thường với các sàn còn lại.
5. DO của đơn đang ở "Đã có DO" tại thời điểm triển khai được đưa vào sổ như đã gửi. DO nào chưa thật sự gửi thì gỡ khỏi sổ lúc triển khai.
6. Có nút Hủy đợt, nút Tải bản nháp (tiền tố `NHÁP`, không ghi sổ), và bỏ mọi đường tải file kế toán theo từng sàn ở trang Robot SAP và Báo cáo SAP.
7. Có lệnh CLI `accounting-run revoke <run_id>` cho admin gỡ cả một đợt đã chốt (có xác nhận, ghi nhật ký sự kiện), để chốt nhầm không phải sửa bằng SQL.
8. **Quy tắc đọc:** mỗi sàn còn đơn chờ được đọc từng ngày, từ ngày goods issue cũ nhất của đơn chờ đến hôm nay, và luôn đọc cả hôm nay.
9. **Sổ nền có thêm mốc ngày:** mọi DO có ngày goods issue thực ≤ mốc coi như đã gửi. Mốc mặc định là ngày chạy migration và đổi được bằng CLI.
10. Áp dụng toàn bộ 18 phát hiện của red-team (mục cuối).

## Mặc định do kiến trúc sư chọn (đổi được khi duyệt)

- **Sổ theo số Delivery**, không gắn cờ lên đơn: DO của SO tạo tay không có đơn trên web vẫn được ghi nhận.
- **Chỉ một đợt mở tại một thời điểm.** Bấm xuất khi đã có đợt mở thì mở lại đợt đó, không tạo đợt song song.
- **Mỗi đợt xếp việc robot mới.** Chỉ nhận vào đợt việc đang `PENDING` hoặc `RUNNING` có cùng hệ thống đích; việc `UNKNOWN`, `NEED_REVIEW` hoặc nhắm hệ thống khác được đóng lại và xếp việc mới.
- **Cửa sổ đọc tối đa 31 ngày lùi.** Đơn chờ cũ hơn được cảnh báo trên trang đợt và đọc bằng form "Ra lệnh cho robot".
- **Chỉ giữ dòng hợp lệ:** dòng có Sold-to thuộc một sàn đã cấu hình, `Actual GI Date` có giá trị và ≤ hôm nay, `Total Movement Goods Stat` là `C`, ngày > mốc. Dòng bị bỏ được đếm và nêu lý do trên trang đợt; dòng chưa có `Actual GI Date` hoặc chưa `C` giữ cặp tương ứng ở trạng thái chờ.
- **Đọc ra "No data to display" cho `zrsd004` là kết quả hợp lệ** ("SAP chưa có DO"), nhưng trung tính với bộ đếm lỗi liên tiếp: không tăng, không xóa. Cặp "No data" mà vẫn còn đơn chờ phải được xác nhận khi chốt.
- **Hai cổng khi chốt:** còn cặp chưa đọc xong thì cần tích "chốt thiếu sàn" (nêu tên cặp); còn đơn có SO mà không có DO trong file thì cần tích "đã xem danh sách đơn chưa có DO". Cả hai ghi vào nhật ký sự kiện.
- **Chốt gắn với đúng bản đã xem:** trang đợt và bản nháp mang dấu vân tay (nguồn, DO bị loại, cặp thiếu); chốt từ chối nếu dấu vân tay đã đổi.
- **Bản nháp** được tạo trong bộ nhớ và gửi thẳng, không lưu đĩa, không ghi sổ.
- **Tải lại file đã chốt** trả đúng file đã lưu, không dựng lại. File đã chốt và file nguồn của đợt đang mở không bị retention xóa.
- **Gỡ chốt** đưa các cặp của đợt đó trở lại danh sách cần đọc cho tới khi một đợt chốt sau chứa chúng.
- **Ngày "hôm nay"** dùng một hàm chung theo múi giờ `Asia/Saigon`.

## Luồng

```
Admin bấm "Xuất file gửi kế toán" (trang lô hoặc trang Gửi kế toán)
        ▼
Đợt mở? ── có ──► mở lại đợt đó (bổ sung cặp mới nếu có)
        │ chưa
        ▼
Tính cặp (sàn, ngày): từ ngày GI cũ nhất của đơn chờ đến hôm nay ──► xếp việc read_zrsd004
        ▼
Robot đọc ──► nhập file, đơn có DO chuyển "Đã có DO"; không có dữ liệu = "SAP chưa có DO"
        ▼
Trang đợt: tiến độ từng cặp ─► (hết việc chờ) đối chiếu, bản nháp, dòng bị bỏ
   lỗi ─► Đọc lại hoặc tải zrsd004 lên đợt
        ▼
Chốt: xác nhận cặp thiếu và đơn chưa có DO nếu có, kiểm dấu vân tay
        ▼
Một giao dịch: lưu file, ghi DO vào sổ, đóng đợt, ghi nhật ký sự kiện
```

## Phases

| # | Phase | Trạng thái | Phụ thuộc |
|---|---|---|---|
| 1 | [Sổ DO, đợt xuất, retention và lưu file](phase-01-ledger-and-runs.md) | pending | — |
| 2 | [Dựng file gộp nhiều nguồn](phase-02-merged-workbook.md) | pending | — |
| 3 | [Robot: không có dữ liệu là kết quả hợp lệ](phase-03-robot-no-data-result.md) | pending | — |
| 4 | [Dịch vụ đợt xuất, đối chiếu và chốt](phase-04-run-service.md) | pending | 1, 2, 3 |
| 5 | [Giao diện web](phase-05-web-ui.md) | pending | 4 |
| 6 | [Tài liệu và chạy thử Production](phase-06-docs-and-live-check.md) | pending | 5 |

Phase 1, 2 và 3 sửa các file khác nhau (phase 2 giữ nguyên `build_accounting_workbook`, nên không đụng `report_ingest.py` hay worker) và làm song song được.

## Tiêu chí hoàn thành

1. Dòng tổng đúng quy tắc của SAP: mỗi cột số lượng cộng theo cột đơn vị của chính nó, số dòng tổng bằng số đơn vị khác nhau lớn nhất ở một cột. Kiểm trên dữ liệu bịa với 1 đơn vị (ra 1 dòng tổng) và 2 đơn vị (ra 2 dòng, tổng cân, không sai số dấu phẩy động).
2. Một nguồn không loại gì thì kết quả giữ đúng các dòng tổng gốc của SAP như hiện nay; test cũ của `build_accounting_workbook` qua nguyên vẹn.
3. Chốt một đợt rồi bắt đầu đợt mới: file mới không chứa DO nào đã chốt hay có ngày ≤ mốc; không còn DO mới thì báo "Không có DO mới" và không tạo file.
4. Một việc đọc lỗi: không chốt được nếu chưa xác nhận thiếu sàn; có thể Đọc lại hoặc tải file tay; chốt thiếu sàn rồi thì DO của sàn đó có trong file ở đợt sau.
5. Đơn có SO mà không có DO trong file hiện ở khung "Chưa thấy DO", chốt cần xác nhận khung đó, và danh sách ghi vào nhật ký sự kiện.
6. Ngày goods issue thực lệch ngày dự kiến của lô vẫn đọc được DO (cửa sổ từng ngày đến hôm nay).
7. Hai sàn có đơn, một sàn không: đợt chỉ xếp việc cho hai sàn và chốt bình thường.
8. `zrsd004` không có dữ liệu cho một cặp: việc `DONE`, bộ đếm lỗi liên tiếp không đổi.
9. File tải lên chứa khách hàng khác hoặc DO chưa goods issue: các dòng đó không vào file và không vào sổ, trang đợt đếm số dòng bị bỏ.
10. Hai người chốt hoặc bắt đầu đợt cùng lúc: chỉ một lần thành công, người kia nhận đợt đã mở, sổ không có DO ghi hai lần (kiểm bằng hai kết nối thật).
11. Dữ liệu đổi giữa lúc xem bản nháp và lúc bấm chốt (việc robot xong thêm, file mới gắn vào): chốt từ chối và báo xem lại.
12. Viewer thao tác bắt đầu, đọc lại, tải lên, chốt, hủy: không có dòng nào của `accounting_run` hay sổ thay đổi, và được chuyển hướng kèm thông báo từ chối (như mọi route admin khác); xem trang và tải file đã chốt thì được.
13. Retention giữ tên và địa chỉ khách cho tới khi DO của đơn vào sổ, và không xóa file đã chốt hay file nguồn của đợt đang mở.
14. `accounting-run revoke`: bản chạy thử không đổi gì, `--yes` xóa đúng DO của đợt đó khỏi sổ, từ chối đợt không ở `FINALIZED`, các cặp quay lại danh sách cần đọc.
15. `uv run pytest` và `uv run ruff check` thoát mã 0; docs cập nhật; chạy thử đợt thật trên `AEP`/300 cho kết quả khớp file làm tay của kế toán, kể cả hai dòng tổng.

## Rủi ro chính

- **Thứ tự dòng tổng theo đơn vị.** Mẫu hai đơn vị cho `SET` trước `PC`, giả thuyết là thứ tự mã đơn vị nội bộ của SAP (`PC` lưu là `ST`). Phase 2 viết quy tắc với bảng thứ tự đơn vị khai báo một chỗ; phase 6 xác nhận bằng file thứ ba.
- **`P_WADAT` là ngày goods issue thực hay dự kiến.** Quyết định 8 che phần lớn rủi ro, nhưng phase 6 phải xác nhận trên SAP thật để biết cửa sổ có đủ không.
- **Mốc ngày bỏ nhầm DO chưa từng gửi.** DO có ngày ≤ mốc mà chưa gửi sẽ không vào file nào. Phase 6 yêu cầu chủ dự án duyệt mốc và sổ nền trước đợt đầu.
- **DO của SO tạo tay** chỉ được đọc khi sàn đó có đơn đang chờ. Cần đọc riêng thì dùng form "Ra lệnh cho robot".
- **Đổi hành vi worker.** Phase 3 sửa kết quả của việc `read_zrsd004`. Kế hoạch [261113-1142-robot-manual-run-on-demand](../261113-1142-robot-manual-run-on-demand/plan.md) đang ghi rủi ro "đọc ngày không có dữ liệu bị tính là lỗi"; cần sửa ghi chú đó khi phase 3 xong.
- **Đợt không bao giờ chốt.** Đợt mở bị bỏ quên chặn đợt mới; có nút Hủy đợt.

## Red Team Review

### Session — 2026-11-13

**Findings:** 18 sau khi gộp trùng từ 4 reviewer (bảo mật, lỗi và sự cố, giả định, phạm vi), 18 accepted, 0 rejected. Mọi finding có trích dẫn `file:line`.
**Severity breakdown:** 1 Critical, 9 High, 8 Medium.

| # | Finding | Severity | Disposition | Applied To |
|---|---|---|---|---|
| 1 | Quy tắc dòng tổng sai: số dòng tổng đổi theo số đơn vị, mỗi cột cộng theo đơn vị riêng; mẫu một đơn vị chỉ có một dòng; cộng bằng số thực sinh sai số | Critical | Accept | Phase 2 |
| 2 | Test không thể dùng file mẫu thật (gitignore, dữ liệu cá nhân); fixture thiếu cột trọng lượng và đơn vị | High | Accept | Phase 2, 6 |
| 3 | Đổi chữ ký `build_accounting_workbook` làm hỏng `report_ingest.py` và worker; phase 1-3 không song song được | High | Accept | Phase 2 |
| 4 | Nguồn không lọc khách hàng, ngày, trạng thái; file tải lên tự gắn vào đợt đưa DO lạ vào file và sổ | High | Accept | Phase 2, 4, 5 |
| 5 | Retention xóa tên khách theo `DELIVERED` và xóa file đã chốt, file nguồn của đợt | High | Accept | Phase 1, 6 |
| 6 | Cặp đọc theo ngày dự kiến của lô, "No data" lọt qua cổng chốt; DO thứ hai và SO tạo tay không bao giờ được đọc | High | Accept (quyết định 8) | Phase 3, 4 |
| 7 | Sổ nền thiếu DO thứ hai, SO tạo tay, đơn nối SO sau khi tải zrsd004; không có lệnh thêm | High | Accept (quyết định 9) | Phase 1, 6 |
| 8 | Chốt dựng lại file khác bản admin đã xem | High | Accept | Phase 4, 5 |
| 9 | Nhận việc cũ qua `DuplicateJob` bỏ qua hệ thống đích và tuổi việc; "Đọc lại" lặp vô hạn | High | Accept | Phase 4 |
| 10 | Bắt đầu đợt đồng thời gây lỗi 500; cặp thêm sau khi đợt đã mở không được đọc | Medium | Accept | Phase 4 |
| 11 | `save_generated` trả `Path`, đặt tên theo giây, ghi đĩa trước commit; bản nháp có thể ghi đè file đã chốt | Medium | Accept | Phase 1, 4 |
| 12 | Tiêu chí "403" sai, ứng dụng chuyển hướng 303 | Medium | Accept | Plan, Phase 5 |
| 13 | Lệnh gỡ chốt mô tả mâu thuẫn, thiếu test, không khôi phục DO của SO tạo tay | Medium | Accept | Phase 1, 4, 6 |
| 14 | Dòng chưa goods issue (`Actual GI Date` trống hoặc trạng thái khác `C`) vào sổ sớm | Medium | Accept | Phase 2, 4 |
| 15 | Làm mới 10 giây dựng lại toàn bộ workbook với truy vấn theo từng dòng | Medium | Accept | Phase 4, 5 |
| 16 | Phase 5 không nêu các test sẽ vỡ, mâu thuẫn robot tắt, nhãn và import thừa | Medium | Accept | Phase 5, 6 |
| 17 | Test migration và test đồng thời không có harness trong `conftest.py` | Medium | Accept | Phase 1, 4 |
| 18 | "Hôm nay" dùng `date.today()` ở chỗ này, `Asia/Saigon` ở chỗ khác | Medium | Accept | Phase 4 |

### Whole-Plan Consistency Sweep

- Files reread: plan.md và sáu file phase.
- Decision deltas checked: 10 (quyết định 8, 9, 10; chữ ký builder; `REVOKED`; ba lệnh CLI; không tự gắn file; `save_generated`; retention; cổng chốt).
- Reconciled stale references: số lệnh CLI, câu "xử lý bằng SQL" ở phase 6, phạm vi file của phase 1/2/4, tiêu chí 403.
- Unresolved contradictions: 0.

## Validation Log

### Session 1 — 2026-11-13
**Trigger:** `/ak-plan validate` trước khi cook. Plan đã có Red Team Review kèm bằng chứng `file:line`, nên bước kiểm chứng chỉ lấy mẫu thêm.
**Questions asked:** 4

#### Verification Results
- Claims checked: 38
- Verified: 33 | Failed: 4 | Unverified: 1
- Tier: Full (6 phase; lấy mẫu rút gọn vì đã có red-team)
- Failures:
  - Phase 4 và red-team #18 nói có hàm "hôm nay" theo `Asia/Saigon` ở chỗ khác: `src/` không có, chỗ cũ đều dùng `date.today()` ([imports.py:22](../../src/shoponline/web/routes/imports.py), [robot.py:63,124](../../src/shoponline/web/routes/robot.py)).
  - Phase 1 tự mâu thuẫn về nơi đặt logic `revoke` (phase 4 hay `accounting/ledger.py` của phase 1).
  - [cli.py:184](../../src/shoponline/cli.py) in "Giữ lại vì đơn chưa có file gửi kế toán", sẽ sai sau khi retention đổi điều kiện; phase 1 không nhắc.
  - Phase 1/4 cần "database riêng" cho test đồng thời và vòng downgrade/upgrade, nhưng [conftest.py](../../tests/conftest.py) chỉ có một database `*_test`.
- Unverified: nội dung hai file mẫu thật trong `docs/` (gitignore, chỉ kiểm tay ở phase 6).

#### Questions & Answers

1. **[Architecture]** Phase 4 nói dùng hàm "hôm nay" theo Asia/Saigon "nếu đã có", nhưng `src/` không có. Đặt hàm chung ở đâu và ai dùng?
   - Options: Hàm chung, đổi cả 3 chỗ cũ (Recommended) | Hàm chung, chỉ accounting dùng | Bỏ hàm, dùng `date.today()`
   - **Answer:** Hàm chung, đổi cả 3 chỗ cũ
   - **Rationale:** cả ứng dụng dùng một khái niệm "hôm nay"; cửa sổ đọc và việc robot không lệch ngày khi máy chủ không chạy giờ VN.
2. **[Architecture]** Logic `revoke` nằm ở phase 1 (`ledger.py`) hay phase 4 (`runs.py`)?
   - Options: ledger.py, phase 1 (Recommended) | runs.py, phase 4
   - **Answer:** ledger.py, phase 1
   - **Rationale:** phase 1 độc lập và test được CLI ngay; phase 4 chỉ import.
3. **[Scope]** Nút ở trang lô: giữ hay đổi URL `POST /batches/{id}/accounting-file`?
   - Options: Giữ URL, đổi nội dung xử lý (Recommended) | Đổi sang POST /accounting/runs
   - **Answer:** Giữ URL, đổi nội dung xử lý
   - **Rationale:** ít sửa test (`test_robot_web.py`, `test_sap_connection.py`); tiêu chí grep ở phase 5 được nới cho route lô.
4. **[Architecture]** Lấy "database riêng" cho test đồng thời và vòng downgrade/upgrade thế nào?
   - Options: Cùng DB `*_test`, commit thật rồi dọn (Recommended) | Tạo DB tạm theo từng test
   - **Answer:** Cùng DB `*_test`, commit thật rồi dọn
   - **Rationale:** không cần quyền CREATE DATABASE, không dựng lại schema mỗi test.

#### Confirmed Decisions
- `today_vn()` ở `src/shoponline/clock.py`, dùng cho accounting, imports và robot.
- `revoke_run` ở `accounting/ledger.py`; package `accounting/` do phase 1 tạo.
- URL của nút ở trang lô giữ nguyên.
- Test đồng thời dùng chính DB `*_test`, dữ liệu commit thật và dọn cuối test.

#### Action Items
- [x] Sửa phase 1, 4, 5 theo bốn quyết định trên.
- [ ] Phase 6: chủ dự án duyệt mốc ngày. Mặc định "ngày chạy migration" loại cả DO có ngày goods issue = hôm đó mà chưa gửi; xem lại ở bước 2 chạy thử (quyết định 9 giữ nguyên, không đổi).

#### Impact on Phases
- Phase 1: thêm `clock.py`, `accounting/`, `ledger.py`, sửa thông báo `cli.py:184`, đổi cách kiểm vòng downgrade/upgrade.
- Phase 4: bỏ tạo `accounting/__init__.py`, thêm sửa `imports.py` và `robot.py`, đổi mô tả fixture đồng thời.
- Phase 5: giữ URL lô, nới tiêu chí grep.

### Whole-Plan Consistency Sweep
- Files reread: plan.md và sáu file phase (tìm các cụm "database riêng", "hàm của phase 4", "nếu đã có", "accounting-file", "date.today").
- Decision deltas checked: 4 (`today_vn`, nơi đặt `revoke_run`, URL nút lô, harness test).
- Reconciled stale references: 6 (phase 1 yêu cầu và bước 4, phase 1 kiểm tra downgrade, phase 4 bối cảnh và danh sách tệp, phase 5 tiêu chí grep).
- Unresolved contradictions: 0. Red-team #18 ở bảng trên giữ nguyên làm bản ghi lịch sử.
