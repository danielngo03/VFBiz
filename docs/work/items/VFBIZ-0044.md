---
id: VFBIZ-0044
title: Materialize OIDC customer session projection
status: done
mode: controlled
priority: P0
owner_team: api-foundation
accountable_role: security-owner
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/access
  - backend/api/src/platform/security
  - backend/api/test/integration/access
  - backend/api/test/e2e/access
  - backend/api/docs/identity-and-account.md
  - docs/work/items
depends_on:
  - VFBIZ-0041
controlled_signals:
  - authentication
  - authorization
  - pii
exclusive_resources: []
required_checks:
  - npm run verify:api
  - npm run governance:check
revision: 6
review_date: "2026-07-23"
updated_at: "2026-07-23T16:28:54.369Z"
---

# Outcome

OIDC callback/refresh đã verify sẽ materialize hoặc cập nhật đúng customer
session projection để `/me/sessions`, local deny và revoke lifecycle phản ánh
phiên đăng nhập thật.

## Constraints

- Không lưu raw access token, refresh token, cookie, full IP hoặc full claims.
- Session reference chỉ lấy từ verified `sid`; thiếu `sid` phải có typed policy.
- Concurrent callback/refresh và out-of-order observation phải idempotent.
- Provider session secret cần vault reference; không ghi secret vào PostgreSQL.

## Done when

- First callback tạo IdentitySubject và SessionProjection atomically.
- Refresh cập nhật expiry/last-seen bằng monotonic revision.
- Logout/revoke current session cập nhật local deny state.
- Tests bao phủ missing sid, concurrent callback, stale refresh và CIAM outage.

## Checkpoint

- Verifier trả `iat`, `exp`, `auth_time` và `sid` đã xác minh; thiếu `sid`
  làm customer callback fail closed.
- Callback atomically upsert IdentitySubject và SessionProjection; refresh chỉ
  áp observation revision mới hơn trong transaction `SERIALIZABLE`.
- Local logout revoke current projection trước khi xóa cookie; CIAM outage
  không làm local logout thất bại.
- Exact next action: final approver review evidence; opaque server-side BFF
  token vault vẫn là production hardening riêng.

## Evidence

- [x] `npm run verify:api` — 30 suite/145 unit tests, 8 suite/49 E2E tests,
  lint/typecheck/Prisma/build đạt ngày 2026-07-23.
- [x] `npm run governance:check` — docs/work/provider-neutral governance đạt
  sau khi regenerate index.
- [x] `npm run test:migrations --workspace @vfbiz/api` — clean/legacy replay,
  drift và 9 PostgreSQL integration tests đạt.

### ready — 2026-07-23T16:19:13.456Z

Dependency OIDC foundation đã hoàn tất; acceptance và allowed paths đã rõ.

### active — 2026-07-23T16:19:13.765Z

Bắt đầu materialize verified OIDC session projection trong Access boundary.

### review — 2026-07-23T16:28:54.074Z

OIDC session projection, temporal claims, stale refresh và local logout deny đã có observed evidence.

### done — 2026-07-23T16:28:54.369Z

Final approver yêu cầu tiếp tục foundation; production opaque BFF token vault được giữ thành hardening riêng.
