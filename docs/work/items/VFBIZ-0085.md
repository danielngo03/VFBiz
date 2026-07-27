---
id: VFBIZ-0085
title: EV Journey Planner release evidence
status: proposed
mode: controlled
priority: P0
owner_team: mobility-platform
accountable_role: release-owner
primary_workspace: api
affected_workspaces:
  - api
  - ai
  - customer-portal
  - infra
allowed_paths:
  - backend/api/test
  - backend/ai/tests/contract/assistant
  - apps/customer-portal/tests
  - infra
  - docs/work/items/VFBIZ-0085.md
  - docs/work/plans/VFBIZ-0077.md
depends_on:
  - VFBIZ-0083
  - VFBIZ-0084
controlled_signals:
  - location-privacy
  - production
  - route-provider
  - trip-correctness
  - trip-release
exclusive_resources: []
required_checks:
  - npm run governance:check
  - npm run contracts:lint
  - npm run verify:api
  - npm run verify:ai
  - npm run verify:apps
  - npm run verify:apps:e2e
plan: docs/work/plans/VFBIZ-0077.md
revision: 1
review_date: "2026-08-24"
---

# Outcome

Release Owner nhận immutable evidence về correctness, privacy, provider policy,
cost, resilience và rollback của EV Journey Planner để quyết định staging/canary.

## Constraints

- Agent chỉ tạo evidence; không tự approve, promote hoặc deploy.
- Load dùng record/replay; provider smoke có budget cap.
- SLO/capacity chỉ được ghi sau benchmark với workload đã công bố.
- Shadow output không tự trở thành training data.

## Done when

- `validate-trip-release` bao phủ zero/one/multi/no-feasible, tariff/timezone,
  connector, stale data, provider outage và location privacy.
- SOC MAE, underprediction, calibration, reserve violation, latency và cost có
  baseline/tolerance versioned.
- Kill switch, rollback, provider outage và data-revision rollback được diễn tập.
- Security, Privacy, Legal, Product và Release human gates có evidence link.

## Decisions and assumptions

- Staging acceptance không đồng nghĩa production release.

## Checkpoint

- Exact next action: chỉ bắt đầu khi VFBIZ-0083 và VFBIZ-0084 có sealed evidence.

## Evidence

- [ ] Governance/contracts/API/AI/apps gates — add observed evidence
- [ ] Release report and rollback drill — add observed evidence
