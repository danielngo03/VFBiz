---
id: VFBIZ-0031
title: Consent atomicity và PostgreSQL account integration tests
status: done
mode: controlled
priority: P0
owner_team: customer-product
accountable_role: privacy-owner
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/customer
  - backend/api/prisma/models/customer.prisma
  - backend/api/prisma/migrations
  - backend/api/scripts/verify-migrations.sh
  - backend/api/test/integration/customer
  - backend/api/test/e2e/customer
depends_on:
  - VFBIZ-0014
controlled_signals:
  - consent
  - customer-data
  - pii
exclusive_resources:
  - database-migration
required_checks:
  - npm run verify:api
  - npm run test:migrations --workspace @vfbiz/api
  - npm run governance:check
revision: 6
review_date: "2026-08-23"
updated_at: "2026-07-23T16:29:30.314Z"
---

# Outcome

Consent batch hoặc được ghi toàn bộ hoặc không ghi gì; test bằng PostgreSQL thật
chứng minh idempotency, ordering và concurrent account/Garage invariants.

## Constraints

- Duplicate purpose bị từ chối trước persistence.
- Không dùng `skipDuplicates` để che conflict business.
- Policy consent/primary transition phải test được ngoài Prisma adapter.
- Không dùng production PII trong fixture.

## Done when

- Batch preflight và transaction loại partial mutation.
- Current consent có causal revision/sequence deterministic.
- Integration tests bao phủ concurrent provisioning, consent conflict,
  cross-subject Garage và concurrent primary transition.
- Retry serialization hữu hạn, không nuốt lỗi không xác định.

## Checkpoint

- Exact next action: viết regression test duplicate-purpose/partial-write rồi
  trích policy thuần tối thiểu cần thiết.

## Evidence

- [x] `npm run verify:api` — pass 2026-07-23; 130 unit tests, 47 E2E tests, lint, typecheck, Prisma validation và build đạt.
- [x] `npm run test:migrations --workspace @vfbiz/api` — pass 2026-07-23; 5 PostgreSQL integration tests cùng clean/legacy replay đạt.
- [x] `npm run governance:check` — pass 2026-07-23; 55 provider-neutral context scenarios đạt.

### ready — 2026-07-23T08:30:40.977Z

Account scopes are complete; duplicate-purpose and concurrency risks now have reproducible acceptance criteria.

### active — 2026-07-23T08:30:41.233Z

Implement consent atomicity and observed PostgreSQL account integration tests in an independent customer lane.

### active — 2026-07-23T09:12:45.765Z

Observed 2026-07-23: consent duplicate-purpose preflight, serializable transaction wrapper, bounded retry and customer E2E overrides are code-complete; npm run verify:api passed and governance:check passed. Acceptance is not done because deterministic causal revision/sequence for current consent still needs a database migration and focused PostgreSQL integration evidence. Exact next action: open a database-migration lane after VFBIZ-0029 lease release, add consent revision/sequence migration and observed concurrency tests.

### review — 2026-07-23T11:13:45.683Z

Consent sequence, idempotent concurrency và migration replay đã có observed evidence; chờ Privacy Owner review.

### done — 2026-07-23T16:29:30.314Z

Final approver cho phép tiếp tục; consent atomicity, causal ordering và PostgreSQL evidence đã đạt.
