---
id: VFBIZ-0056
title: Workforce authorization runtime and API
status: active
mode: controlled
priority: P0
owner_team: api-foundation
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/access
  - backend/api/src/platform/security
  - backend/api/prisma/models/access.prisma
  - backend/api/prisma/migrations
  - backend/api/prisma/seed
  - backend/api/scripts/bootstrap-workforce-administrators.ts
  - backend/api/package.json
  - backend/api/test/e2e/access
  - backend/api/test/integration/access
  - backend/api/docs/workforce-authorization.md
  - contracts/openapi/workforce-v1.yaml
  - docs/work/items/VFBIZ-0056.md
  - docs/work/plans/VFBIZ-0055.md
  - WORK.md
depends_on:
  - VFBIZ-0055
controlled_signals:
  - authorization
  - workforce-admin
  - migration
exclusive_resources:
  - database-migration
  - public-contract
required_checks:
  - npm run verify:api
  - npm run test:migrations --workspace @vfbiz/api
  - npm run governance:check
revision: 3
review_date: "2026-08-24"
updated_at: "2026-07-24T20:10:00.000+07:00"
---

# Outcome

API resolve dynamic workforce entitlement từ PostgreSQL, enforce capability
deny-by-default và expose workforce authorization management contract.

## Constraints

- Không tin business role/capability từ token.
- Capability catalog là contract code-owned.
- Scope chỉ global, market, showroom hoặc department.
- Privileged change bắt buộc maker-checker và step-up MFA.
- Mutation, audit, revision và outbox atomic.

## Done when

- Additive schema/migration và seed catalog hợp lệ.
- Capability decorator/decision service có negative tests.
- Workforce API có role, assignment, approval và entitlement baseline.
- Redis chỉ là optional cache; database failure fail closed.

## Checkpoint

- Implemented capability/role/assignment/approval schema and additive migration.
- Added database-backed entitlement resolution, capability decision service,
  deny-by-default guard and workforce management endpoints.
- Added separate workforce OpenAPI contract and local authorization boundary
  documentation.
- Added directory projection and minimized audit query endpoints; repository
  prevents revoking the final active global authorization administrator.
- Added controlled, non-HTTP two-administrator bootstrap with an explicit
  acknowledgement, audit/outbox evidence and partial-authority refusal.
- Exact next action: add durable idempotency replay and Redis invalidation
  transport before production cutover.

## Evidence

- [x] Prisma format, validate and generate
- [x] API lint and typecheck
- [x] API build
- [x] Focused capability decision/decorator/guard tests (8 tests)
- [x] Workforce OpenAPI contract lint
- [x] PostgreSQL clean replay, schema drift, 17 integration tests and legacy backfill
- [x] API lint/typecheck, 197 unit/integration tests, 59 E2E tests, Prisma
  validation and build
- [x] `npm run test:migrations --workspace @vfbiz/api`
- [x] Bootstrap command fails closed without explicit acknowledgement.
- [ ] Durable idempotency replay and entitlement invalidation transport.
