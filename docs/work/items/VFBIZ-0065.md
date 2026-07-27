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
  - backend/api/test/integration/customer
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
- **Database-backed audit integration test — done**:
  `test/integration/customer/workforce-customer-support.postgres-spec.ts`
  (4 tests, real PostgreSQL, following the `describeWithDatabase` pattern)
  seeds a real `CustomerProfile`, calls
  `PrismaWorkforceCustomerSupportRepository.search()` and asserts exactly
  one `AuditEvent` row with correct `actorRef`/`correlationId`/`action`,
  that the raw search term never appears in `metadata`, and that a
  no-match and an out-of-market-scope search still audit correctly.
- **Real bug found and fixed while writing that test**: `search()`
  unconditionally included `{ id: { equals: input.query } }` in its `OR`
  filter. Since `id` is a native `uuid` Postgres column, any non-UUID
  search term (i.e. every ordinary name search — the primary use case)
  made Postgres reject the whole query with "invalid input syntax for type
  uuid", a 500 for the single most common workforce search. Fixed by only
  including the exact-ID branch when the query is syntactically a UUID,
  otherwise matching on `displayName` alone. Covered by both the new
  no-match test (a non-UUID term) and a new dedicated exact-ID-match test.
- Exact next action: Security Owner review and Customer Portal opaque BFF
  cutover remain the only open items (BFF token vault turns out to already
  be built under `apps/customer-portal`, owned by the Customer Web
  Experience track per VFBIZ-0070/0071/0073 — worth Engineering Lead
  confirming this item's `depends_on`/`allowed_paths` should reflect that
  rather than re-scoping it here).

## Evidence

- [x] API typecheck và targeted Customer Support HTTP E2E đạt.
- [x] Clean/legacy migration replay đạt với 16 migrations.
- [x] Workforce Portal typecheck và 15 tests đạt.
- [x] Ba OpenAPI contracts lint sạch; 24 capabilities hợp lệ.
- [x] Local Keycloak Identity Bridge integration smoke đạt.
- [x] Customer/Workforce auth contracts lint sạch và application builds đạt.
- [x] Database-backed customer-search audit test — 2026-07-27: 4/4 tests
  pass against a real, freshly migrated PostgreSQL 17 + PostGIS container;
  full re-verification after the `search()` fix — `npm run verify:api`
  (lint, typecheck, 263 unit/integration tests, 63 E2E tests, Prisma
  validation, build) and all 34 `*.postgres-spec.ts` tests repo-wide — all
  pass.
- [ ] Security Owner review và Customer Portal opaque BFF cutover chưa hoàn tất.
