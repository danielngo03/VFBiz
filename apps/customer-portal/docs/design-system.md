---
id: customer-portal-design-system
title: Design system Customer Portal
status: active
owner_role: design-lead
scope: customer-portal
when_to_read:
  - design-system
  - customer-portal-ui
  - visual-change
context_anchors:
  design-system: "## Nguyên tắc"
  customer-portal-ui: "## Quy tắc component"
  visual-change: "## Gate"
tags:
  - design
  - accessibility
  - nextjs
revision: 2
review_date: 2026-08-24
supersedes: []
---

# Design system Customer Portal

## Nguyên tắc

- Dùng visual language trung tính và nguyên bản cho tới khi Brand/Legal Owner
  phê duyệt asset và trademark.
- Token semantic (`surface`, `text`, `border`, `accent`, `danger`, `focus`) là
  contract; component không hard-code palette theo feature.
- Component primitive có variant rõ, kích thước target tối thiểu và trạng thái
  focus/disabled/loading/error.
- Ưu tiên Server Component; chỉ primitive cần interaction mới dùng client
  boundary.

## Nền tảng

- Tailwind CSS 4 tiêu thụ local CSS token.
- Radix Primitive được dùng cho interaction có keyboard/focus phức tạp, ví dụ
  destructive confirmation; không bọc primitive không có consumer.
- `class-variance-authority`, `clsx` và `tailwind-merge` dùng cho variant và
  class composition, không tạo một `utils` catch-all.
- Form dùng label, description và error được liên kết bằng accessible name;
  màu sắc không phải tín hiệu duy nhất.

## Quy tắc component

- Primitive nằm ở `components/ui`, composition layout ở `components/layout`,
  feedback dùng chung ở `components/feedback`.
- Feature-owned component ở `features/<capability>`; không đẩy lên shared khi
  mới có một consumer.
- Destructive action hiển thị đối tượng bị tác động, hậu quả, pending state và
  kết quả thật từ API.
- Loading không làm layout nhảy. Skeleton dùng semantic token, giữ kích thước
  gần với panel thật, có accessible status và tôn trọng reduced motion.
- Không tạo `loading.tsx` chỉ để hiển thị một câu. Route-level loading chỉ hợp
  lệ khi toàn segment phải chờ; còn lại page shell hiển thị ngay và từng data
  panel có `Suspense` riêng.
- Motion tôn trọng `prefers-reduced-motion`.

## Gate

Design Lead quyết định thay đổi material về journey/token. Agent review chỉ đưa
evidence. Keyboard, focus, contrast, zoom, reduced motion và axe serious/critical
violations là phần của acceptance.
