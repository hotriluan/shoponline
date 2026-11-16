---
title: "Xuất dòng nối tiếp file Shop Online 2022-2026"
description: "Trang web xuất mọi đơn đã có DO mà chưa vào file lịch sử ra đúng 17 cột của file Shop Online, ghi nhận đơn đã dán để không sót và không lặp."
status: in-progress
priority: P2
effort: 2.5d
branch: main
tags: [feature, backend, database, web]
blockedBy: []
blocks: []
created: 2026-11-16
---

# Xuất dòng nối tiếp file Shop Online 2022-2026

## Overview

Kế toán giữ file `Shop Online 2022-2026_10.xlsx` (sheet1, 17 cột, 3.010 dòng tới 10/2026). Hiện admin gõ tay từng dòng. Database production đã có đủ dữ liệu cho mọi cột của các đơn đã có DO, trừ tên báo cáo của sản phẩm (itemName, kích cỡ, variation). Kế hoạch này thêm bảng tên báo cáo theo mã vật tư, hàm tách tỉnh/thành từ địa chỉ, sổ ghi đơn đã vào file lịch sử, bộ dựng file và một trang web để xuất và xác nhận.

Nguồn quyết định: [brainstorm-261116-1319-shop-online-history-export.md](../reports/brainstorm-261116-1319-shop-online-history-export.md).

## Hợp đồng

- **Kết quả:** admin mở trang "File Shop Online", tải về một file có header và 17 cột như sheet1, gồm mọi dòng sản phẩm của các đơn `DELIVERED` chưa được xác nhận đã vào file lịch sử. Admin dán vào cuối file lịch sử rồi bấm "Xác nhận đã dán"; lần xuất sau không có lại các đơn đó. Đơn có DO trễ (đặt cuối tháng, có DO tháng sau) vẫn vào lần xuất kế tiếp.
- **Ràng buộc:**
  - Không đổi các bảng đơn hàng và các file xuất đang có.
  - Một migration (`0007_sales_history`); sao lưu database trước khi chạy trên production (script deploy đã sao lưu trước khi `migrate`).
  - Admin sửa tên báo cáo, xác nhận và gỡ xác nhận; mọi tài khoản đăng nhập (kể cả viewer) được xem trang và tải file.
  - File xuất chứa tên khách (dữ liệu cá nhân): lưu qua `save_generated` như file đơn hàng, chịu retention hiện có.
  - Retention không xóa tên và địa chỉ của đơn `DELIVERED` chưa được xác nhận vào file lịch sử.
- **Ngoài phạm vi:** nạp ngược 3.010 dòng lịch sử; ghi thẳng vào file lịch sử; sellerDiscountTotal, shippingFee, số điện thoại thật; theo dõi đơn trả hàng sau DO; thêm shop Shopee PGT hay Đà Nẵng.

## Quyết định đã chốt (2026-11-16, chủ dự án)

1. `unitPrice` = `sales_order_item.unit_price` (đơn giá của dòng trong đơn).
2. `Customer paid` = `(unit_price − unit_subsidy) × quantity`.
3. Chỉ đơn `DELIVERED` ("Đã có DO"). Không tách đơn trả hàng.
4. SHOPEE là `Shopee Bình Dương`; TIKTOK là `tiktok Bình Dương`; LAZADA là `Lazada Mall`.
5. `billingName` lấy `customer_info.customer_name`; thiếu tên thì chặn xuất, admin bổ sung trước.
6. `billingCity` tách tự động từ địa chỉ, không làm tay.
7. itemName, kích cỡ, variation đi qua ánh xạ SAP (mã vật tư) tới bảng tên báo cáo.
8. Ghi nhận đơn đã vào file lịch sử; mỗi lần xuất lấy mọi đơn đã có DO mà chưa xác nhận (Validation 1).
9. Retention giữ tên khách tới khi đơn đã được xác nhận vào file lịch sử (Validation 1).
10. Viewer được tải file (Validation 1).

## Mặc định do kiến trúc sư chọn (đổi được khi duyệt)

- **Ô "Đến ngày đặt hàng"** (mặc định `today_vn()`): chỉ lấy đơn đặt tới hết ngày đó, để chốt tháng mà không kéo đơn tháng sau vào. Không có ô "từ ngày": đơn chưa xác nhận nào cũng được lấy.
- **Xác nhận theo từng file đã tải.** Mỗi file tải về ghi lại danh sách đơn trong file. "Xác nhận đã dán" ghi các đơn đó là đã vào lịch sử; đơn đã được xác nhận qua file khác thì bỏ qua và báo số lượng. "Gỡ xác nhận" xóa ghi nhận của đúng file đó để xuất lại.
- **Thứ tự dòng:** theo `ordered_at`, rồi mã đơn, rồi `line_no`.
- **Bảng tên báo cáo sửa trên một trang** có lưu hàng loạt (giống trang Ánh xạ SAP), không làm thêm upload/download Excel: chỉ khoảng 75 mã.
- **Gợi ý điền sẵn** khi mã chưa có tên báo cáo: itemName lấy từ tên sản phẩm dạng `Propan - … - <kích cỡ>` bỏ đuôi kích cỡ; kích cỡ lấy phần sau dấu phẩy cuối của tên phân loại; variation là `Màu sắc:` + phần trước dấu phẩy. Gợi ý chỉ hiện trong ô nhập, admin bấm lưu mới ghi.
- **Chặn chứ không đoán:** đơn thiếu tên khách, địa chỉ không tách được tỉnh/thành, hay mã vật tư chưa có tên báo cáo thì không xuất file; trang liệt kê từng đơn kèm link sửa.

## Luồng

```
Admin mở "File Shop Online" (đến ngày đặt hàng = hôm nay)
        ▼
Lấy đơn DELIVERED chưa có trong sổ đã xuất ──► dựng dòng: Division, thời gian, tên, ******,
                                                tỉnh/thành, công thức, tiền, tên báo cáo
        ▼
Có đơn bị chặn? ── có ──► liệt kê lý do + link sửa (Khách hàng, Tên báo cáo), không cho tải
        │ không
        ▼
Tải `SHOP ONLINE LỊCH SỬ ddmmyy.xlsx` (lưu file + danh sách đơn trong file)
        ▼
Admin dán dòng 2 trở đi vào cuối sheet1 ──► bấm "Xác nhận đã dán" cho file đó
        ▼
Đơn vào sổ đã xuất: không xuất lại; retention được phép xóa tên sau thời hạn
```

## Phases

| # | Phase | Trạng thái | Phụ thuộc |
|---|---|---|---|
| 1 | [Bảng mới, tách tỉnh/thành, retention](phase-01-report-names-and-province.md) | completed | — |
| 2 | [Trang sửa tên báo cáo](phase-02-report-names-page.md) | completed | 1 |
| 3 | [Bộ dựng file lịch sử](phase-03-history-workbook.md) | completed | 1 |
| 4 | [Trang xuất file và xác nhận](phase-04-export-page.md) | completed | 2, 3 |
| 5 | [Tài liệu và chạy thử production](phase-05-docs-and-live-check.md) | in-progress (đã deploy, tách tỉnh 62/62; còn admin duyệt tên báo cáo, xuất và xác nhận lần đầu: [biên bản](../reports/live-check-261116-1444-shop-online-history-export.md)) | 4 |

Phase 2 và 3 sửa các file khác nhau và làm song song được sau phase 1. Phase 4 sau phase 2 vì cả hai sửa `app.py` và `base.html`.

## Tiêu chí hoàn thành

1. Lần xuất đầu trên production ra đúng các dòng của mọi đơn `DELIVERED` hiện có (24 đơn tại 2026-11-16; ghi con số thật lúc kiểm), header và thứ tự 17 cột giống hệt dòng 1 của sheet1.
2. `Customer paid` = `(unit_price − unit_subsidy) × quantity`, `unitPrice` = `unit_price`; test có dòng có trợ giá và số lượng > 1.
3. Dán dòng 2 trở đi vào cuối file lịch sử: `Cust + time` và `Transaction` tính đúng theo dòng mới (công thức tương đối).
4. Sau "Xác nhận đã dán", lần xuất sau không chứa các đơn đó; đơn đặt trước ngày của lần xuất trước nhưng có DO sau đó vẫn có trong lần xuất sau. "Gỡ xác nhận" đưa đơn của file đó trở lại.
5. Hai lần xác nhận cho hai file chứa cùng đơn: đơn chỉ được ghi một lần, lần sau báo số đơn bỏ qua.
6. Đơn thiếu tên khách, địa chỉ không ra tỉnh/thành trong danh sách 34, hoặc dòng có mã vật tư chưa có tên báo cáo: không tải được file, trang liệt kê đơn và lý do.
7. Tách tỉnh/thành đúng cho mọi dạng địa chỉ đã thấy trên production: `…, Thành phố Hồ Chí Minh, Việt Nam`, `…, Tỉnh An Giang, Việt Nam`, `…, An Giang, Việt Nam` (Lazada, TikTok không tiền tố), và chữ tiếng Việt ở dạng tổ hợp (NFD).
8. Retention không xóa `customer_info` của đơn `DELIVERED` chưa vào sổ đã xuất, kể cả khi DO đã gửi kế toán; xóa như cũ khi đã có cả hai.
9. Viewer tải được file; viewer gửi lưu tên báo cáo, xác nhận hay gỡ xác nhận thì không dòng nào thay đổi và bị chuyển hướng kèm thông báo từ chối như các route admin khác.
10. `uv run pytest` và `uv run ruff check` thoát mã 0.

## Rủi ro chính

- **Danh sách 34 tỉnh/thành** phải khớp cách sàn ghi sau sáp nhập 2025. Toàn bộ 62 địa chỉ trên production (2026-11-16) có tỉnh/thành nằm trong danh sách; phase 5 kiểm lại trên dữ liệu lúc chạy thử.
- **Gợi ý tên báo cáo sai** (Shopee đặt tên kiểu `V-09 VN-0.8L - …`). Gợi ý chỉ là giá trị điền sẵn; admin duyệt một lần ở phase 5.
- **Quên bấm xác nhận:** đơn sẽ xuất lại ở lần sau (lặp, không sót). Trang hiện file đã tải mà chưa xác nhận để nhắc.
- **Tên khách giữ lâu hơn 90 ngày** cho đơn chưa xuất; ghi rõ trong tài liệu bảo mật.

## Validation Log

### Session 1 — 2026-11-16
**Trigger:** `/ak-plan validate` trước khi cook.
**Questions asked:** 3

#### Verification Results
- Tier: Full (5 phase)
- Claims checked: 32
- Verified: 32 | Failed: 0 | Unverified: 0
- Đã kiểm: `app.py:209-221` nạp router bằng một tuple module; `require_admin` ném `AdminRequired`, handler ở `app.py:199-204` flash và chuyển hướng; `batches.py:118-140` mẫu `save_generated` + `FileResponse`; `save_generated` ở `uploads.py:59` trả `GeneratedFile`; `today_vn` ở `clock.py`; `log_event` ở `states.py:47`; `customers.py` nhận `platform` và `missing`; `sku_mapping.py` có `save_unmapped`; `SalesOrderItem.line_no`, `SalesOrder.ordered_at` (naive); `retention_days` mặc định 90 (`config.py:28`); retention giữ `customer_info` theo `accounting_sent_delivery` (`retention.py:57-81`); fixture web `tests/web/test_web_flow.py:34`; dạng địa chỉ TikTok trên production có cả tỉnh không tiền tố.
- Phát hiện thiết kế (không phải sai dẫn chứng): lọc theo khoảng ngày đặt hàng làm sót đơn có DO trễ; retention 90 ngày có thể xóa tên trước khi xuất; phase 2 và phase 4 cùng sửa `app.py`/`base.html` nên không song song.

#### Questions & Answers

1. **[Architecture]** Kế hoạch đang lọc theo ngày đặt hàng. Một đơn đặt ngày 30/11 nhưng 2/12 mới có DO sẽ bị sót: lúc xuất tháng 11 thì đơn chưa có DO, còn lúc xuất tháng 12 thì đơn nằm ngoài khoảng ngày. Xử lý thế nào?
   - Options: Ghi nhận đơn đã xuất (Recommended) | Giữ lọc theo khoảng ngày | Lọc theo ngày có DO
   - **Answer:** Ghi nhận đơn đã xuất
   - **Rationale:** không sót và không lặp đơn giữa các lần xuất; cần thêm sổ và nút xác nhận.
2. **[Risks]** Tác vụ retention xóa tên và địa chỉ khách sau 90 ngày, kể từ khi DO của đơn đã được gửi kế toán. Nếu admin xuất trễ hơn 90 ngày thì đơn sẽ bị chặn vì thiếu tên. Có cần giữ tên lâu hơn không?
   - Options: Giữ tới khi đã xuất (Recommended) | Giữ 90 ngày như hiện tại
   - **Answer:** Giữ tới khi đã xuất
   - **Rationale:** đơn chưa xuất không bao giờ mất tên; đổi điều kiện trong `retention.py`.
3. **[Scope]** File xuất ra có tên khách và tỉnh/thành. Tài khoản xem (viewer) có được tải file này không?
   - Options: Viewer được tải (Recommended) | Chỉ admin
   - **Answer:** Viewer được tải
   - **Rationale:** giống file đơn hàng hiện nay.

#### Confirmed Decisions
- Sổ đã xuất: hai bảng mới `sales_history_file_order` (đơn trong từng file đã tải) và `sales_history_exported` (đơn đã xác nhận, khóa chính `sales_order_id`).
- Bỏ ô "từ ngày"; giữ ô "đến ngày đặt hàng".
- Retention: xóa `customer_info` của đơn `DELIVERED` chỉ khi DO đã gửi kế toán và đơn đã vào sổ đã xuất.
- Tải file: `current_user`; xác nhận và gỡ xác nhận: `require_admin`.

#### Action Items
- [x] Phase 1: thêm hai bảng sổ, migration đổi tên thành `0007_sales_history`, sửa retention và test.
- [x] Phase 3: lấy đơn chưa xác nhận thay vì khoảng ngày.
- [x] Phase 4: ghi danh sách đơn của file khi tải; nút xác nhận và gỡ xác nhận; phụ thuộc phase 2.
- [x] Phase 5: tài liệu bảo mật về thời hạn giữ tên mới; kiểm luồng xác nhận trên production.

#### Impact on Phases
- Phase 1: thêm bảng sổ và đổi điều kiện retention.
- Phase 3: đổi đầu vào của `collect_rows`.
- Phase 4: thêm route xác nhận, gỡ xác nhận, danh sách file đã tải.
- Phase 5: tài liệu và kịch bản chạy thử.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01, phase-02, phase-03, phase-04, phase-05.
- Decision deltas checked: 5 (sổ đã xuất, bỏ "từ ngày", retention, quyền tải, phụ thuộc phase 4).
- Reconciled stale references: 7 (số địa chỉ production 55 sửa thành 62; tên migration `0007_report_item_name`; `date_from` trong phase 3 và 4; tên file có khoảng ngày; tiêu chí "xuất 11–16/11"; phụ thuộc phase 4; câu "Phase 2 và 3 song song" giữ nguyên, thêm ghi chú phase 4).
- Unresolved contradictions: 0.
