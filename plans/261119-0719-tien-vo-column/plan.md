---
title: "Cột Tiền Vô từ file quyết toán Shopee/TikTok trong file Shop Online 2022-2026"
description: "Upload file quyết toán Shopee và TikTok, lưu tiền vô theo đơn; file lịch sử Shop Online có cột 20 Tiền Vô, đơn Shopee/TikTok chưa có tiền vô chờ ở mục riêng, Lazada để trống."
status: in-progress
priority: P2
effort: 10h
branch: main
tags: [feature, backend, database, web]
blockedBy: []
blocks: []
created: 2026-11-19
---

# Cột Tiền Vô trong file Shop Online 2022-2026

## Overview

Kế toán cần biết sàn đã trả bao nhiêu tiền cho mỗi đơn. Shopee ("Số tiền", theo "Mã đơn hàng") và TikTok ("Tổng số tiền quyết toán", theo "ID đơn hàng liên quan"; "ID đơn hàng/điều chỉnh" là ID giao dịch) có tiền theo đơn trong file export của sàn; Lazada "Balance Transactions" thì không có mã đơn nên để trống. Kế hoạch thêm bảng lưu dòng quyết toán, bộ đọc và form upload cho hai sàn, rồi thêm cột 20 `Tiền Vô` và mục "Đơn chờ tiền vô" vào trang File Shop Online.

Nguồn quyết định: [brainstorm-261119-1409-tien-vo-column.md](../reports/brainstorm-261119-1409-tien-vo-column.md). File mẫu: `docs/tienvo/` (không commit, có mã đơn thật).

## Hợp đồng

- **Kết quả:** người dùng upload file quyết toán Shopee/TikTok ngay trên trang File Shop Online; file tải về có cột 20 `Tiền Vô` sau `Tax Invoice Doc.`.
- **Ràng buộc:** giữ cơ chế tải file với các đơn đã đủ dữ liệu; một migration `0009_platform_settlement`, sao lưu DB trước khi chạy trên production; upload lại file trùng kỳ không cộng trùng; file gốc bị xóa ngay sau khi nhập.
- **Ngoài phạm vi:** đọc Balance Transactions của Lazada; đối soát với ngân hàng hoặc "Customer paid"; tự tải file từ sàn; điền tiền vô cho đơn đã xác nhận dán; nút bỏ qua đơn không bao giờ quyết toán.

## Quyết định đã chốt (2026-11-19, chủ dự án)

1. Đơn Shopee/TikTok chưa có tiền vô không vào file lần này, nằm ở mục riêng "Đơn chờ tiền vô"; file vẫn tải được với các đơn đã có tiền vô.
2. Lazada: cột Tiền Vô để trống, không chờ.
3. Đơn nhiều dòng: tiền vô chỉ ghi ở dòng đầu của đơn.
4. Shopee "Điều chỉnh" (Mã đơn hàng "-"): không tính. Đơn giao không thành công chỉ có "Tiền ra" thì xuất với tổng âm (ví dụ -2.700); chốt lại sau red team.
5. Form upload nằm ở trang File Shop Online (hộp "Đơn chờ tiền vô"), chỉ admin được upload.
6. TikTok dòng loại khác "Đơn hàng": bỏ qua và báo số dòng bỏ qua kèm ID giao dịch và đơn liên quan sau khi upload; chốt lại sau red team (chưa có mẫu điều chỉnh thật để kiểm).
7. Không có ngày bắt đầu: khi bật tính năng mọi đơn Shopee/TikTok đang chờ đều cần tiền vô; phase 3 upload phủ cả phần tồn (chốt sau red team).

## Luồng

```
Sàn Shopee/TikTok ──export──► file quyết toán ──upload ở /sales-history──► read_settlement_file
                                                                              ▼ (nhận sàn theo header)
                                             upsert platform_settlement (một dòng / giao dịch), xóa file gốc
                                                                              ▼
collect_rows: SUM(amount) theo (platform, mã đơn) ──► có thì xuất, cột 20 ở dòng đầu đơn
                                                  └─► Shopee/TikTok chưa có ──► "Đơn chờ tiền vô"
                                                  └─► Lazada ──► cột 20 trống
```

## Phases

| # | Phase | Trạng thái | Phụ thuộc |
|---|---|---|---|
| 1 | [Bảng quyết toán, bộ đọc và nhập](phase-01-settlement-store-and-readers.md) | completed | — |
| 2 | [Cột 20, mục chờ tiền vô và form upload](phase-02-history-column-and-upload.md) | completed | 1 |
| 3 | [Tài liệu và chạy thử production](phase-03-docs-and-live-check.md) | in-progress (tài liệu xong; deploy production chờ chủ dự án) | 2 |

## Tiêu chí hoàn thành

1. Nhập `docs/tienvo/shopee.xlsx`: 177 dòng có mã đơn (174 tiền vào, 3 tiền ra -2.700), bỏ 3 dòng "Điều chỉnh"; nhập `docs/tienvo/tiktok.xlsx`: 115 đơn, 21 đơn bằng 0, 1 đơn âm -2565. Nhập lại cùng file không đổi số dòng hay tổng. Hai giao dịch Shopee giống hệt trong một file được lưu thành hai dòng, không lỗi.
2. `docs/tienvo/lazada.xlsx` và file không đúng mẫu bị từ chối với thông báo rõ, không ghi gì; file gốc không còn trong `uploads/`, kể cả khi nhập gặp lỗi bất ngờ.
3. File tải về có 20 cột, header cột 20 `Tiền Vô`, định dạng `#,##0`; Shopee/TikTok ghi tổng tiền của đơn ở dòng đầu, dòng sau trống; Lazada trống.
4. Đơn Shopee/TikTok chưa có tiền vô không có trong file và hiện ở mục "Đơn chờ tiền vô"; đơn có tiền vô 0 vẫn xuất với 0, tổng âm xuất số âm; đơn thiếu cả thứ khác vẫn ở "Đơn bị chặn" và vẫn được đếm trong số đơn chờ tiền vô.
5. `uv run pytest` và `uv run ruff check` thoát mã 0.
6. `git check-ignore` khớp `docs/tienvo/*.xlsx`.

## Rủi ro chính

- **Đơn cũ đang chờ xuất:** khi bật tính năng, mọi đơn Shopee/TikTok chưa dán đều chờ tiền vô tới khi upload file sàn phủ kỳ của chúng. Phase 3 upload một kỳ rộng trên production.
- **Sàn đổi tên cột:** bộ đọc từ chối file với tên cột thiếu, không đoán.
- **Mã đơn TikTok** chưa đối chiếu với dữ liệu thật; phase 1 đối chiếu với file đơn TikTok có sẵn trong `docs/`, phase 3 đối chiếu với production trước khi deploy, không khớp thì dừng.
- **Tiền vô đổi sau khi xuất** (sàn ghi "Tiền ra" muộn) không được sửa hay báo lại; nằm ngoài phạm vi, ghi ở docs.
- **Đơn không bao giờ quyết toán** nằm mãi ở "Đơn chờ tiền vô" và giữ thông tin khách; nút bỏ qua ngoài phạm vi, ghi ở docs.

## Red Team Review

### Session — 2026-11-19
**Findings:** 15 (14 accepted, 1 rejected)
**Severity breakdown:** 0 Critical, 7 High, 8 Medium
Reviewers: Security Adversary, Assumption Destroyer, Failure Mode Analyst (Standard tier: Fact Checker + Contract Verifier). Các thay đổi trong phase file đánh dấu **[Red team]**.

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | Khóa lặp trong một file làm upsert lỗi 500 và file gốc nằm lại; tiền/độ dài không có giới hạn | High | Accept | Phase 1, 2 |
| 2 | Mã đơn TikTok phải lấy từ `ID đơn hàng liên quan`; dòng điều chỉnh có cột liên kết | High | Accept (quyết định 6 giữ, thêm liệt kê ID) | Phase 1, plan |
| 3 | TikTok có tiền âm -2565, ô trống, định dạng ngày chưa nêu | High | Accept | Phase 1, plan |
| 4 | `.gitignore` không phủ `docs/tienvo/` | High | Accept | Phase 1, plan |
| 5 | Đơn Shopee giao không thành công: âm hoặc chờ mãi | High | Accept (chủ dự án: xuất số âm) | Phase 2, plan |
| 6 | Tiền vô đổi sau khi xuất không được ghi nhận | High | Accept (chỉ ghi rủi ro, ngoài phạm vi) | Phase 2, 3, plan |
| 7 | Bật tính năng trước khi chứng minh mã TikTok khớp | High | Accept (đối chiếu sớm; không thêm ngày bắt đầu) | Phase 1, 3, plan |
| 8 | Nhập sai không gỡ được; `record.platform` trống; đếm "cập nhật" sai nghĩa | Medium | Accept (không thêm nút hoàn tác; ghi cách gỡ) | Phase 1, 3 |
| 9 | Shopee không lọc `Trạng thái` | Medium | Accept | Phase 1 |
| 10 | Tách khỏi `blocked` làm sai câu "Không có đơn nào chờ xuất" (`sales_history.html:15-22`) | Medium | Accept | Phase 2 |
| 11 | Đơn chờ cả hóa đơn và tiền vô không được đếm; thiếu khoảng ngày cần export | Medium | Accept | Phase 2, 3 |
| 12 | Bước sắp xếp của kế toán phải chọn A:T | Medium | Accept | Phase 2, 3 |
| 13 | "Mở workbook một lần" mâu thuẫn với `read_table` | Medium | Accept | Phase 1 |
| 14 | Rollback không downgrade 0009; tài liệu lưu giữ thiếu nội dung file; form cần chặn viewer | Medium | Accept | Phase 2, 3 |
| 15 | Formula injection qua `billing_name` trong workbook builder | Medium | Reject: lỗi có sẵn (`sales_history_workbook.py:229-252`), kế hoạch không thêm chuỗi người dùng; nên sửa riêng | — |

Đã kiểm lại bằng chứng chính: `.gitignore:9-10` không phủ thư mục con (`git check-ignore` không khớp); `report_ingest.py:74` khử trùng bằng dict trước upsert; `sap_reports.py:89` chỉ bắt `UploadRejected`/`FileRejected`; `tiktok.xlsx` có cột 55 `ID đơn hàng liên quan` (bằng ID ở 115/115 dòng) và một dòng `-2565`.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01-settlement-store-and-readers.md, phase-02-history-column-and-upload.md, phase-03-docs-and-live-check.md
- Decision deltas checked: 7 (khóa đơn TikTok, khóa Shopee `#n`, `parse_signed_money` cho cả hai sàn, lọc `Trạng thái`, đếm `unchanged`, kiểm mã TikTok chuyển lên phase 1/trước deploy, tổng âm được xuất)
- Reconciled stale references: 4 (Overview khóa TikTok, tiêu chí 1/2/4, rủi ro mã TikTok, effort)
- Unresolved contradictions: 0

## Validation Log

### Session 1 — 2026-11-19
**Trigger:** `/ak-plan validate` sau red team, trước khi cook.
**Questions asked:** 2

#### Verification Results
- **Tier:** Standard (đã có bằng chứng red team; không còn thẻ `[UNVERIFIED]`, kiểm lại nhanh)
- **Claims checked:** 14
- **Verified:** 14 | **Failed:** 0 | **Unverified:** 0
- Đã kiểm: `migrations/versions/0008_sap_tax_invoice.py` là head; `read_table` có 7 nơi gọi trong `src/`; `parse_money` (`excel_table.py:122`), `save_upload(kind=, platform=)` (`web/uploads.py:24`), `require_admin` (`web/app.py:61`), mẫu `upload_zrsd003` chỉ bắt `UploadRejected`/`FileRejected` (`sap_reports.py:75-99`); `ImportBatch.platform` nullable có `new/updated/unchanged_count` (`db/models.py:48-65`); `MONEY_COLUMNS = ("J","K")`, `Reason`, `collect_rows` (`sales_history_workbook.py:64-136`); `kept_files`/`waiting_uploads` không giữ file kind `settlement` nên `discard_unused` xóa được (`retention.py:131-170`, `runs.py:347-351`); bốn file docs và bốn file test của phase 2 tồn tại; `git check-ignore docs/tienvo/shopee.xlsx` vẫn chưa khớp (bước 0 phase 1 còn cần).
- Đối chiếu mã đơn trên file mẫu: Shopee `Mã đơn hàng` khớp 7/8 mã trong `Order.toship.20261111_20261111.xlsx`; TikTok `ID đơn hàng liên quan` khớp 7/7 mã 18 số trong ba file đơn TikTok ở `docs/`.
- Phát hiện: 21 đơn TikTok tiền vô 0 là đơn hoàn tiền toàn bộ (`Khách thanh toán` = -`Tiền hoàn của khách`); đơn -2565 là hoàn tiền toàn bộ cộng phí xử lý.

#### Questions & Answers

1. **[Assumptions]** 21/115 đơn TikTok quyết toán 0 vì hoàn tiền toàn bộ, một đơn -2.565 (hoàn tiền + phí xử lý). Kế hoạch xuất các đơn này với Tiền Vô 0 hoặc số âm như Shopee giao không thành công. Giữ không?
   - Options: Xuất 0 / số âm (Recommended) | Không đưa đơn hoàn tiền vào file
   - **Answer:** Xuất 0 / số âm
   - **Rationale:** Quyết định liệu đơn hoàn tiền có vào file hay nằm chờ mãi.

2. **[Risk]** Shopee không có mã giao dịch nên khóa gồm số tiền; nếu Shopee export lại cùng giao dịch với số tiền đã sửa thì cộng cả hai. Giữ khóa hay thay bằng xóa-rồi-nhập theo khoảng ngày của file?
   - Options: Giữ khóa, ghi rủi ro (Recommended) | Thay theo khoảng ngày
   - **Answer:** Giữ khóa, ghi rủi ro
   - **Rationale:** Thay theo khoảng ngày xử lý được số sửa nhưng xóa nhầm khi file bị lọc.

#### Confirmed Decisions
- Đơn hoàn tiền toàn bộ: xuất với Tiền Vô 0 hoặc âm, tài liệu giải thích 0 nghĩa là hoàn tiền toàn bộ.
- Khóa dòng Shopee: giữ `mã đơn|Ngày|Loại giao dịch|Số tiền|#n`, rủi ro số tiền sửa được ghi ở docs.

#### Action Items
- [ ] Phase 1 bước 6: ghi kết quả đối chiếu trên file mẫu (7/7) vào journal; vẫn đối chiếu production ở phase 3.
- [ ] Phase 3: `daily-operations.md` nói rõ Tiền Vô 0 là đơn hoàn tiền toàn bộ.

#### Impact on Phases
- Phase 1: bước 6 đã có kết quả sơ bộ trên file mẫu.
- Phase 3: thêm câu giải thích Tiền Vô 0 trong docs.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01-settlement-store-and-readers.md, phase-02-history-column-and-upload.md, phase-03-docs-and-live-check.md
- Decision deltas checked: 2 (đơn hoàn tiền xuất 0/âm; giữ khóa Shopee). Cả hai giữ nguyên kế hoạch, chỉ thêm ghi chú.
- Reconciled stale references: 0 (tiêu chí 4 "đơn có tiền vô 0 vẫn xuất với 0" và phase 2 bước 1 đã khớp)
- Unresolved contradictions: 0
