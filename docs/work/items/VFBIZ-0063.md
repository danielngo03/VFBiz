---
id: VFBIZ-0063
title: Tách namespace Scalar cho Customer và Workforce
status: done
mode: controlled
priority: P0
owner_team: api-foundation
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
  - workforce-portal
allowed_paths:
  - backend/api/src/platform/openapi
  - backend/api/test/contract
  - backend/api/README.md
  - backend/api/docs/workforce-authorization.md
  - apps/workforce-portal/README.md
  - contracts/openapi/public-v1.yaml
  - docs/work/items/VFBIZ-0061.md
  - docs/work/items/VFBIZ-0063.md
  - WORK.md
depends_on: []
controlled_signals:
  - authentication
  - authorization
  - workforce-admin
exclusive_resources:
  - workforce-contract
  - public-contract
required_checks:
  - npm run verify:api
  - npm run contracts:lint
  - npm run governance:check
revision: 5
review_date: "2026-08-24"
updated_at: "2026-07-24T05:07:39.574Z"
---

# Outcome

Customer Scalar và Workforce Scalar dùng namespace không chồng lấn, render đúng
contract tương ứng và không thể bị middleware Customer bắt nhầm.

## Constraints

- Giữ `/reference` làm redirect tương thích, không làm middleware mount point.
- Public document không chứa workforce endpoint.
- Workforce document không chứa customer auth/session endpoint.
- Internal reference không persist token hoặc gửi contract tới Scalar Agent.

## Done when

- `/reference/customer` render `VFBiz Customer API`.
- `/reference/workforce` render `VFBiz Workforce API`.
- `/reference` trả 308 tới `/reference/customer`.
- Customer và Workforce dùng OpenAPI URL riêng.
- Contract test, browser snapshot và route smoke test đều chứng minh isolation.

## Checkpoint

- Đã đổi Customer Scalar và Swagger/OpenAPI sang namespace `/customer`.
- Đã thêm exact redirects cho URL cũ.
- Đã tắt Scalar Agent ở cả hai reference và dùng favicon data URI.
- Browser snapshot xác nhận hai title/sidebar/contract khác nhau.
- Exact next action: đóng work item sau full API/governance gate.

## Evidence

- [x] `npm run verify:api` — API lint/typecheck/tests/E2E/Prisma/build đạt.
- [x] `npm run contracts:lint` — ba OpenAPI contract và runtime schemas đạt.
- [x] `npm run governance:check` — work/docs/routing/agent governance đạt.
