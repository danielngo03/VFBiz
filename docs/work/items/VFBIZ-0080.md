---
id: VFBIZ-0080
title: Google route adapters và FinOps controls
status: proposed
mode: controlled
priority: P0
owner_team: mobility-platform
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
  - infra
allowed_paths:
  - backend/api/src/modules/mobility/application/ports
  - backend/api/src/modules/mobility/infrastructure/providers
  - backend/api/src/platform/config
  - backend/api/test/integration/mobility
  - backend/api/test/fixtures/mobility
  - infra/local
  - docs/work/items/VFBIZ-0080.md
  - docs/work/plans/VFBIZ-0077.md
depends_on:
  - VFBIZ-0077
controlled_signals:
  - ev-trip-planner
  - location-privacy
  - route-provider
  - secret
exclusive_resources: []
required_checks:
  - npm run verify:api
  - npm run governance:check
plan: docs/work/plans/VFBIZ-0077.md
revision: 1
review_date: "2026-08-24"
---

# Outcome

Google Routes/Places được bao bởi provider-neutral ports, use-case field-mask
allowlist, quota/cost controls, privacy redaction và deterministic replay.

## Constraints

- Browser/server key tách biệt và không commit secret.
- Route/polyline chỉ được persist/cache khi provider policy cho phép.
- Autocomplete session token, attribution và Terms/Privacy behavior bắt buộc.
- Real-provider test có explicit budget cap; load test dùng approved replay.

## Done when

- Timeout, quota, 4xx/5xx, malformed payload và circuit breaker có typed result.
- Field mask test thất bại khi adapter yêu cầu field ngoài allowlist.
- Log/trace không chứa raw origin, destination, key hoặc provider token.
- Cost/request metrics và budget alert evidence được thu thập bất đồng bộ.

## Decisions and assumptions

- Adapter fixture là baseline cho CI; provider smoke test không chạy mặc định.

## Checkpoint

- Exact next action: Legal/Privacy review storage matrix và API configuration.

## Evidence

- [ ] `npm run verify:api` — add observed evidence
- [ ] `npm run governance:check` — add observed evidence
