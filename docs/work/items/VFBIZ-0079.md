---
id: VFBIZ-0079
title: Charging projection, adapters và discovery API
status: proposed
mode: controlled
priority: P0
owner_team: mobility-platform
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
  - root
allowed_paths:
  - backend/api/src/modules/mobility/domain/charging
  - backend/api/src/modules/mobility/application
  - backend/api/src/modules/mobility/infrastructure/providers
  - backend/api/src/modules/mobility/presentation/http
  - backend/api/test/integration/mobility
  - backend/api/test/e2e/mobility
  - contracts/openapi
  - packages/api-client/src/generated.ts
  - docs/work/items/VFBIZ-0079.md
  - docs/work/plans/VFBIZ-0077.md
depends_on:
  - VFBIZ-0078
controlled_signals:
  - charging-data
  - data-governance
  - public-contract
  - route-provider
exclusive_resources:
  - public-contract
required_checks:
  - npm run contracts:lint
  - npm run verify:api
plan: docs/work/plans/VFBIZ-0077.md
revision: 1
review_date: "2026-08-24"
---

# Outcome

API cung cấp charging-location discovery từ governed projections, với adapter
OCPI/V-GREEN rõ authority, freshness và typed unavailable state.

## Constraints

- Customer API không gọi trực tiếp OCPP hoặc charger.
- Google Places không là authority cho connector, tariff hoặc live status.
- Adapter fail closed khi source revision, market hoặc temporal validity thiếu.
- Không lưu credential/provider payload ngoài retention được duyệt.

## Done when

- Discovery hỗ trợ corridor/radius, compatible connector và temporal filters.
- Response có source revision, observed/effective time và freshness.
- Provider duplicate/out-of-order/malformed events không làm hỏng projection.
- OpenAPI, generated SDK, integration và negative authorization tests đạt.

## Decisions and assumptions

- V-GREEN/CSMS adapter có thể dùng fixture cho đến khi có approved credentials.

## Checkpoint

- Exact next action: khóa discovery contract và adapter fixture sau VFBIZ-0078.

## Evidence

- [ ] `npm run contracts:lint` — add observed evidence
- [ ] `npm run verify:api` — add observed evidence
