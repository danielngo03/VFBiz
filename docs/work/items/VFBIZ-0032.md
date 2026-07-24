---
id: VFBIZ-0032
title: DSAR intake, target snapshot và customer status
status: review
mode: controlled
priority: P0
owner_team: customer-product
accountable_role: privacy-owner
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/customer
  - backend/api/prisma/models/customer.prisma
  - backend/api/prisma/migrations
  - backend/api/scripts/verify-migrations.sh
  - backend/api/test/integration/customer
  - backend/api/test/e2e/customer
  - backend/api/docs/identity-and-account.md
  - backend/api/docs/data-model.md
  - contracts/openapi
  - packages/api-client
  - docs/work/items
  - WORK.md
depends_on:
  - VFBIZ-0014
  - VFBIZ-0029
  - VFBIZ-0031
  - VFBIZ-0044
controlled_signals:
  - customer-data
  - pii
  - consent
exclusive_resources:
  - database-migration
  - public-contract
required_checks:
  - npm run verify:api
  - npm run test:migrations --workspace @vfbiz/api
  - npm run contracts:lint
  - npm run governance:check
revision: 6
review_date: "2026-08-23"
updated_at: "2026-07-23T16:47:36.949Z"
---

# Outcome

Data request được tiếp nhận idempotently, snapshot đúng execution target theo
loại export/delete và cho customer theo dõi lifecycle mà không lộ target hoặc
provider error nội bộ.

## Constraints

- Target snapshot gồm API, AI, cache, object storage và telemetry boundary.
- Registry snapshot được tạo ngay khi nhận request; target chưa có adapter thật
  phải giữ `pending`/`permanent_failure`, không dùng noop success.
- Legal hold cần authority, purpose và expiry; không phải cờ bỏ qua xóa tùy ý.
- Foundation chỉ định state/retry/lease/evidence contract; worker và adapter
  thực thi nằm trong VFBIZ-0049.
- Không dùng immutable audit/hash để lách right-to-erasure.

## Done when

- Request lifecycle có target-level state, retry/lease fields và typed legal
  hold evidence constraints.
- Delete/export idempotent; delete luôn giữ subject mapping tới phase cuối.
- Dữ liệu request cũ được backfill target snapshot/event fail-closed.
- Customer list/detail subject-scoped và OpenAPI/SDK đồng bộ.
- Migration clean replay, schema drift và PostgreSQL integration đạt.

## Checkpoint

- Exact next action: Privacy Owner review foundation; VFBIZ-0049 chỉ được ready
  sau khi retention, deadline, recent-auth và legal-hold authority được duyệt.

## Evidence

- [x] `npm run verify:api` — 31 unit suites/147 tests, 8 E2E
  suites/52 tests, lint, typecheck, Prisma validate và build đạt ngày
  2026-07-23.
- [x] `npm run test:migrations --workspace @vfbiz/api` — PostgreSQL 17/PostGIS
  clean replay, schema drift, integration và legacy replay đạt với 10 migration.
- [x] `npm run contracts:lint` — reviewed OpenAPI + runtime schema compile đạt;
  TypeScript SDK đã regenerate ngày 2026-07-23.
- [x] `npm run governance:check` — 46 WorkItemV2 và 55 provider-neutral context
  scenarios đạt ngày 2026-07-23.

### ready — 2026-07-23T16:30:00.492Z

Dependencies Account, Session, Consent đã hoàn tất; target registry và fail-closed boundary đã được audit.

### active — 2026-07-23T16:30:00.794Z

Triển khai DSAR request/target snapshot và customer-visible status trước external adapters.

### review — 2026-07-23T16:47:36.949Z

Foundation đã đạt gates: target plan v2, legacy backfill, subject-scoped status, legal-hold constraints và OpenAPI/SDK parity. Chờ Privacy Owner review; external execution adapters được tách sang VFBIZ-0049.
