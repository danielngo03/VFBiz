# VFBiz Workforce Portal

Workforce Portal là cổng làm việc dành cho nhân sự VFBiz: CSKH, vận hành dữ
liệu, kiểm soát phát hành, kiểm toán và quản trị quyền. Ứng dụng dùng Next.js
App Router và đóng vai trò BFF; NestJS vẫn là nơi thực thi authorization và
business policy.

## Trạng thái

Portal đã có OIDC Code + PKCE, encrypted Redis token vault, generated workforce
SDK và capability-aware shell. Các view role, assignment, approval và audit đọc
dữ liệu thật bằng Server Component, validate lại response và fail closed.
Login bắt buộc verified email + MFA; BFF hỗ trợ refresh rotation-safe, xem
security status, danh sách thiết bị và đăng xuất tất cả phiên đã index.
Mutation quản trị chưa được mở cho đến khi idempotency, CSRF/origin check,
expected version và maker-checker E2E có đủ evidence.

## Chạy cục bộ

```bash
npm run dev --workspace @vfbiz/workforce-portal
npm run typecheck --workspace @vfbiz/workforce-portal
npm test --workspace @vfbiz/workforce-portal
npm run test:e2e --workspace @vfbiz/workforce-portal
```

Portal mặc định chạy tại `http://localhost:3002`. Các biến môi trường bắt buộc
được mô tả trong `.env.example`; không commit client secret hoặc token.

Luồng đăng nhập bắt đầu tại:

```text
http://localhost:3002/api/auth/login?returnTo=/authorization
```

Đây là browser redirect endpoint của Next.js BFF, không phải API nhận username
và password. Customer Scalar nằm tại `/reference/customer`; tài liệu Workforce
API nội bộ được xem tại
`http://127.0.0.1:8000/reference/workforce` khi API bật
`VFBIZ_WORKFORCE_API_DOCS_ENABLED=true`.

## Ranh giới

- Keycloak xác thực workforce identity và MFA.
- Next.js giữ opaque browser session và access/refresh token trong server-side
  token vault.
- NestJS trả entitlement và quyết định authorization.
- Customer Support chỉ đọc projection tối thiểu khi có
  `customer-support.customer.read`, MFA, organizational scope và access reason
  được audit; portal không được truy cập trực tiếp bảng customer.
- UI chỉ ẩn/khóa action theo entitlement để cải thiện trải nghiệm.
- Drupal editorial administration vẫn thuộc Drupal.

Đọc [kiến trúc](docs/architecture.md), [authorization UX](docs/authorization-ux.md)
[design system](docs/design-system.md) và [testing](docs/testing.md) khi thay đổi
đúng boundary tương ứng.
