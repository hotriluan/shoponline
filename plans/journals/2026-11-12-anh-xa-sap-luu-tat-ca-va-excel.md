---
title: "Ánh xạ SAP: lưu tất cả một lần và vòng Excel cho tên còn thiếu"
date: 2026-11-12
summary: Mỗi dòng thiếu ánh xạ từng là một form riêng nên bấm Lưu một dòng làm mất dữ liệu đã gõ ở các dòng khác; nay một form, một nút Lưu tất cả, kèm file Excel tải ra để điền rồi nhập lại
---

# Ánh xạ SAP: lưu tất cả và Excel

## Lỗi
- Bảng "Sản phẩm chưa có ánh xạ" đặt mỗi dòng trong một `<form>` riêng. Bấm Lưu chỉ gửi dòng đó, trang chuyển hướng tải lại, các giá trị đã gõ ở dòng khác mất.

## Đã sửa
- Cả bảng là một form gửi tới `POST /sku-mappings/bulk`, một nút **Lưu tất cả**. Dòng trống cả Mã SAP và Tên SAP bị bỏ qua.
- Lưu theo kiểu tất cả hoặc không: có dòng sai thì không lưu gì, trang hiện lại với mọi giá trị đã gõ và lỗi ghi cạnh từng dòng sai. Cách này giống hệt luật nhập file ánh xạ.
- `GET /sku-mappings/unmapped.xlsx` tải danh sách còn thiếu theo đúng bố cục file nhập (cột Mã SAP định dạng chữ để Excel không làm mất số 0 ở đầu).
- Khi nhập file ánh xạ, các dòng trống cả Mã SAP và Tên SAP được bỏ qua, không còn làm hỏng cả file. Nhờ vậy file tải ra chỉ cần điền một phần.
- Form sửa từng dòng `POST /sku-mappings` vẫn giữ nguyên.

## Kiểm chứng
- Ba test web mới: lưu nhiều dòng, dòng sai thì không lưu gì và giữ giá trị đã gõ, vòng tải Excel rồi nhập lại. Toàn bộ 119 test đều đạt.
