---
title: "Tải tất cả đơn theo khoảng ngày đặt hàng, mọi trạng thái, cả đã và chưa xác nhận"
description: "Thêm nút Tải tất cả đơn ở trang File Shop Online: chọn từ ngày đến ngày đặt hàng, file cùng bố cục file nháp (20 cột lịch sử cộng cột 21 Trạng thái), chứa mọi đơn ở mọi trạng thái, không chặn đơn thiếu dữ liệu, không lưu, không xác nhận được."
status: completed
priority: P2
effort: 4h
branch: main
tags: [feature, backend, web]
blockedBy: []
blocks: []
created: 2026-11-25
---

# Tải tất cả đơn theo khoảng ngày

## Overview

File nháp chỉ lấy đơn DELIVERED chưa xác nhận dán, nên đơn đã xác nhận (ví dụ 18 đơn TikTok có tiền vô, xác nhận lúc 09:07 ngày 25/11/2026) và đơn ở trạng thái khác không bao giờ xuất hiện lại. Người dùng không có cách nào xem một khoảng ngày đầy đủ để đối chiếu với file Excel kế toán. Kế hoạch này thêm một file chỉ để đối chiếu: mọi đơn có ngày đặt trong khoảng đã chọn, cùng bố cục file nháp.

Nguồn quyết định: brainstorm phiên 2026-11-25. Chủ dự án chọn lọc theo ngày đặt hàng, dạng file giống file nháp, một dòng mỗi sản phẩm với tiền vô ở dòng đầu, khoảng ngày không giới hạn.

## Hợp đồng

- **Kết quả:** trang File Shop Online có form **Từ ngày** / **Đến ngày** và nút **Tải tất cả đơn**. File `.xlsx` gồm mọi đơn có `ordered_at` từ 00:00 của từ ngày đến hết đến ngày (hai đầu đều tính), ở mọi trạng thái, đã hoặc chưa xác nhận dán. Bố cục: 20 cột file lịch sử, cột 21 `Trạng thái`. Sheet tên `TẤT CẢ ĐƠN - KHÔNG DÁN`.
- **Cột 21 `Trạng thái`:** các phần nối bằng `"; "`, theo thứ tự:
  1. nhãn trạng thái đơn (`states.LABELS`: Mới, Sẵn sàng, Đã có SO, Đã có DO, Thiếu ánh xạ, Cần kiểm tra, Đã hủy);
  2. `Chờ hóa đơn` và/hoặc `Chờ tiền vô`, chỉ với đơn Đã có DO, theo cùng điều kiện như file nháp;
  3. `Đã xác nhận dán` hoặc `Chưa xác nhận`.

  Chỉ ghi ở dòng đầu của mỗi đơn.
- **Ràng buộc:**
  - Chỉ đọc: không `GeneratedFile`, không `SalesHistoryFileOrder`, không `SalesHistoryExported`, không file trên đĩa, không `commit`.
  - Dữ liệu thiếu thì để trống hoặc dùng dữ liệu của sàn, không chặn đơn: tên khách và tỉnh trống; thiếu mã vật tư hoặc tên báo cáo thì `itemName` lấy `sap_name` rồi `product_name`, `variation` lấy `variation_name`, `size` trống.
  - Tiền vô và Tax Invoice Doc. lấy từ cùng nguồn và cùng cách tính như `collect_rows`; tiền vô hiện cho mọi trạng thái nếu có dòng quyết toán (kể cả đơn đã hủy).
  - Cùng quyền với file nháp (`current_user`, tài khoản xem cũng tải được).
  - File chính, file nháp và luồng xác nhận giữ nguyên hành vi và 20/21 cột. Không migration.
- **Ngoài phạm vi:** lọc theo sàn hoặc trạng thái; bảng đối soát riêng; giới hạn khoảng ngày; lưu lịch sử lần tải; tự động hủy xác nhận.

## Phases

| # | Phase | Trạng thái | Phụ thuộc |
|---|---|---|---|
| 1 | [Thu thập dòng, route, form và test](phase-01-collect-route-ui.md) | completed | — |
| 2 | [Tài liệu](phase-02-docs.md) | completed | 1 |

## Tiêu chí hoàn thành

1. Có sáu đơn trong khoảng: đã xác nhận có tiền vô; chưa xác nhận đủ; chờ hóa đơn; Sẵn sàng (chưa DO, thiếu mã vật tư); Đã hủy; thiếu tên khách. Cộng một đơn ngoài khoảng. File có đúng sáu đơn, không có đơn ngoài khoảng, và cột 21 đúng với từng đơn.
2. Đơn đã xác nhận hiện đủ `Tiền Vô` và `Tax Invoice Doc.`, cột 21 ghi `Đã xác nhận dán`. Đơn chưa xác nhận ghi `Chưa xác nhận`.
3. Đơn nhiều sản phẩm có một dòng mỗi sản phẩm, `Tiền Vô` và `Trạng thái` chỉ ở dòng đầu.
4. Đơn đặt lúc 23:59 của đến ngày có trong file; đơn đặt lúc 00:00 ngày sau không có. Từ ngày bằng đến ngày cho ra đúng một ngày.
5. Sau khi tải: số dòng `generated_file`, `sales_history_file_order`, `sales_history_exported` không đổi, và thư mục file sinh ra không có file mới. Tải file chính và file nháp sau đó ra đúng như trước.
6. Từ ngày sau đến ngày, thiếu một trong hai ngày, hoặc ngày sai định dạng: không tải, báo lỗi rõ, quay lại trang. Khoảng không có đơn nào: báo `Không có đơn nào trong khoảng này.`
7. Tên file giải mã ra `TẤT CẢ ĐƠN SHOP ONLINE ddmmyy-ddmmyy.xlsx`. Tài khoản xem tải được.
8. `uv run pytest` và `uv run ruff check` thoát mã 0.

## Rủi ro chính

- **Dán nhầm vào file lịch sử:** sheet khác `sheet1`, tên file khác, có cột 21, và dòng chữ trên trang. Không có nút xác nhận.
- **Làm lệch file chính và file nháp:** ba file dùng chung tra cứu (khách, tên báo cáo, hóa đơn, tiền vô). Phase 1 tách phần tra cứu thành hàm dùng chung và giữ nguyên test hiện có chạy qua không sửa.
- **Khoảng ngày rất dài tải nhiều đơn vào bộ nhớ:** khoảng không giới hạn theo quyết định của chủ dự án. Dữ liệu hiện có vài trăm đơn mỗi tháng, đủ nhỏ; không thêm phân trang. Xem lại nếu số đơn tăng nhiều chục lần.
- **Tên khách đã bị xóa theo thời hạn lưu 90 ngày:** đơn cũ có tên khách và tỉnh trống. Đây là hành vi mong muốn (file chỉ để đối chiếu), ghi trong tài liệu.
