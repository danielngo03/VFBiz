---
id: VFBIZ-0041
title: Hoàn thiện customer OIDC và browser session foundation
status: done
mode: controlled
priority: P0
owner_team: api-foundation
accountable_role: security-owner
primary_workspace: api
affected_workspaces:
  - api
  - customer-portal
  - root
allowed_paths:
  - backend/api/src/modules/access
  - backend/api/src/platform/security
  - backend/api/src/platform/http
  - backend/api/src/platform/config
  - backend/api/src/bootstrap
  - backend/api/test/e2e/access
  - backend/api/test/unit/platform
  - backend/api/.env.example
  - backend/api/docs/identity-and-account.md
  - apps/customer-portal
  - contracts/openapi
  - backend/api/src/platform/openapi
  - backend/api/test/contract
depends_on:
  - VFBIZ-0029
  - VFBIZ-0047
controlled_signals:
  - authentication
  - authorization
  - pii
  - public-contract
exclusive_resources:
  - public-contract
required_checks:
  - npm run verify:api
  - npm run verify:apps
  - npm run contracts:lint
  - npm run governance:check
revision: 8
review_date: "2026-08-23"
updated_at: "2026-07-23T16:19:13.124Z"
---

# Outcome

Khách hàng có thể bắt đầu đăng nhập, đăng ký, khôi phục mật khẩu, hoàn tất
Authorization Code + PKCE và đăng xuất qua các entrypoint cùng origin; API xác
minh đúng customer issuer/client, bảo vệ mutation dùng cookie bằng CSRF và
không nhận password.

## Constraints

- CIAM/Keycloak tiếp tục sở hữu credential, email verification, recovery và MFA.
- Chỉ chấp nhận redirect trở lại customer portal origin đã cấu hình.
- Không log hoặc lưu access token, refresh token, cookie hay authorization code.
- Public contract chỉ công bố route thực sự tồn tại; không tạo endpoint giả.
- Browser session hiện tại là foundation cho localhost/staging. Trước
  production phải thay token cookie bằng opaque server-side session theo một
  work item có secret storage và revocation design riêng.

## Done when

- Login/register dùng state, PKCE S256 và redirect allowlist.
- Callback fail closed khi state, code, issuer, realm hoặc authorized party sai.
- Cookie có `HttpOnly`, `SameSite`, `Secure` theo environment và thời hạn hữu hạn.
- Cookie-authenticated mutation cần double-submit CSRF kể cả route public logout.
- Logout xóa đầy đủ cookie và không nhận password/token trong request body.
- Portal tạo same-origin auth URL và không cho open redirect.
- Runtime OpenAPI, reviewed OpenAPI và test mô tả cùng route/account boundary.
- API, app, contract và governance gates đạt.

## Checkpoint

- Native Keycloak và real-provider browser flow đã loại bỏ blocker ban đầu.
- Login/register/reset/callback/refresh/logout, negative auth/CSRF,
  cookie redaction và public contract đã có observed evidence.
- Exact next action: đóng foundation sau chỉ đạo tiếp tục của final approver;
  session projection materialization được theo dõi riêng tại VFBIZ-0044.

## Evidence

- [x] `npm run verify:api` — pass 2026-07-23; 143 unit tests, 49 E2E tests,
  lint, typecheck, Prisma validation và build đạt.
- [x] `npm run verify:apps` — pass 2026-07-23; Customer Portal và Operations Admin typecheck/test đạt.
- [x] `npm run contracts:lint` — pass 2026-07-23; public/internal OpenAPI và runtime contract schema đạt.
- [x] `npm run governance:check` — pass 2026-07-23; docs index, work schema và 55 routing scenarios đạt.
- [x] Native Keycloak check và real browser acceptance — discovery, JWKS,
  PKCE, callback, refresh, logout và cookie policy đạt với synthetic user đã
  được xóa sau kiểm thử.

### ready — 2026-07-23T11:05:48.823Z

Identity flow và route inventory đã được audit; acceptance, path và security boundary đã rõ.

### active — 2026-07-23T11:05:49.094Z

Tiếp tục lane OIDC/CSRF đang dở, không mở chatbot hoặc Trip Planner.

### review — 2026-07-23T11:13:46.076Z

OIDC/PKCE, refresh/logout, CSRF và contract parity đã có observed evidence; chờ Security Owner review.

### audit finding — 2026-07-23

Local Keycloak chưa chạy, Java runtime chưa tồn tại và customer realm import
đang allow callback `localhost:5173/bff/callback` trong khi API sử dụng
`127.0.0.1:8000/auth/customer/callback`. Mock/contract evidence không đủ chứng
minh Account flow end-to-end; VFBIZ-0047 phải hoàn tất trước acceptance.

### blocked — 2026-07-23T15:40:24.003Z

Chờ VFBIZ-0047 cung cấp native Keycloak và real-provider OIDC acceptance; mock-only evidence không đủ.

### review — 2026-07-23T16:19:12.855Z

Blocker native Keycloak đã được VFBIZ-0047 giải quyết; full security/contract gates đạt.

### done — 2026-07-23T16:19:13.124Z

Final approver cho phép tiếp tục foundation; OIDC session projection được tách sang VFBIZ-0044.
