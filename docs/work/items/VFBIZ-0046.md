---
id: VFBIZ-0046
title: Database readiness health cho API foundation
status: review
mode: bounded
priority: P0
owner_team: api-foundation
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/platform/health
  - backend/api/test/e2e/platform
  - backend/api/docs/architecture.md
  - contracts/openapi
  - docs/work/items
  - WORK.md
depends_on: []
controlled_signals:
  - availability
  - public-contract
exclusive_resources:
  - public-contract
required_checks:
  - npm run verify:api
  - npm run contracts:lint
  - npm run governance:check
revision: 4
review_date: "2026-07-23"
updated_at: "2026-07-23T16:08:32.507Z"
---

# Outcome

Load balancer và developer phân biệt được process còn sống với API thực sự sẵn
sàng truy cập PostgreSQL; database mất kết nối phải fail readiness nhưng không
làm liveness fail.

## Constraints

- Readiness không trả connection string, SQL error hoặc topology nội bộ.
- Liveness không gọi database hay provider.
- Chưa thêm Redis/CIAM vào readiness khi chúng chưa là dependency bắt buộc cho
  mọi request nền tảng.

## Done when

- `GET /api/v1/health/live` vẫn trả `200` chỉ dựa trên process.
- `GET /api/v1/health/ready` chạy lightweight PostgreSQL probe.
- Database up trả `200`; database error trả RFC Problem Details `503`.
- Runtime OpenAPI và reviewed public contract có cùng operation.

## Checkpoint

- `GET /api/v1/health/ready` chạy `SELECT 1` qua Prisma và chỉ công bố trạng
  thái dependency, không lộ SQL/connection/error.
- E2E quan sát cả `200` khi database up và RFC Problem Details `503` khi probe
  lỗi; liveness vẫn độc lập database.
- Reviewed OpenAPI và runtime inventory có cùng operation.
- Exact next action: Engineering Lead review behavior và evidence.

## Evidence

- [x] `npm run verify:api` — 30 suite/143 unit tests, 8 suite/49 E2E tests,
  Prisma validation và build đạt.
- [x] `npm run contracts:lint` — public/internal OpenAPI không warning; runtime
  contract schemas compile.
- [x] `npm run governance:check` — 45 WorkItemV2 và 55 provider-neutral
  scenarios đạt.
