---
id: VFBIZ-0132
title: Authenticate internal AI execution responses
status: active
mode: controlled
priority: P0
owner_team: architecture-integration
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - api
  - ai
  - root
allowed_paths:
  - backend/api/src/platform/config
  - backend/api/src/modules/engagement/infrastructure/ai
  - backend/api/test
  - backend/api/.env.example
  - backend/ai/app/platform/security
  - backend/ai/app/platform/config
  - backend/ai/app/bootstrap
  - backend/ai/app/api/internal_v1
  - backend/ai/tests
  - backend/ai/.env.example
  - contracts/openapi/internal-v1.yaml
  - docs/work/items/VFBIZ-0132.md
  - backend/api/docs/ai-gateway-and-tools.md
  - backend/ai/docs/architecture.md
depends_on: []
controlled_signals:
  - ai-assistant
  - security
  - internal-contract
exclusive_resources:
  - ai-internal-conversation-contract
required_checks:
  - npm run verify:api
  - npm run verify:ai
  - npm run contracts:lint
  - npm run governance:check
revision: 3
review_date: "2026-07-27"
updated_at: "2026-07-27T17:03:43.708Z"
---

# Outcome

NestJS chỉ chấp nhận kết quả execution từ FastAPI khi raw response body có
chữ ký workload hợp lệ, còn hiệu lực và được bind với request/correlation ID;
response bị sửa, replay hoặc ký bởi key ngoài allowlist phải fail closed trước
khi parse/commit kết quả hội thoại.

## Constraints

- Dùng asymmetric workload key; API chỉ giữ public key, AI giữ private key trong
  secret-mounted absolute file. Không đưa key material vào `.env` hoặc Git.
- Chữ ký bind raw response digest, request ID, correlation ID, issued/expiry và
  key ID. TTL tối đa 60 giây và hỗ trợ tối đa ba key để rotation chồng lấn.
- HTTP redirect tiếp tục bị cấm. mTLS vẫn là deployment control độc lập; signed
  response không được mô tả như thay thế network identity.
- Dispatch bật mà response verification chưa cấu hình phải fail closed.

## Done when

- FastAPI ký mọi successful turn execution response bằng Ed25519 hoặc ES256 từ
  configured keyring và không log private key/signature payload.
- NestJS verify signature trên raw bytes trước JSON parsing và kiểm request,
  correlation, TTL, body digest cùng allowlisted key ID.
- Tampered body/header, unknown key, expired/future signature và missing
  signature đều bị từ chối bằng typed `invalid_response`.
- Unit/integration tests chứng minh rotation overlap và binding; OpenAPI/env/docs
  mô tả đúng local/staging behavior.

## Checkpoint

- Implemented Ed25519 detached response signatures for successful execution and
  cancellation responses. AI loads only a secret-mounted private PEM; API
  loads an allowlisted public-key ring and verifies raw bytes before parsing.
- Signature input binds protocol version, key ID, issue/expiry timestamps,
  request ID, correlation ID and raw-body SHA-256. TTL is bounded to 60 seconds;
  future, expired, unknown-key, wrong-binding and tampered responses fail closed.
- Staging/production AI configuration requires response signing. Enabled API
  trust requires response verification keys. Local disabled mode remains usable.
- mTLS remains a separate deployment/human evidence gate.
- Exact next action: independent security/reviewer verification and deployment
  evidence for secret mount, overlapping key rotation and mTLS identity.

## Evidence

- [x] `npm run verify:api` — 60 suites/336 unit tests, 10 suites/67 E2E tests,
      lint, typecheck, Prisma validation and build passed on 2026-07-27.
- [x] `npm run verify:ai` — Ruff, Pyright, fast tests and Alembic SQL generation
      passed on 2026-07-27.
- [x] `VFBIZ_RUN_DB_INTEGRATION=1 npm run verify:ai:integration` — 108 real
      PostgreSQL/pgvector integration tests passed with zero skips on
      2026-07-27.
- [x] `npm run contracts:lint` — five OpenAPI contracts, runtime schemas and
      workforce capabilities passed on 2026-07-27.
- [x] Focused authenticity suites — API signer/config/verifier/transport and AI
      signer/middleware/settings tests passed, including tamper and expiry cases.
- [x] `npm run governance:check` and native API migration replay — 129 work
      items validated; all 23 migrations and 41 PostgreSQL tests passed.
- [ ] Independent reviewer-verifier, security risk review and production mTLS
      evidence remain required; this item is not marked done by its implementer.

### ready — 2026-07-27T17:03:43.385Z

Scope and acceptance refined; implementation can begin.

### active — 2026-07-27T17:03:43.708Z

Implementing asymmetric response authenticity; public dispatch remains disabled.
