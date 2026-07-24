---
id: VFBIZ-0037
title: Vehicle Catalog contract parity và generated SDK
status: proposed
mode: controlled
priority: P0
owner_team: architecture-integration
accountable_role: architect
primary_workspace: root
affected_workspaces:
  - root
allowed_paths:
  - contracts/openapi
  - tests/contract
  - packages/api-client
depends_on:
  - VFBIZ-0033
controlled_signals:
  - architecture
  - public-contract
  - vehicle-catalog
exclusive_resources:
  - public-contract
required_checks:
  - npm run contracts:lint
  - npm run governance:check
revision: 2
review_date: "2026-08-23"
---

# Outcome

Reviewed OpenAPI, runtime NestJS và generated TypeScript SDK mô tả cùng một
Vehicle Catalog contract; client không phải dựa vào một YAML khác với route
đang chạy thật.

## Constraints

- Không tạo placeholder endpoint để làm contract “đạt”.
- `market`, operation ID, response schema và failure shape phải khớp runtime.
- Breaking change cần compatibility plan/ADR; contract writer giữ exclusive
  lease.
- Không đưa `extensionData`, Prisma record hoặc raw source payload vào SDK.

## Done when

- Runtime route inventory phát hiện operation thừa/thiếu so với reviewed
  OpenAPI.
- List/detail response pin release/source/freshness và typed availability.
- OpenAPI lint không warning; generated SDK reproducible và compatibility gate
  đạt.
- Contract tests có negative case cho unavailable/stale catalog.

## Checkpoint

- Runtime/reviewed contract test hiện so sánh toàn bộ public operation inventory
  thay vì chỉ Account. Catalog list/detail và commercial endpoint đã có
  operation ID đồng nhất; TypeScript SDK đã sinh lại.
- Work item vẫn `proposed` vì VFBIZ-0033 chưa qua Data Owner/release operation
  acceptance và semantic response parity cần independent Architecture review.
- Exact next action: independent semantic contract review sau VFBIZ-0033.

## Evidence

- [x] `npm run contracts:lint` — public/internal OpenAPI không warning; runtime
  inventory và generated SDK đạt ngày 24/07/2026.
- [ ] `npm run governance:check` — add evidence reference
