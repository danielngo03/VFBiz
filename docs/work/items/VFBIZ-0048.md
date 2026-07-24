---
id: VFBIZ-0048
title: Chuẩn hóa retry cho PostgreSQL transaction conflict
status: review
mode: bounded
priority: P0
owner_team: api-foundation
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/platform/database
  - backend/api/src/modules/customer/infrastructure/persistence
  - backend/api/test
  - docs/work/items
  - WORK.md
depends_on: []
controlled_signals:
  - customer-data
exclusive_resources: []
required_checks:
  - npm run verify:api
  - npm run test:migrations --workspace @vfbiz/api
  - npm run governance:check
revision: 2
review_date: "2026-07-23"
updated_at: "2026-07-23T16:08:33.119Z"
---

# Outcome

Các transaction `SERIALIZABLE` của Customer foundation retry có giới hạn cho
cả Prisma error code và `DriverAdapterError` từ PostgreSQL adapter, không fail
ngẫu nhiên khi hai request hợp lệ ghi đồng thời.

## Constraints

- Chỉ retry unique/write conflict được xác định bằng typed code/kind.
- Không retry validation, authorization, business conflict hoặc lỗi không rõ.
- Giữ tối đa ba attempt; không tạo retry loop vô hạn.

## Done when

- Retry classifier dùng chung cho Account và Garage repository.
- Có regression test cho `P2002`, `P2034`, `TransactionWriteConflict` và
  negative error.
- PostgreSQL integration concurrency chạy ổn định qua migration gate.

## Checkpoint

- Migration gate phát hiện `DriverAdapterError` có
  `cause.kind=TransactionWriteConflict` chưa được classifier hiện tại nhận.
- Classifier dùng chung hiện nhận Prisma `P2002`/`P2034` và typed driver
  `UniqueConstraintViolation`/`TransactionWriteConflict`, không dựa vào message.
- Account và Garage repository giữ tối đa ba attempt.
- Exact next action: Engineering Lead review retry taxonomy và evidence.

## Evidence

- [x] Focused lint/typecheck và 8 classifier regression cases đạt.
- [x] `npm run test:migrations --workspace @vfbiz/api` — clean/legacy replay,
  schema drift và 7 PostgreSQL integration tests đạt sau fix.
- [x] `npm run verify:api` — 30 suite/143 unit tests, 8 suite/49 E2E tests,
  Prisma validation và build đạt.
- [x] `npm run governance:check` — 45 WorkItemV2 và 55 provider-neutral
  scenarios đạt.
