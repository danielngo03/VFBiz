---
id: VFBIZ-0027
title: OIDC scope policy và authorization guard
status: done
mode: controlled
priority: P0
owner_team: api-foundation
accountable_role: security-owner
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/platform/security
  - backend/api/test/unit/platform/security
depends_on:
  - VFBIZ-0013
controlled_signals:
  - authentication
  - authorization
  - customer-data
exclusive_resources: []
required_checks:
  - npm run verify:api
  - npm run governance:check
revision: 5
review_date: "2026-08-23"
updated_at: "2026-07-23T07:58:44.812Z"
---

# Outcome

API có policy primitive và guard typed để route khai báo scope bắt buộc; token
đúng issuer/audience/realm nhưng thiếu scope phải bị từ chối trước controller.

## Constraints

- Không hardcode scope theo URL trong global guard.
- Không tin scope do client body/header khai; chỉ dùng principal đã verify.
- Scope là least-privilege theo operation, không dùng wildcard mặc định.
- Lane này chỉ tạo platform primitive; annotation trên Customer route thuộc
  work item VFBIZ-0028.

## Done when

- `RequireScopes` metadata và guard hỗ trợ all-of/any-of rõ ràng.
- Missing/malformed/wrong-client scope trả typed 403, không làm lộ claim.
- Public route chỉ bypass khi có explicit public metadata.
- Unit tests bao phủ issuer đúng nhưng scope sai, scope trùng và nhiều scope.

## Checkpoint

- Scope policy primitive và global guard đã hoàn tất trong
  `src/platform/security`; Customer route adoption vẫn thuộc VFBIZ-0028.
- `@Public()` xung đột với `@RequireScopes()` bị fail-closed.
- Policy bind đồng thời operation scope và allowlist `authorizedParty`; cùng
  scope từ client khác vẫn bị từ chối.
- Exact next action: VFBIZ-0028 áp dụng scope cụ thể lên Account, Consent và
  Garage controller, kèm negative E2E theo operation.

## Evidence

- [x] `npm run verify:api` — 20 unit suites/85 tests, 6 E2E suites/23 tests,
  ESLint, TypeScript, Prisma validation và Nest build đều đạt ngày 2026-07-23.
- [x] `npm run governance:check` — 50 provider-neutral context scenarios và
  toàn bộ instruction/role/skill/work schema checks đạt ngày 2026-07-23.
- [x] Focused scope tests — 2 suites/13 tests đạt; bao phủ public-policy
  conflict, malformed scope, duplicate scope, all-of/any-of và wrong client.

### ready — 2026-07-23T07:36:32.412Z

Account/Vehicle audit confirmed missing operation-scope enforcement as P0 prerequisite for authenticated chatbot.

### active — 2026-07-23T07:36:32.697Z

Start platform-only authorization primitive; Customer route adoption remains VFBIZ-0028.

### review — 2026-07-23T07:58:44.545Z

Risk review completed; one bounded fix cycle closed public/scope conflict and authorized-party binding.

### done — 2026-07-23T07:58:44.812Z

Platform scope guard accepted with full API and governance evidence; route adoption continues in VFBIZ-0028.
