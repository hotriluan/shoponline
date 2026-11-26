---
title: "Plan: tra cứu nhanh đơn hàng"
date: 2026-11-26
summary: "Lập plan ô tra cứu toàn cục theo mã đơn, hóa đơn VAT, SO, DO, phiếu trả"
---

# Plan: tra cứu nhanh đơn hàng

## What happened
Người dùng phải mở từng lô ở /batches mới tìm được một đơn. Đã brainstorm và chốt hướng A: một ô tra cứu toàn cục, khớp chính xác thì chuyển thẳng tới /orders/{id}.

## Decision
- Phạm vi gồm mã đơn sàn, số hóa đơn VAT (tax_invoice_doc, không phải billing_doc), SO, DO và số phiếu trả hàng.
- Hóa đơn VAT so bằng ltrim(..., '0'), giống code kế toán đã làm.
- Số phiếu trả có khoảng trắng bên trong, nên so sau khi bỏ khoảng trắng ở cả hai phía và khớp theo phần đầu.
- Kết quả khớp một phần luôn hiện dạng danh sách, không tự chuyển trang.

## Next steps
Plan: plans/261126-0504-quick-order-lookup. Phase 1 là migration 0020 thêm index (sao lưu DB trước), phase 2 là GET /search kèm test, phase 3 là ô tìm trong base.html, phím / và docs.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
