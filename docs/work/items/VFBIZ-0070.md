---
id: VFBIZ-0070
title: Account, security và privacy journeys
status: active
mode: controlled
priority: P0
owner_team: customer-web-experience
accountable_role: product-owner
primary_workspace: customer-portal
affected_workspaces:
  - customer-portal
allowed_paths:
  - apps/customer-portal/src/app/(account)
  - apps/customer-portal/src/features/account-profile
  - apps/customer-portal/src/features/account-security
  - apps/customer-portal/src/features/privacy
  - apps/customer-portal/src/lib
  - apps/customer-portal/tests
  - docs/work/items/VFBIZ-0070.md
  - WORK.md
depends_on:
  - VFBIZ-0069
controlled_signals:
  - authentication
  - customer-data
  - customer-privacy
exclusive_resources: []
required_checks:
  - npm run verify:apps
  - npm run verify:apps:e2e
revision: 3
review_date: "2026-08-24"
updated_at: "2026-07-24T08:35:17.856Z"
---

# Outcome

Khách hàng quản lý profile, MFA/session, consent và DSAR với fail-closed
authorization, optimistic concurrency và provider reconciliation rõ ràng.

## Constraints

- Không thay đổi Garage, chatbot, Trip Planner, commerce hoặc mobile.
- Keycloak tiếp tục sở hữu credential và MFA; PostgreSQL chỉ giữ nghiệp vụ/audit cần thiết.
- Device/IP metadata không được dùng làm identity hoặc authorization factor.

## Done when

- Profile, security, sessions, privacy và data-request journeys đạt acceptance.
- Không có token/PII trong browser storage, bundle hoặc log.
- Browser, security và accessibility evidence đầy đủ.

## Checkpoint

- Waiting for VFBIZ-0069.
- Exact next action: transition to ready after dependency is done.

## Evidence

- [ ] Browser and security acceptance.
