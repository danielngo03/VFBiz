---
id: VFBIZ-0078
title: Chuẩn hóa charging data và migration
status: proposed
mode: controlled
priority: P0
owner_team: mobility-platform
accountable_role: data-owner
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/prisma/models/mobility.prisma
  - backend/api/prisma/migrations
  - backend/api/src/modules/mobility/domain/charging
  - backend/api/src/modules/mobility/infrastructure/persistence
  - backend/api/test/integration/mobility
  - backend/api/test/e2e/mobility
  - docs/work/items/VFBIZ-0078.md
  - docs/work/plans/VFBIZ-0077.md
depends_on:
  - VFBIZ-0033
  - VFBIZ-0037
  - VFBIZ-0077
controlled_signals:
  - charging-data
  - migration
  - schema
  - trip-correctness
exclusive_resources:
  - database-migration
required_checks:
  - npm run test:migrations --workspace @vfbiz/api
  - npm run verify:api
plan: docs/work/plans/VFBIZ-0077.md
revision: 1
review_date: "2026-08-24"
---

# Outcome

Charging data được chuẩn hóa thành Location, EVSE, Connector, availability,
tariff revision và reliability snapshot, thay cho số lượng connector tổng hợp.

## Constraints

- Migration phải additive trước, có rollback/recovery và không bịa dữ liệu
  connector từ `unitCount`.
- Availability observation không ghi đè identity/capability tĩnh của EVSE.
- Tariff giữ currency, timezone, effective window và price component rõ ràng.
- Chỉ integration owner giữ `database-migration` lease.

## Done when

- Clean database và legacy fixture áp migration không drift.
- Domain invariant chặn EVSE/Connector/Tariff không hợp lệ.
- Dữ liệu không chuyển đổi an toàn được quarantine thay vì suy diễn.
- Repository/mapping/integration tests chứng minh revision và temporal query.

## Decisions and assumptions

- OCPI là interoperability reference, không được copy mù quáng thành domain.

## Checkpoint

- Exact next action: chỉ chuyển `ready` sau khi dependencies `done` và migration
  strategy được Data Owner/Architect review.

## Evidence

- [ ] `npm run test:migrations --workspace @vfbiz/api` — add observed evidence
- [ ] `npm run verify:api` — add observed evidence
