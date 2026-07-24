---
id: VFBIZ-0066
title: Customer Portal opaque BFF session và revocation reconciliation
status: done
mode: controlled
priority: P0
owner_team: customer-web-experience
accountable_role: security-owner
primary_workspace: customer-portal
affected_workspaces:
  - customer-portal
  - api
  - infra
allowed_paths:
  - apps/customer-portal
  - package.json
  - backend/api/src/modules/access
  - backend/api/src/platform/config
  - backend/api/src/platform/openapi
  - backend/api/src/platform/security
  - backend/api/test
  - backend/api/docs/identity-and-account.md
  - backend/api/.env.example
  - contracts/openapi/public-v1.yaml
  - contracts/openapi/customer-bff-v1.yaml
  - packages/api-client
  - infra/local
  - docs/work/items/VFBIZ-0066.md
  - WORK.md
depends_on: []
controlled_signals:
  - authentication
  - customer-data
  - public-contract
exclusive_resources:
  - customer-session-contract
  - public-openapi
required_checks:
  - npm run verify:api
  - npm run verify:apps
  - npm run contracts:lint
  - npm run governance:check
revision: 5
review_date: "2026-08-24"
updated_at: "2026-07-24T08:12:08.143Z"
---

# Outcome

Customer browser chỉ giữ opaque session cookie; access/refresh token nằm trong
encrypted server-side vault, có idle/absolute timeout, rotation-safe refresh và
durable provider-revocation reconciliation.

## Constraints

- Không đổi Keycloak thành business authorization authority.
- Không lưu token trong browser, PostgreSQL business tables, log hoặc audit.
- Refresh single-flight và revocation phải fail closed.
- Customer session projection tiếp tục chỉ giữ fingerprint/hash và metadata tối
  thiểu; token vault là boundary riêng.
- Provider outage không được báo logout thành công nếu chưa có reconciliation.

## Done when

- Customer Portal có BFF runtime thật, opaque cookie, encrypted vault và CSRF.
- NestJS resource API không còn đọc customer access token trực tiếp từ cookie.
- Refresh rotation/reuse, idle timeout, absolute timeout và logout-all có Redis,
  HTTP và browser E2E.
- Handoff từ local deny sang provider reconciliation có retry/outbox evidence.
- Public OpenAPI và Scalar mô tả đúng browser BFF so với resource API.

## Checkpoint

- NestJS resource API đã Bearer-only; browser auth contract thuộc riêng
  Customer Portal BFF.
- Opaque cookie, encrypted Redis token vault, PKCE/nonce, CSRF,
  idle/absolute timeout và back-channel logout đã hoàn tất.
- Atomic session revision, subject/provider fence và replay-safe back-channel
  processing chặn session resurrection trong concurrent logout/refresh.
- Provider revocation có renewable fenced lease, bounded retry/retention và
  terminal evidence không giữ refresh token.
- Required browser gate fail-fast khi thiếu E2E credentials thay vì skip im lặng.
- Exact next action: VFBIZ-0069 xây enterprise UI foundation trên boundary đã khóa.

## Evidence

- [ ] Architecture/Security Owner chấp nhận migration design.
- [x] Customer BFF vault integration tests.
- [x] Browser login/callback, authenticated `/bff/me`, CSRF deny/allow và
      Keycloak back-channel logout chạy thật trên local.
- [x] Keycloak admin logout làm opaque Customer Portal session trả `401`;
      duplicate back-channel delivery vẫn idempotent.
- [x] Provider outage/reconciliation, session race và replay tests: 9/9 Redis integration tests passed.
- [x] Security review findings resolved in two review/fix cycles.
- [x] `npm run verify:api` passed: lint, typecheck, 195 unit tests, 61 E2E tests, Prisma validation and build.
- [x] `npm run verify:apps` passed for Customer and Workforce portals.
- [x] `npm run contracts:lint` passed for all four OpenAPI contracts.
- [x] `npm run governance:check` passed with 60 provider-neutral scenarios.
- [x] `npm run verify:apps:e2e` now fails closed with exit 2 when required credentials are absent.
