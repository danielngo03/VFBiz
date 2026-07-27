---
id: VFBIZ-0083
title: Customer EV Journey Planner experience
status: proposed
mode: controlled
priority: P1
owner_team: mobility-platform
accountable_role: product-owner
primary_workspace: customer-portal
affected_workspaces:
  - customer-portal
allowed_paths:
  - apps/customer-portal/src/app
  - apps/customer-portal/src/features
  - apps/customer-portal/src/platform/api
  - apps/customer-portal/src/components
  - apps/customer-portal/src/styles
  - apps/customer-portal/tests
  - docs/work/items/VFBIZ-0083.md
  - docs/work/plans/VFBIZ-0077.md
depends_on:
  - VFBIZ-0072
  - VFBIZ-0082
controlled_signals:
  - customer-journey
  - ev-trip-planner
  - location-privacy
  - route-provider
exclusive_resources: []
required_checks:
  - npm run lint --workspace @vfbiz/customer-portal
  - npm run typecheck --workspace @vfbiz/customer-portal
  - npm run test --workspace @vfbiz/customer-portal
  - npm run test:e2e:required --workspace @vfbiz/customer-portal
plan: docs/work/plans/VFBIZ-0077.md
revision: 1
review_date: "2026-08-24"
---

# Outcome

Customer Portal cho phép chọn xe, nhập hành trình, theo dõi job và so sánh
alternatives với source/freshness/confidence và failure state trung thực.

## Constraints

- Browser không giữ server key, raw provider credential hoặc bearer token.
- Attribution, consent và location-retention copy phải đúng provider/policy.
- Map không biến kết quả pre-trip thành live navigation guidance.
- UI không hiển thị con số chắc chắn khi tariff, availability hoặc energy
  confidence không đủ.

## Done when

- Origin/destination ambiguity, loading, cancel, retry và provider unavailable
  có accessible states.
- Zero/one/multi-stop, no-feasible và stale-data journeys có browser evidence.
- Keyboard, focus, responsive layout và WCAG AA checks đạt.
- Client dùng generated SDK và không gọi provider trực tiếp.

## Decisions and assumptions

- Customer Web Experience là coordination consumer; Mobility Platform vẫn chịu
  trách nhiệm correctness của planner capability.

## Checkpoint

- Exact next action: Design Lead review journey/warning copy sau API fixture ổn định.

## Evidence

- [ ] Portal lint/typecheck/unit — add observed evidence
- [ ] Required Playwright E2E — add observed evidence
