---
id: VFBIZ-0028
title: Account, consent và Garage scope enforcement
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
  - backend/api/test/e2e/customer
depends_on:
  - VFBIZ-0027
controlled_signals:
  - authorization
  - consent
  - customer-data
  - customer-garage
  - pii
exclusive_resources: []
required_checks:
  - npm run verify:api
  - npm run governance:check
revision: 5
review_date: "2026-08-23"
updated_at: "2026-07-23T08:13:19.844Z"
---

# Outcome

Mỗi Account/Consent/DSAR/Garage operation yêu cầu đúng OIDC scope và subject
ownership; realm đúng nhưng thiếu capability không thể đọc hoặc mutate dữ liệu.

## Constraints

- Dùng primitive từ VFBIZ-0027, không tạo guard riêng trong Customer module.
- Không dùng role rộng thay cho operation scope.
- Không trả khác biệt giúp attacker suy đoán object của subject khác.
- Garage tự khai báo không được nâng thành verified ownership.

## Done when

- Scope matrix được khai báo cạnh controller/use case và có test negative.
- Customer A không đọc/sửa account, consent, data request hoặc Garage của B.
- Missing scope, wrong scope và wrong realm đều fail closed.
- Authorization evidence không chứa raw token hoặc PII.

## Checkpoint

- Scope matrix đã được áp dụng cho 9 Account/Consent/DSAR/Garage operation:
  `profile:read/write`, `consent:read/write`, `data-request:create` và
  `garage:read/write`.
- `vfbiz-customer-bff` và `vfbiz-mobile` là authorized-party allowlist; đúng
  scope từ client khác vẫn bị từ chối trước repository.
- Subject-scoped application/repository authorization giữ nguyên; Garage vẫn
  chỉ là self-reported reference.
- Exact next action: VFBIZ-0030 rà contract parity sau VFBIZ-0029; VFBIZ-0031
  kiểm consent/garage invariant trên PostgreSQL thật.

## Evidence

- [x] `npm run verify:api` — 21 unit suites/96 tests, 6 E2E suites/33 tests,
  ESLint, TypeScript, Prisma validation và Nest build đều đạt ngày 2026-07-23.
- [x] `npm run governance:check` — instruction, role, skill, WorkItemV2 và 50
  provider-neutral routing scenarios đều đạt ngày 2026-07-23.
- [x] Independent risk review — một P2 về `azp` coverage được sửa trong đúng
  một vòng; E2E chứng minh wrong client fail-closed và `vfbiz-mobile` hợp lệ.

### ready — 2026-07-23T07:59:34.778Z

OIDC scope primitive VFBIZ-0027 is complete; current Customer controllers and tests provide a bounded route-adoption lane.

### active — 2026-07-23T07:59:35.088Z

Apply operation scopes to Account, Consent, DSAR and Garage routes; add negative E2E without changing public contract.

### review — 2026-07-23T08:13:19.560Z

Independent risk review completed; the sole P2 azp coverage gap was fixed in one bounded cycle.

### done — 2026-07-23T08:13:19.844Z

Account, Consent, DSAR and Garage operations now enforce scope, realm, authorized party and subject boundaries with full API/governance evidence.
