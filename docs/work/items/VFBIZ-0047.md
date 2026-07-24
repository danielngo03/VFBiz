---
id: VFBIZ-0047
title: Native Keycloak local và OIDC acceptance
status: done
mode: controlled
priority: P0
owner_team: reliability-engineering
accountable_role: security-owner
primary_workspace: infra
affected_workspaces:
  - infra
  - api
  - customer-portal
allowed_paths:
  - infra/local/keycloak
  - backend/api/.env.example
  - backend/api/docs/identity-and-account.md
  - backend/api/test/integration/access
  - docs/work/items
  - WORK.md
depends_on: []
controlled_signals:
  - authentication
  - authorization
  - pii
exclusive_resources:
  - identity-provider-config
required_checks:
  - npm run verify:api
  - npm run verify:apps
  - npm run governance:check
revision: 5
review_date: "2026-07-23"
updated_at: "2026-07-23T16:19:12.567Z"
---

# Outcome

Keycloak chạy native trên localhost với database PostgreSQL riêng, hai realm
customer/workforce và confidential client đúng redirect/audience/scope để
Account flow có real-provider integration evidence thay vì chỉ mock.

## Constraints

- Không dùng production user, email, secret hoặc federation.
- Không commit bootstrap admin password hoặc generated client secret.
- Customer và workforce realm/database/client phải tách.
- API callback hiện tại là `http://127.0.0.1:8000/auth/customer/callback`;
  realm import không được giữ redirect `localhost:5173/bff/callback` lệch runtime.
- Native process không chiếm cổng PostgreSQL/Redis/API hiện hữu.

## Done when

- Keycloak discovery/JWKS của hai realm trả `200` trên localhost.
- Customer confidential client dùng PKCE S256, đúng callback và audience mapper.
- Registration, login, callback, refresh, logout và invalid-state flow chạy qua
  provider thật với synthetic local user.
- MFA/email verification policy được cấu hình hoặc ghi rõ staging limitation.
- Secret chỉ nằm trong ignored local environment.

## Checkpoint

- Keycloak `26.7.0` chạy native với OpenJDK `25.0.4`, database
  `vfbiz_keycloak` riêng trên PostgreSQL 17 và secrets ignored ngoài Git.
- Customer/workforce discovery và JWKS đạt; realm import không còn missing
  scope. Customer BFF dùng confidential client, PKCE S256, audience riêng,
  đúng callback và least-privilege scopes.
- Browser acceptance bằng synthetic user đã quan sát authorization code,
  callback `302`, access/refresh/CSRF cookie, refresh `204` và logout `204`;
  synthetic user đã được xóa sau kiểm thử.
- Lần kiểm thử đầu phát hiện access token thiếu `sub`; root cause là realm
  import thiếu standard `basic` client scope. Definition và live realm đã được
  sửa, browser flow sau đó đạt.
- Email verification và customer registration được cấu hình nhưng SMTP local
  chưa được cấu hình; workforce TOTP là default required action. Production
  SMTP/federation/conditional access nằm ngoài local foundation.
- Exact next action: Security Owner review realm policy; portal integration
  test registration/email/MFA được mở khi mail sink và workforce UI tồn tại.

## Evidence

- [x] `infra/local/keycloak/native-check.sh` — discovery, JWKS, PKCE, callback
  và required scopes đạt.
- [x] Real-provider browser acceptance — login/callback/refresh/logout đạt,
  cookie content không được ghi vào evidence.
- [x] `npm run verify:api` — API gate đạt.
- [x] `npm run verify:apps` — 3 Customer Portal và 2 Operations Admin tests
  đạt.
- [x] `npm run governance:check` — 45 WorkItemV2 và 55 provider-neutral
  scenarios đạt.

### done — 2026-07-23T16:19:12.567Z

Final approver yêu cầu tiếp tục; native Keycloak và real-provider acceptance đã đạt, production SMTP/federation vẫn là release gate riêng.
