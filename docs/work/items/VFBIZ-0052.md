---
id: VFBIZ-0052
title: Catalog release state machine và atomic persistence
status: review
mode: controlled
priority: P0
owner_team: customer-product
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/product
  - backend/api/prisma/models/product.prisma
  - backend/api/prisma/migrations
  - backend/api/prisma/seed
  - backend/api/test/integration/product
  - backend/api/scripts/verify-migrations.sh
  - backend/api/docs/vehicle-catalog-and-garage.md
  - docs/work/items/VFBIZ-0033.md
  - docs/work/items/VFBIZ-0052.md
  - WORK.md
depends_on: []
controlled_signals:
  - data-governance
  - migration
  - vehicle-catalog
exclusive_resources:
  - database-migration
required_checks:
  - npm run verify:api
  - npm run test:migrations --workspace @vfbiz/api
  - npm run governance:check
revision: 2
review_date: "2026-08-24"
updated_at: "2026-07-24T13:00:00.000+07:00"
---

# Outcome

Catalog release có state machine và evidence fields ở database; approve,
activate, supersede và rollback không thể tạo hai active release hoặc bỏ qua
separation of duties.

## Constraints

- Đây là implementation enabler cho VFBIZ-0033, không phải Data Owner
  acceptance.
- Chưa tạo workforce endpoint trong work item này.
- Release activation chỉ nhận candidate có source và fact provenance hợp lệ.
- Mọi transition ghi audit/outbox cùng transaction.
- Rollback không được hồi sinh source stale, retired hoặc hết hiệu lực.

## Done when

- Prisma và PostgreSQL check constraint giữ state/timestamp/evidence invariant.
- Application service có approve, activate và rollback command typed.
- PostgreSQL advisory lock hoặc tương đương serialize activation theo market.
- Audit/outbox được ghi atomic.
- Unit/integration/migration replay bao phủ transition hợp lệ và transition bị
  từ chối.

## Checkpoint

- Code complete: state machine, separation of duties, OCC, advisory lock theo
  market, atomic audit/outbox và rollback đều đã có persistence test.
- Đây vẫn chỉ là technical enabler. Data Owner chưa chấp nhận source hoặc
  Catalog release VinFast nào.
- Exact next action: independent review; sau đó VFBIZ-0033 có thể bổ sung
  workforce authorization và reconciliation operation.

## Evidence

- [x] `npm run verify:api` — 34 suites/163 tests; 8 E2E suites/54 tests; lint,
  typecheck, Prisma validate và build đạt ngày 24/07/2026.
- [x] PostgreSQL workflow integration — approve, activate release A/B và
  rollback về A; audit/outbox được ghi cùng transaction.
- [x] `npm run test:migrations --workspace @vfbiz/api` — 12 migration replay
  sạch, schema drift rỗng, 4 suites/14 PostgreSQL tests và legacy backfill đạt.
- [x] `npm run governance:check` — 50 WorkItemV2, instruction/role/skill/
  adapters và 55 provider-neutral scenarios đạt ngày 24/07/2026.
