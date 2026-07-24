---
id: VFBIZ-0050
title: Tính toàn vẹn mutation Customer Profile và Garage
status: done
mode: controlled
priority: P0
owner_team: customer-product
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/customer
  - backend/api/test/integration/customer
  - backend/api/test/e2e/customer
  - backend/api/docs/identity-and-account.md
  - backend/api/docs/data-model.md
  - contracts/openapi/public-v1.yaml
  - packages/api-client
  - docs/work/items
  - WORK.md
depends_on: []
controlled_signals:
  - customer-data
  - pii
  - authorization
exclusive_resources: []
required_checks:
  - npm run verify:api
  - npm run test:migrations --workspace @vfbiz/api
  - npm run contracts:lint
  - npm run governance:check
revision: 6
review_date: "2026-08-24"
updated_at: "2026-07-23T17:19:05.819Z"
---

# Outcome

Profile và Garage mutation từ chối identity/profile không còn active tại thời
điểm commit, dùng optimistic concurrency và ghi business state, audit cùng
outbox trong một transaction.

## Constraints

- Không lưu profile value, nickname, token hoặc PII trong audit/outbox.
- Không thay đổi public route hoặc quyền sở hữu dữ liệu.
- Idempotent Garage create không tạo lại audit/outbox khi replay.
- Không dùng provider call bên trong database transaction.

## Done when

- Suspend identity trước mutation làm Profile/Garage fail closed.
- Profile update ghi một audit và một outbox event cùng state change.
- Garage create/update/archive ghi audit và versioned outbox event cùng state
  change; replay không nhân đôi evidence.
- Migration, PostgreSQL integration, API/E2E và contract gates đạt.

## Checkpoint

- Exact next action: không còn; work item đã hoàn thành. Mọi capability ownership
  hoặc verified VIN mới phải mở controlled work item riêng.

## Evidence

- [x] `npm run verify:api` — 32 unit suites/153 tests, 8 E2E suites/54 tests,
  lint, typecheck, Prisma validate và build đạt ngày 2026-07-24.
- [x] `npm run test:migrations --workspace @vfbiz/api` — 11 migration clean
  replay, drift, PostgreSQL integration và legacy backfill đạt ngày 2026-07-24.
- [x] `npm run contracts:lint` — OpenAPI lint, runtime JSON schema và generated
  TypeScript types đạt ngày 2026-07-24.
- [x] `npm run governance:check` — 52 durable documents, 47 WorkItemV2,
  instruction budgets, roles, skills và 55 routing scenarios đạt ngày
  2026-07-24.

### ready — 2026-07-23T17:18:41.191Z

Boundary Customer đã xác định; acceptance, allowed paths và kiểm thử controlled đầy đủ.

### active — 2026-07-23T17:18:41.459Z

Triển khai atomic Profile/Garage mutation, audit/outbox và suspend guard.

### review — 2026-07-23T17:18:41.727Z

Implementation và runtime gates đạt; chờ governance evidence cuối và focused review.

### done — 2026-07-23T17:19:05.819Z

Profile/Garage mutation đã atomically commit state + redacted audit + outbox, fail closed khi subject bị suspend; toàn bộ required checks đạt.
