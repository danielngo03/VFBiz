---
id: VFBIZ-0061
title: Tách tài liệu Workforce API và chuẩn hóa luồng đăng nhập
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
  - backend/api/src/platform/config
  - backend/api/src/main.ts
  - backend/api/.env.example
  - backend/api/test/contract
  - backend/api/test/unit/platform/config
  - backend/api/docs/workforce-authorization.md
  - apps/workforce-portal/README.md
  - contracts/openapi/workforce-v1.yaml
  - docs/work/items/VFBIZ-0061.md
  - docs/INDEX.md
  - docs/INDEX.json
  - WORK.md
depends_on: []
controlled_signals:
  - authentication
  - authorization
  - workforce-admin
exclusive_resources:
  - workforce-contract
required_checks:
  - npm run verify:api
  - npm run verify:apps
  - npm run verify:governance
revision: 5
review_date: "2026-08-24"
updated_at: "2026-07-24T04:58:08.605Z"
---

# Outcome

Public API và Workforce API có Scalar riêng; workforce login đi qua Next.js BFF
và internal contract không khuyến khích browser trực tiếp sở hữu token.

## Constraints

- Không đưa endpoint workforce vào Public API document.
- Không tạo password/token/refresh endpoint trong NestJS.
- Không bật Workforce Scalar ở production.
- Không lưu hoặc persist workforce credential trong Scalar.

## Done when

- Local development phục vụ Workforce Scalar và contract YAML ở URL ổn định.
- Production configuration từ chối bật Workforce Scalar.
- Contract mô tả đúng BFF login, bearer boundary và dynamic authorization.
- Public OpenAPI tiếp tục không chứa `/api/v1/workforce/**`.

## Checkpoint

- Đã thêm read-only Workforce Scalar tại `/reference/workforce`.
- Đã chuyển Customer Scalar sang `/reference/customer`; `/reference` chỉ là
  exact redirect, không còn là prefix middleware có thể nuốt Workforce route.
- Đã bổ sung local/staging server, tag hierarchy và BFF login guidance.
- Đã khóa production-off bằng environment validation.
- Exact next action: review evidence và đóng work item.

## Evidence

- [x] `npm run verify:api` — 42 suites/199 tests, 59 E2E, Prisma validate và build đạt.
- [x] `npm run verify:apps` — Customer Portal tests và Workforce Portal 12 tests/build đạt.
- [x] `npm run verify:governance` — 56 routing scenarios, docs index và ba OpenAPI contract đạt.
