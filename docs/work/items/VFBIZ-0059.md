---
id: VFBIZ-0059
title: Migrate workforce release authorization to capabilities
status: proposed
mode: controlled
priority: P0
owner_team: api-foundation
accountable_role: security-owner
primary_workspace: api
affected_workspaces:
  - api
  - infra
allowed_paths:
  - backend/api/src/modules/product
  - backend/api/src/platform/security
  - backend/api/test/e2e/product
  - infra/local/keycloak
  - docs/work/items/VFBIZ-0059.md
depends_on:
  - VFBIZ-0056
controlled_signals:
  - authorization
  - workforce-admin
  - vehicle-catalog
exclusive_resources: []
required_checks:
  - npm run verify:api
  - npm run governance:check
revision: 3
review_date: "2026-08-24"
updated_at: "2026-07-24T20:10:00.000+07:00"
---

# Outcome

Catalog/commercial release endpoints dùng capability decision thay hard-coded
Keycloak realm role, giữ nguyên URL và separation of duties.

## Constraints

- Shadow compare trước enforcement cutover.
- Không giảm MFA hoặc object authorization hiện có.
- Keycloak role chỉ là migration input, không còn business authority.

## Done when

- Decision parity suite đạt.
- Current operator/reviewer mapping thành system roles.
- Không Operations endpoint nào còn `@RequireRoles`.

## Checkpoint

- Capability mapping và entitlement runtime đã tồn tại, nhưng release controller
  chủ động giữ `@RequireRoles` để không khóa toàn bộ operator trước khi có
  bootstrap/backfill assignment và shadow comparison thật.
- Work item chưa chuyển `ready/review` vì dependency VFBIZ-0056 vẫn active.
- Exact next action: bootstrap tối thiểu hai global administrators, import legacy
  assignments, chạy shadow parity trên runtime DB rồi mới cutover controller.

## Evidence

- [x] API unit/integration suite: 181/181.
- [x] API E2E suite: 59/59 cho authorization boundary hiện hành.
- [ ] Runtime assignment backfill và shadow comparison.
- [ ] Capability cutover; legacy role enforcement vẫn active để fail safely.
