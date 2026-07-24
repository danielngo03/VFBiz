---
id: customer-portal-product
title: Customer Portal
status: active
owner_role: product-owner
scope: cross-system
when_to_read:
  - customer-portal
  - customer-journey
  - customer-bff
  - customer-profile
  - customer-privacy
  - customer-garage
tags:
  - product
  - customer
  - portal
revision: 1
review_date: 2026-08-24
supersedes: []
---

# Customer Portal

## Outcome

Customer Portal là web experience đã xác thực để khách hàng tự quản lý dữ liệu
tài khoản và xe tự khai báo mà không đưa credential hoặc access token vào
browser. Portal phải làm rõ trạng thái thực, xử lý lỗi có thể phục hồi và không
biến dữ liệu khách tự nhập thành dữ liệu đã được doanh nghiệp xác minh.

## Đối tượng và phạm vi

Đối tượng hiện tại là khách hàng có identity trong customer realm. Current
delivery gồm:

- hồ sơ, locale, timezone, market và communication preference;
- trạng thái email/MFA và liên kết tới required action do CIAM sở hữu;
- danh sách session, revoke một session và logout-all;
- consent theo purpose/version/source/time;
- tạo và theo dõi yêu cầu export/delete dữ liệu;
- Customer Garage: xem, thêm model/variant, đổi nickname, đặt primary và xóa
  reference tự khai báo;
- catalog model/variant chỉ để chọn xe trong Garage.

## Nguyên tắc trải nghiệm

- Mỗi màn hình phân biệt loading, empty, success, stale conflict,
  provider-unavailable và permission-denied.
- `unverified`, `verification_pending`, `verified` và `rejected` phải được trình
  bày đúng nghĩa; khách hàng không thể tự đặt `verified`.
- Device label, IP hint và user-agent chỉ hỗ trợ nhận biết session, không được
  mô tả như bằng chứng định danh thiết bị.
- Destructive action cần mô tả hậu quả, confirmation phù hợp và kết quả
  reconciliation nếu provider chưa xác nhận.
- Nội dung và tương tác đạt WCAG AA; keyboard, focus, screen reader và reduced
  motion là acceptance chứ không phải polish sau cùng.

## Acceptance

- Khách hàng hoàn thành được profile, security/session, privacy/DSAR và Garage
  journey trên viewport desktop và mobile web.
- Stale ETag không overwrite dữ liệu; UI hiển thị conflict và cho phép tải lại.
- Logout, logout-all và revoke hiển thị `confirmed`, `pending` hoặc
  `retry_required` đúng với provider reconciliation.
- Không token nào xuất hiện trong storage, HTML, client bundle hoặc log.
- Browser không gọi NestJS bằng bearer token; NestJS vẫn chặn cross-subject
  access dù UI bị sửa.
- Garage không nhận raw VIN và không cho customer tự xác minh ownership.
- Component chính có keyboard/axe evidence; các journey bắt buộc có browser
  evidence trước acceptance.

## Chỉ số

- Tỷ lệ hoàn thành journey và lỗi theo bước.
- Tỷ lệ stale conflict, provider reconciliation pending và retry thành công.
- Tỷ lệ session revoke/logout-all hoàn tất.
- Accessibility violations mức serious/critical bằng 0 trong gate.
- Không có cross-subject access hoặc token exposure trong security suite.

## Non-goals

- Chưa làm trải nghiệm khám phá/mua xe đầy đủ, chatbot, Trip Planner, commerce,
  service booking hoặc mobile.
- Chưa dùng logo, asset hoặc visual language VinFast khi chưa có brand approval.
- Portal không sở hữu credential, business record, authorization decision hoặc
  product catalog; các authority đó nằm ở CIAM và API Platform.
