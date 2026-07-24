---
id: VFBIZ-0029
title: Access session projection và CIAM revoke lifecycle
status: done
mode: controlled
priority: P0
owner_team: api-foundation
accountable_role: security-owner
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/access
  - backend/api/src/platform/security
  - backend/api/src/app.module.ts
  - backend/api/prisma/models/access.prisma
  - backend/api/prisma/migrations
  - backend/api/scripts/verify-migrations.sh
  - backend/api/test/integration/access
  - backend/api/test/e2e/access
depends_on:
  - VFBIZ-0027
controlled_signals:
  - authentication
  - authorization
  - migration
  - pii
exclusive_resources:
  - database-migration
required_checks:
  - npm run verify:api
  - npm run test:migrations --workspace @vfbiz/api
  - npm run governance:check
revision: 6
review_date: "2026-08-23"
updated_at: "2026-07-23T09:10:53.416Z"
---

# Outcome

API quản lý projection của customer session để liệt kê/revoke/reconcile an toàn,
trong khi credential, MFA và token lifecycle vẫn thuộc CIAM/BFF.

## Constraints

- Không lưu password, MFA secret, raw refresh/access token hoặc browser cookie.
- `/auth/customer/*` thuộc Customer Portal BFF, không được giả làm API route.
- Session identifier là opaque; revoke phải subject-scoped và idempotent.
- Migration theo expand/migrate/contract và cần lease.

## Done when

- Session projection pin issuer/subject/client, created/last-seen/expiry/revoked.
- List/revoke kiểm subject và scope; CIAM failure có typed reconciliation state.
- Revoked/expired session không quay lại active qua out-of-order event.
- PostgreSQL integration tests và migration clean/legacy replay đạt.

## Checkpoint

- Access session projection, CIAM revoke lifecycle và local deny path đã
  code-complete. Exact next action: chuyển sang public Account contract parity
  hoặc DSAR deletion registry; không mở rộng thêm chatbot trước khi foundation
  account/vehicle xong.

## Evidence

- [x] `npm run verify:api` — pass 2026-07-23; 26 unit suites/121 tests, 7 E2E suites/42 tests, lint/typecheck/Prisma/build pass.
- [x] `npm run test:migrations --workspace @vfbiz/api` — pass 2026-07-23; clean replay, schema drift, legacy backfill and Access PostgreSQL behavior pass.
- [x] `npm run governance:check` — pass 2026-07-23; docs index, 36 WorkItemV2 files, roles/adapters/skills and 55 context scenarios pass.

### ready — 2026-07-23T08:14:29.062Z

OIDC operation scopes are complete and session projection schema already exists; implementation can proceed behind a provider-neutral revocation port.

### active — 2026-07-23T08:14:29.393Z

Implement Access session domain/application/persistence and safe provider reconciliation; do not create BFF callback routes in API.

### checkpoint — 2026-07-23

Bounded context và HTTP boundary đã code-complete, 24 unit suites/110 tests và
7 E2E suites/36 tests đạt; clean/legacy migration replay trên PostgreSQL/PostGIS
thật đạt. Risk review chặn acceptance vì revocation chưa có durable
pending/outbox state, adapter chưa có secret reference/provider routing, local
deny chưa được nối vào authentication path và test repository mới là mock
contract seam. Exact next action: thực hiện đúng một fix cycle cho các finding
trên và thêm observed PostgreSQL behavior test.
