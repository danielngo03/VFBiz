---
id: VFBIZ-0064
title: Hoàn thiện Workforce API contract và HTTP E2E
status: proposed
mode: controlled
priority: P0
owner_team: api-foundation
accountable_role: security-owner
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/access
  - backend/api/test/e2e/access
  - backend/api/test/contract
  - contracts/openapi/workforce-v1.yaml
  - docs/work/items/VFBIZ-0064.md
  - WORK.md
depends_on:
  - VFBIZ-0056
controlled_signals:
  - authorization
  - workforce-admin
  - public-contract
exclusive_resources:
  - workforce-contract
required_checks:
  - npm run verify:api
  - npm run contracts:lint
  - npm run governance:check
revision: 1
review_date: "2026-08-24"
---

# Outcome

Workforce OpenAPI phản ánh chính xác runtime routes, capability requirements và
mọi response quan trọng; HTTP E2E chứng minh deny-by-default, scope, MFA,
maker-checker và optimistic concurrency.

## Constraints

- Contract vẫn tách khỏi Customer/Public API.
- Test phải đi qua HTTP guard/filter/validation thật, không chỉ gọi service.
- Không dùng production identity hoặc PII trong fixture.
- Mọi mutation giữ idempotency, expected version, reason và correlation ID.

## Done when

- Runtime route inventory và reviewed Workforce OpenAPI không drift.
- Scalar hiển thị rõ 400, 401, 403, 404, 409/412, 428 và 503 theo operation.
- E2E bao phủ missing/expired token, wrong realm/audience, missing capability,
  stale version, self-approval, cross-scope và database unavailable.
- Problem Details không lộ policy internals hoặc sensitive identity data.

## Checkpoint

- Audit hiện tại xác nhận contract có 17 operations nhưng phần lớn chỉ khai báo
  success + `default`; chưa có route-level Workforce HTTP E2E.
- Exact next action: hoàn tất durable idempotency của VFBIZ-0056, sau đó khóa
  response taxonomy và tạo runtime/contract parity inventory.

## Evidence

- [ ] `npm run verify:api` — chờ route-level Workforce HTTP E2E.
- [ ] `npm run contracts:lint` — chờ explicit response taxonomy.
- [ ] `npm run governance:check` — chạy khi dependency hoàn tất.
