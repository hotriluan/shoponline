---
title: Lên plan xuất dòng nối tiếp file Shop Online
date: 2026-11-16
summary: Plan 5 phase để xuất đơn đã có DO ra đúng 17 cột của file Shop Online 2022-2026
---

# Lên plan xuất dòng nối tiếp file Shop Online

## What happened
Đọc file `docs/Shop Online 2022-2026_10.xlsx` (sheet1, 17 cột, 3.010 dòng tới 10/2026) và so với database production trên máy 192.168.18.123 (đọc qua SSH, chỉ đọc). Production có 74 đơn từ 11–16/11/2026, trong đó 24 đơn "Đã có DO". Không có dòng nào trùng với file, nên chỉ xuất được phần nối tiếp.

## Decision
Chủ dự án chốt: unitPrice = đơn giá trong database; Customer paid = (đơn giá − trợ giá) × số lượng; chỉ đơn DELIVERED; SHOPEE là Shopee Bình Dương; thiếu tên khách thì chặn xuất. billingCity tách tự động từ địa chỉ (mọi địa chỉ trên production kết thúc bằng ", <tỉnh>, Việt Nam"). itemName, kích cỡ, variation đi qua ánh xạ SAP tới một bảng tên báo cáo mới theo mã vật tư (75 mã), thay vì thêm cột vào 597 dòng sku_mapping.

Plan: `plans/261116-1354-shop-online-history-export/plan.md`, 5 phase: bảng tên báo cáo và tách tỉnh/thành, trang sửa tên báo cáo, bộ dựng file, trang xuất, tài liệu và chạy thử production.

## Next steps
`/ak-cook plans/261116-1354-shop-online-history-export/plan.md`. Rủi ro cần kiểm khi chạy thử: danh sách 34 tỉnh/thành khớp cách sàn ghi, và gợi ý tên báo cáo cho tên sản phẩm kiểu Shopee.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
