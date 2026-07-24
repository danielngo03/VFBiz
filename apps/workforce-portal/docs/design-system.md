---
id: workforce-portal-design-system
title: Design system Workforce Portal
status: active
owner_role: design-lead
scope: workforce-portal
when_to_read:
  - design-system
  - accessibility
context_anchors:
  design-system: "## Token"
  accessibility: "## Chất lượng"
tags:
  - design
  - workforce
  - accessibility
revision: 1
review_date: 2026-08-24
supersedes: []
---

# Design system của Workforce Portal

## Phạm vi

Đây là design foundation cục bộ cho một consumer. Chưa tạo shared package cho
đến khi có consumer thứ hai và ownership rõ ràng.

## Token

Token semantic nằm trong `src/styles/globals.css`:

- Canvas, surface, text, muted text, border.
- Brand, focus và danger.
- Spacing, radius, shadow và content width.

Component không dùng raw color cho trạng thái nghiệp vụ. Dark mode chỉ được
thêm khi toàn bộ component và data visualization đạt contrast test; không bật
một theme chưa kiểm chứng.

## Component convention

- Ưu tiên HTML semantic.
- Radix Primitive chỉ dùng cho interaction phức tạp như dialog, menu, select
  hoặc tooltip.
- Server-render component mặc định; chỉ thêm `"use client"` vào leaf component
  cần state/browser API.
- TanStack Table dành cho dataset lớn; sorting/filtering nhạy cảm phải thực thi
  lại ở API.
- React Hook Form và Zod chỉ quản lý UX validation; API vẫn validate độc lập.
- Component không nhận access token và không đọc browser storage.

## Bố cục

- Shell có header, capability-aware navigation và vùng nội dung.
- Trang danh sách có title, mô tả, filter, table và trạng thái empty/error.
- Trang thay đổi quyền luôn có diff preview, reason và impact warning.
- Audit là read-only; export là action riêng có capability riêng.

## Chất lượng

- WCAG AA cho text, focus và trạng thái.
- `prefers-reduced-motion` được tôn trọng.
- Mobile vẫn usable, nhưng ưu tiên desktop workforce workflow.
- Snapshot không thay accessibility/interaction test.
- Không đưa dữ liệu khách hàng thật vào fixture hoặc screenshot.

Skeleton phải giữ gần đúng số cột, chiều cao và mật độ của nội dung thật để
tránh layout shift. Primitive `Skeleton` chỉ vẽ khối; tên trạng thái dành cho
screen reader nằm ở feature-owned panel skeleton. Không lặp một `loading.tsx`
text-only cho từng route.
