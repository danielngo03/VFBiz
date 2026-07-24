---
id: VFBIZ-0058
title: Workforce authorization management UX
status: proposed
mode: controlled
priority: P0
owner_team: workforce-experience
accountable_role: business-owner
primary_workspace: workforce-portal
affected_workspaces:
  - workforce-portal
  - api
allowed_paths:
  - apps/workforce-portal
  - contracts/openapi/workforce-v1.yaml
  - docs/work/items/VFBIZ-0058.md
depends_on:
  - VFBIZ-0056
  - VFBIZ-0057
controlled_signals:
  - authorization
  - workforce-admin
exclusive_resources:
  - public-contract
required_checks:
  - npm run verify:apps
  - npm run contracts:lint
revision: 2
review_date: "2026-08-24"
updated_at: "2026-07-24T20:10:00.000+07:00"
---

# Outcome

Role matrix, scoped assignment, approval inbox và audit timeline hoạt động qua
generated workforce client.

## Constraints

- UI capability check chỉ là presentation hint.
- Privileged mutation luôn qua approved change request.
- UI tiếng Việt, capability key giữ nguyên tiếng Anh và đạt WCAG AA.

## Done when

- Read-only, editor và approver journeys có test.
- Self-elevation/last-admin/scope warning rõ ràng.
- Direct unauthorized API call vẫn bị NestJS từ chối.

## Checkpoint

- Read-only Role, Assignment, Approval và Audit views đã nối API qua server DAL.
- Portal kiểm capability trước khi fetch, lọc response theo runtime schema và
  hiển thị trạng thái forbidden/unavailable mà không đưa token ra client.
- Mutation UI chưa được mở. Work item giữ `proposed` cho đến khi VFBIZ-0056 có
  durable idempotency và portal có CSRF/origin, OCC/maker-checker E2E.
- Exact next action: khóa mutation contract và thêm secure Server Action/Route
  Handler cho role diff/change request trước khi chuyển work item sang `ready`.

## Evidence

- [x] Portal lint, typecheck, 12 unit tests, production build và Playwright 2/2.
- [x] Static bundle scan không phát hiện access token, refresh token hoặc vault
  key trong client bundle.
- [ ] Mutation, accessibility matrix và maker-checker E2E evidence.
