---
id: VFBIZ-0072
title: Tích hợp và nghiệm thu Customer Portal
status: proposed
mode: controlled
priority: P0
owner_team: architecture-integration
accountable_role: release-owner
primary_workspace: root
affected_workspaces:
  - customer-portal
  - api
  - root
allowed_paths:
  - apps/customer-portal
  - contracts/openapi
  - packages/api-client
  - tests
  - docs/work/items/VFBIZ-0072.md
  - WORK.md
depends_on:
  - VFBIZ-0070
  - VFBIZ-0071
controlled_signals:
  - authentication
  - customer-data
  - public-contract
exclusive_resources:
  - public-openapi
  - package-lock
required_checks:
  - npm run governance:check
  - npm run contracts:lint
  - npm run verify:api
  - npm run verify:apps
  - npm run verify:apps:e2e
revision: 1
review_date: "2026-08-24"
---

# Outcome

Hai journey lane được tích hợp với contract, security, accessibility và browser
evidence nhất quán, có rollback point rõ.

## Constraints

- Integration owner không mở thêm feature hoặc nới acceptance đã khóa.
- Review/fix tối đa hai vòng và finding cũ cần evidence mới để mở lại.
- Không đóng work item nếu thiếu browser evidence hoặc rollback point.

## Done when

- Experience/accessibility và security/privacy review hoàn tất trong hai vòng.
- Toàn bộ verification gate đạt và generated files không drift.
- Residual risk và rollback point được ghi rõ.

## Checkpoint

- Waiting for VFBIZ-0070 and VFBIZ-0071.
- Exact next action: integrate only after both dependencies are done.

## Evidence

- [ ] Integration and release-owner acceptance.
