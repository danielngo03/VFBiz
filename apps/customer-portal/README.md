# Customer Portal

Next.js 16 BFF cho các hành trình khách hàng đã xác thực. Runtime chạy ở
`http://localhost:3001`; NestJS resource API chạy ở `http://127.0.0.1:8000`.

Current scope gồm profile, account security/session, consent/DSAR và
self-reported Customer Garage. Chatbot, Trip Planner, commerce, service booking
và mobile không thuộc workspace delivery hiện tại.

## Ranh giới

- Browser chỉ giữ opaque session ID trong cookie `HttpOnly`, `SameSite=Lax`.
- Access/refresh token được mã hóa AES-256-GCM trong Redis token vault; không
  nằm trong `localStorage`, client bundle, PostgreSQL hoặc log.
- Keycloak sở hữu registration, password recovery, email verification, MFA và
  provider session.
- Portal BFF thực hiện OIDC Authorization Code + PKCE, refresh single-flight,
  CSRF, idle/absolute timeout và back-channel logout.
- NestJS tiếp tục xác minh bearer token và sở hữu Customer Profile, consent,
  garage, DSAR cùng business authorization.
- Portal không gọi database, Drupal, Keycloak Admin API hoặc AI provider trực
  tiếp.

Tài liệu local:

- [Architecture](docs/architecture.md) cho BFF, DAL, auth và session.
- [Design system](docs/design-system.md) cho token và component convention.
- [Experience and accessibility](docs/experience-and-accessibility.md) cho
  journey state và WCAG acceptance.
- [Testing](docs/testing.md) cho taxonomy, artifact và acceptance gate.

## Lệnh local

```bash
node ../../infra/local/keycloak/sync-application-env.mjs
npm run dev
npm run typecheck
npm test
npm run test:integration
npm run build
npm run test:e2e
```

Redis local dùng database `3`. File `.env.local` được sinh với mode `0600` và
không được commit.

`test:e2e` là acceptance harness cho stack local thật. Suite được skip nếu
không đặt `CUSTOMER_E2E_ENABLED=true`, account E2E và credential Keycloak Admin
dành riêng cho back-channel. Test bị skip không được tính là bằng chứng
acceptance.

Browser-specific auth/BFF contract và NestJS resource contract được quản lý
riêng. Các mutation cookie-authenticated yêu cầu exact Origin và CSRF defense;
browser không được gọi resource API bằng bearer token.

Provider revocation thất bại được mã hóa và xếp hàng trong Redis. Scheduler dùng
machine credential gọi `POST /api/internal/provider-revocations` để retry.
Local session luôn bị xóa ngay; response phân biệt `confirmed`, `pending` và
`retry_required`.
