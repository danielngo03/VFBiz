---
id: VFBIZ-0018
title: Conversation Runtime persistence integration
status: proposed
mode: controlled
priority: P0
owner_team: customer-engagement
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/prisma/models/engagement.prisma
  - backend/api/prisma/migrations
  - backend/api/src/modules/engagement/infrastructure
  - backend/api/src/modules/engagement/engagement.module.ts
  - backend/api/scripts
  - backend/api/test/e2e/engagement
  - backend/api/test/integration/engagement
depends_on:
  - VFBIZ-0017
  - VFBIZ-0032
controlled_signals:
  - customer-conversation
  - session-concurrency
  - migration
  - schema
  - pii
exclusive_resources:
  - database-migration
required_checks:
  - npm run test:migrations --workspace @vfbiz/api
  - npm run verify:api
revision: 1
review_date: "2026-08-23"
---

# Outcome

Persistence của Conversation Runtime được triển khai bằng migration có replay,
constraint/index và recovery evidence phù hợp với application core VFBIZ-0017.

API Foundation phối hợp review migration/transaction strategy; Customer
Engagement vẫn là owner duy nhất của schema và persistence adapter trong bounded
context này.

## Constraints

- Chỉ integration owner ghi migration và giữ `database-migration` lease.
- Không đổi public/AI contract trong lane này.
- Legacy conversation projection không được backfill bằng identity, citation
  hoặc source giả.

## Done when

- Clean database và legacy fixture áp toàn bộ migration không drift.
- Unique/partial index bảo vệ idempotency, monotonic sequence, active claim và
  handoff lifecycle như schema cho phép.
- Migration fail closed khi dữ liệu legacy không thể chuyển an toàn.
- PostgreSQL integration test chứng minh transaction, OCC/fencing và purge.

## Checkpoint

- Exact next action: chỉ start sau VFBIZ-0017; review SQL và fixture trước
  `migrate deploy`.

## Evidence

- [ ] `npm run test:migrations --workspace @vfbiz/api` — add evidence reference
- [ ] `npm run verify:api` — add evidence reference
