---
id: VFBIZ-0093
title: API internal AI trust configuration
status: done
mode: controlled
priority: P0
owner_team: api-foundation
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/.env.example
  - backend/api/src/platform/config
  - backend/api/src/platform/security
  - backend/api/test/integration/access
depends_on:
  - VFBIZ-0019
  - VFBIZ-0021
controlled_signals:
  - authorization
  - ai-assistant
exclusive_resources: []
required_checks:
  - npm run verify:api
  - npm run governance:check
revision: 8
review_date: "2026-07-25"
updated_at: "2026-07-25T08:54:21.405Z"
---

# Outcome

API Platform có typed, fail-fast configuration và asymmetric signing keyring
cho short-lived internal AI assertion; public JWKS chỉ lộ public key và không
tái sử dụng Keycloak/customer credential.

## Constraints

- Không sửa public conversation contract hoặc engagement business state.
- Private key chỉ đọc từ secret/file reference được typed config kiểm tra; không
  commit key thật.
- Local fixture chỉ được phép trong test; staging/production dùng secret
  manager/workload delivery và HTTPS allowlist.
- Rotation hỗ trợ current/next key overlap theo `kid`.

## Done when

- Environment schema kiểm base URL private, timeout, retry budget, issuer,
  audience, TTL và keyring.
- Signer tạo assertion EdDSA/ES256 có `kid`, `jti`, expiry ngắn và pinned
  claims, đồng bộ với private `internal-v1`.
- JWKS exporter không chứa private material.
- Invalid key/URL/TTL/config fail trước runtime; unit/integration tests đạt.

## Checkpoint

- Typed config, disabled-safe trust module, EdDSA/ES256 keyring, HMAC subject
  pseudonymization, assertion signer và public-only JWKS exporter đã hoàn tất.
- Enabled runtime từ chối private key có permission rộng, sai owner, URL/host
  không hợp lệ hoặc thiếu revision; disabled baseline fail closed khi ký.
- Trust module đã được compose qua VFBIZ-0024 và API E2E không còn circular
  import.
- Exact next action: final independent review rồi transition `review`.

## Evidence

- [x] `npm run verify:api` — lint/typecheck, 52 unit suites/256 tests, 9 E2E
  suites/61 tests, Prisma validation và build đạt ngày 25/07/2026.
- [x] Focused trust gate — ESLint, typecheck và 3 suites/17 tests đạt, gồm
  NestJS integration, rotation, public-only JWKS và disabled fail-closed.
- [x] `npm run governance:check` — docs, reports, guides, authorization, 90 work
  items và 61 provider-neutral scenarios đạt.
- [x] `npm run verify:ai` — environment parity tiếp tục đạt Ruff, Pyright,
  133 tests (2 skipped) và Alembic dry-run ngày 25/07/2026.
