---
id: VFBIZ-0065
title: Customer identity assurance và Workforce Customer Support
status: active
mode: controlled
priority: P0
owner_team: customer-engagement
accountable_role: security-owner
primary_workspace: api
affected_workspaces:
  - api
  - workforce-portal
  - infra
allowed_paths:
  - backend/api/src/modules/access
  - backend/api/src/modules/customer
  - backend/api/prisma
  - contracts/authorization
  - contracts/openapi
  - apps/workforce-portal
  - infra/local/keycloak
  - docs/work/items/VFBIZ-0065.md
  - WORK.md
depends_on: []
controlled_signals:
  - authentication
  - authorization
  - customer-data
  - workforce-admin
exclusive_resources:
  - workforce-contract
  - database-migration
required_checks:
  - npm run verify:api
  - npm run verify:apps
  - npm run contracts:lint
revision: 3
review_date: "2026-08-24"
---

# Outcome

Customer và workforce thấy đúng identity/session assurance; customer có thể
đăng xuất mọi thiết bị; nhân sự CSKH chỉ tìm thấy projection khách hàng tối
thiểu trong phạm vi capability và organizational scope được cấp.

## Invariants

- Keycloak sở hữu credential, email verification, MFA enrollment và provider
  session; PostgreSQL/Redis chỉ giữ projection tối thiểu cần cho local control.
- Không lưu password, OTP seed, recovery code, token hoặc raw IP.
- Customer search cần MFA, capability, market/global scope và audited reason.
- Raw search term không đi vào audit.

## Constraints

- Không lưu password, OTP seed, recovery code, access/refresh token hoặc raw IP
  trong PostgreSQL hay browser storage.
- Provider credential/session là authority của Keycloak; local projection chỉ
  dùng cho fail-closed denial, UX tối thiểu và audit.
- Workforce customer lookup phải yêu cầu verified workforce principal, MFA,
  capability, organizational scope và business reason.
- Không tuyên bố provider revocation thành công khi bridge không xác nhận.

## Done when

- Customer callback chặn email chưa verify và session security phân biệt rõ
  provider enrollment với current-session evidence.
- Customer có thể xem session tối thiểu và logout-all local/provider với trạng
  thái reconciliation rõ ràng.
- Workforce BFF chỉ giữ opaque cookie, token vault server-side và hỗ trợ device
  list/logout-all.
- Customer Support HTTP boundary chứng minh MFA alternative, capability,
  organizational scope, minimized response và fail-closed behavior.
- Keycloak native check/smoke, API/apps/contracts/governance gates đạt.

## Checkpoint

- Customer session projection đã có device/browser, network prefix,
  email-verification và session MFA evidence.
- Protected Keycloak Admin bridge cung cấp MFA enrollment và subject-wide
  logout; thiếu bridge trả trạng thái unavailable/manual review.
- Workforce BFF đã có subject session index và logout-all.
- Customer Support read API đã có runtime, capability và reviewed OpenAPI.
- HTTP E2E khóa MFA alternative, capability deny, market scope, minimized
  response, query/reason validation. Workforce route test khóa multi-session
  logout, token minimization và same-origin protection.
- Native Keycloak check đã xác nhận discovery/JWKS/PKCE, AMR mapper và
  least-privilege Identity Bridge; synthetic smoke đã xác nhận read credential
  inventory và subject-wide logout.
- Customer callback chặn email chưa verify; optional MFA enrollment dùng
  Keycloak `CONFIGURE_TOTP`, không đưa OTP secret vào VFBiz.
- Exact next action: Security Owner review, Customer Portal opaque BFF token
  vault và database-backed audit integration test cho customer search.

## Evidence

- [x] API typecheck và targeted Customer Support HTTP E2E đạt.
- [x] Clean/legacy migration replay đạt với 16 migrations.
- [x] Workforce Portal typecheck và 15 tests đạt.
- [x] Ba OpenAPI contracts lint sạch; 24 capabilities hợp lệ.
- [x] Local Keycloak Identity Bridge integration smoke đạt.
- [x] Customer/Workforce auth contracts lint sạch và application builds đạt.
- [ ] Security Owner review và Customer Portal opaque BFF cutover chưa hoàn tất.
