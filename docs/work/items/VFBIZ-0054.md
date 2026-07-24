---
id: VFBIZ-0054
title: Workforce release operations and authorization
status: review
mode: controlled
priority: P0
owner_team: workforce-experience
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
  - infra
allowed_paths:
  - backend/api/src/platform/security
  - backend/api/src/modules/product
  - backend/api/test/integration/product
  - backend/api/docs/identity-and-account.md
  - backend/api/docs/vehicle-catalog-and-garage.md
  - infra/local/keycloak/realms/workforce-realm.json
  - docs/work/items/VFBIZ-0054.md
  - WORK.md
depends_on:
  - VFBIZ-0052
  - VFBIZ-0053
controlled_signals:
  - identity
  - workforce-admin
  - authorization
  - vehicle-catalog
  - data-governance
exclusive_resources: []
required_checks:
  - npm run verify:api
  - npm run test:migrations --workspace @vfbiz/api
  - npm run governance:check
revision: 2
review_date: "2026-08-24"
updated_at: "2026-07-24T18:15:00.000+07:00"
---

# Outcome

Catalog và commercial release có command API nội bộ, chỉ workforce identity
đúng role và có MFA evidence mới được approve, activate hoặc rollback.

## Constraints

- Không đưa Operations route vào public OpenAPI hoặc generated customer SDK.
- Actor lấy từ signed token; không nhận subject/role từ request payload.
- Operator và reviewer là role khác nhau; database tiếp tục enforce
  separation of duties theo subject.
- Không tạo CRUD bypass cho release/fact/source.

## Done when

- OIDC verifier đưa validated realm role vào principal và reject malformed
  claim.
- Workforce endpoints enforce realm, role, MFA, OCC và typed error.
- Catalog và commercial workflows commit release state, audit và outbox
  atomically.
- Commercial activation fail closed với source/fact/anomaly không hợp lệ.

## Checkpoint

- Code complete: role/MFA guards, Keycloak role + AMR configuration, internal
  release controller và commercial release workflow.
- Public OpenAPI không có Operations command.
- Exact next action: independent Security/Product review, sau đó thiết kế
  production ingestion adapter; không mở direct fact CRUD.

## Evidence

- [x] `npm run verify:api` — lint/typecheck, 37 suites/173 tests, 9 E2E
  suites/59 tests, Prisma validation và build đạt ngày 24/07/2026.
- [x] `npm run test:migrations --workspace @vfbiz/api` — 14 migrations, schema
  drift rỗng, legacy backfill và 5 PostgreSQL suites/17 tests đạt.
- [x] `npm run contracts:lint` — public/internal OpenAPI không warning;
  Operations release route không xuất hiện trong public document.
- [x] `npm run governance:check` — 51 WorkItemV2, 52 indexed docs và 55
  provider-neutral context scenarios đạt.
- [x] Local Keycloak reconcile/check — workforce operator/reviewer roles, OIDC
  AMR access-token mapper, discovery, JWKS, PKCE và scopes đạt.
