---
id: VFBIZ-0082
title: Constrained planner, asynchronous jobs và persistence
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
  - backend/api/src/modules/mobility/domain/trip
  - backend/api/src/modules/mobility/application
  - backend/api/src/modules/mobility/infrastructure/persistence
  - backend/api/src/modules/mobility/infrastructure/workers
  - backend/api/src/modules/mobility/presentation/http
  - backend/api/test/unit/mobility
  - backend/api/test/integration/mobility
  - backend/api/test/e2e/mobility
  - contracts/openapi
  - packages/api-client/src/generated.ts
  - docs/work/items/VFBIZ-0082.md
  - docs/work/plans/VFBIZ-0077.md
depends_on:
  - VFBIZ-0037
  - VFBIZ-0079
  - VFBIZ-0080
  - VFBIZ-0081
controlled_signals:
  - ev-trip-planner
  - location-privacy
  - public-contract
  - trip-correctness
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

Constrained planner tạo, hủy và truy vấn asynchronous TripPlan với alternatives,
revision pinning, uncertainty và typed `NO_FEASIBLE_ROUTE`.

## Constraints

- Plan computation không chạy trong HTTP request thread.
- Idempotency, OCC/fencing và cancellation ngăn stale worker commit.
- Exact location dùng approved encryption/pseudonymization và TTL.
- Plan không phải live navigation hoặc safety instruction.

## Done when

- State lifecycle `queued/routing/evaluating_stops/completed/failed/cancelled`
  không có transition trái phép.
- Solver xử lý zero/one/multi-stop và no-feasible cases.
- Totals khớp leg/stop components trong tolerance đã version.
- Provider/data/algorithm revisions và source freshness được persist.
- Cancellation, replay, duplicate job và stale completion tests đạt.

## Decisions and assumptions

- Giữ solver trong NestJS Mobility cho đến khi profiling chứng minh cần tách.

## Checkpoint

- Exact next action: integration owner khóa contract lease và worker transaction.

## Evidence

- [ ] `npm run contracts:lint` — add observed evidence
- [ ] `npm run verify:api` — add observed evidence
