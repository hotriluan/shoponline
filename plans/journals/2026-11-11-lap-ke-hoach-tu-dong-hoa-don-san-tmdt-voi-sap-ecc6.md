---
title: Lap ke hoach tu dong hoa don san TMDT voi SAP ECC6
date: 2026-11-11
summary: "Đọc docs, chốt hợp đồng brainstorm và tạo kế hoạch 12 phase với 6 cổng nghiệm thu; chưa viết mã."
---

# Lap ke hoach tu dong hoa don san TMDT voi SAP ECC6

## What happened

- Đọc `docs/`: kế hoạch V2, danh sách điều kiện giá (`vk11pdf.pdf`), hai bảng kê đối soát Lazada và TikTok tháng 10/2026. Không mở `docs/passwordapi.txt` vì là bí mật.
- Tạo `plans/261111-0431-ecommerce-sap-automation/` gồm `plan.md` và 12 phase; `ak plan validate` báo hợp lệ.
- Chưa viết mã, chưa khởi tạo git.

## Findings

- Sản lượng thật: 31 hóa đơn Lazada và 44 hóa đơn TikTok trong tháng, tức 3–4 đơn/ngày. Rủi ro chính là sai kế toán, không phải hiệu năng.
- Lazada giữ lại khoảng 29–30% mỗi đơn, TikTok khoảng 18%; tiền về theo tuần.
- `ZPR1 = PriceList IncludeTax`; `ZDI3`–`ZDI8` là các loại discount; `ZMWS = Tax`.
- Hai file bảng kê là mẫu đích và là chuẩn so sánh cho phase đối soát.
- Chưa có bảng kê Shopee.

## Decision

- Giữ topology V2 (Docker + máy Windows robot); mã là một gói Python, topology là cấu hình triển khai.
- Hàng đợi SAP là bảng PostgreSQL với `SKIP LOCKED`; Web UI render phía máy chủ.
- Shadow mode so đề xuất của robot với SO sales admin tạo tay, tìm theo mã đơn sàn; không cần hệ thống SAP test.
- Kéo việc kiểm tra mức đủ dữ liệu đối soát lên phase 2.

## Next steps

- Xử lý `docs/passwordapi.txt` trước lần commit đầu tiên (phase 1).
- Bắt đầu phase 1 và phase 2 song song; đăng ký app ba sàn ngay vì thời gian duyệt nằm ngoài tầm kiểm soát.
- Câu hỏi còn mở cho chủ dự án: có hệ thống SAP test không, máy chủ nào chạy Docker, Shopee có đang bán không.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
