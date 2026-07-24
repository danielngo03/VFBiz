---
id: customer-portal-experience-accessibility
title: Trải nghiệm và accessibility Customer Portal
status: active
owner_role: design-lead
scope: customer-portal
when_to_read:
  - customer-journey
  - accessibility
  - customer-profile
  - customer-privacy
  - customer-garage
context_anchors:
  customer-journey: "## Journey states"
  accessibility: "## Accessibility acceptance"
  customer-profile: "## Account và privacy"
  customer-privacy: "## Account và privacy"
  customer-garage: "## Garage"
tags:
  - experience
  - accessibility
  - customer
revision: 1
review_date: 2026-08-24
supersedes: []
---

# Trải nghiệm và accessibility Customer Portal

## Journey states

Mỗi page/flow phải có trạng thái hữu ích cho:

- loading và first load;
- empty với next action rõ;
- validation lỗi tại field và summary khi cần;
- stale ETag/conflict, kèm reload thay vì overwrite;
- provider unavailable hoặc reconciliation pending;
- permission/session expired;
- success được xác nhận bởi server.

Không dùng optimistic success cho logout-all, consent, DSAR hoặc Garage mutation
khi server chưa xác nhận.

## Account và privacy

- Profile cho biết field nào do khách hàng sửa và field nào do CIAM/provider
  quản lý.
- Security page không gọi user-agent/IP là identity proof.
- Logout/revoke mô tả phạm vi session và trạng thái provider reconciliation.
- Consent hiển thị purpose, version và effective state; DSAR nêu loại yêu cầu,
  trạng thái và điều kiện không thể xóa do legal hold nếu có.

## Garage

- Model/variant selector chỉ dùng approved catalog.
- Ownership status luôn kèm giải thích; `unverified` không bị trình bày như lỗi.
- Customer không nhập raw VIN trong current flow và không có control tự đặt
  `verified`.
- Invalid variant, stale catalog và provider unavailable có state riêng, không
  tự chọn giá trị thay thế.

## Accessibility acceptance

- Semantic landmark và heading order có nghĩa khi không có CSS.
- Tất cả action dùng được bằng keyboard, có visible focus và accessible name.
- Dialog giữ/khôi phục focus đúng; error được announce bằng live region phù hợp.
- Touch target, contrast và zoom/reflow đáp ứng WCAG AA.
- Component test kiểm accessible behavior; async Server Component journey được
  xác minh bằng browser E2E.
