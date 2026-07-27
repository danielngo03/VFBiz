---
id: VFBIZ-0024
title: API–AI Conversation Transport integration
status: done
mode: controlled
priority: P0
owner_team: customer-engagement
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
  - ai
allowed_paths:
  - backend/api/.env.example
  - backend/api/src/app.module.ts
  - backend/api/src/platform/config
  - backend/api/src/platform/security
  - backend/api/src/modules/engagement/application
  - backend/api/src/modules/engagement/infrastructure
  - backend/api/src/modules/engagement/engagement.module.ts
  - backend/api/src/modules/engagement/engagement-runtime.module.ts
  - backend/api/src/modules/engagement/presentation
  - backend/api/docs/ai-gateway-and-tools.md
  - backend/api/docs/conversation-runtime.md
  - backend/api/test/integration/engagement
  - backend/api/test/e2e/engagement
  - backend/ai/.env.example
  - backend/ai/app/platform/config/settings.py
  - backend/ai/tests/unit/platform
  - guides/customer-ai
depends_on:
  - VFBIZ-0019
  - VFBIZ-0021
controlled_signals:
  - customer-conversation
  - ai-assistant
  - authorization
  - pii
  - session-concurrency
exclusive_resources: []
required_checks:
  - npm run verify:api
  - npm run governance:check
revision: 10
review_date: "2026-08-23"
updated_at: "2026-07-25T08:54:21.699Z"
---

# Outcome

NestJS dispatch một claimed turn tới private FastAPI endpoint bằng signed
assertion và map result/event về Conversation Runtime mà không chuyển identity,
authorization hoặc side-effect authority cho AI Platform.

## Constraints

- Contract từ VFBIZ-0019 là read-only input; breaking change cần work item mới.
- Cancellation, timeout và fencing phải xuyên suốt transport.
- Không gửi raw access token, capability cookie hoặc customer ID do client khai.
- Provider/model lỗi phải trả typed fail-closed outcome; không retry vô hạn.

## Done when

- Signed assertion pin conversation/version/fencing/profile/scope/budget và
  policy/graph/knowledge revision.
- Private client có timeout, bounded retry, circuit breaker và cancellation.
- Result đến từ stale fencing/replay bị loại trước khi ghi public event.
- Final answer/citation chỉ thành business state sau transaction commit của API;
  AI checkpoint hoặc provider stream không được coi là committed response.
- Error mapping không làm lộ prompt, tool payload hoặc internal stack.
- Integration test dùng fake FastAPI server; provider outage/cancel/replay đạt.

## Checkpoint

- Signed assertion, HMAC-pseudonymized subject, public-only JWKS, private HTTP
  transport, bounded retry, timeout, redirect denial và response validation đã
  được nối vào runtime module.
- PostgreSQL inbox dispatcher thực thi tối đa ba session song song; cancellation
  dùng durable outbox, lease, retry hữu hạn và fencing.
- Business tools vẫn bị deny; cả public và authenticated baseline chỉ được đề
  xuất `search_public_knowledge` cho tới khi API-side tool gateway hoàn tất.
- Public conversation controller chưa được compose vào `AppModule`; activation
  thuộc integration/acceptance work item sau retrieval.
- Review cycle 1 phát hiện ba P1 và đã sửa: dispatch có activation gate riêng,
  transport failure không ghi reserved budget thành usage, cancellation lane
  không bị starve/reclaim sớm, response/citation bind exact release revisions.
- Exact next action: final reviewer confirmation; sau đó đóng transport/trust
  foundation và mở VFBIZ-0025 retrieval snapshot.

## Evidence

- [x] `npm run verify:api` — 52 unit suites/259 tests, 9 E2E suites/61 tests,
  lint, typecheck, Prisma validation và Nest build đều đạt ngày 25/07/2026.
- [x] `npm run verify:ai` — Ruff, Pyright, 133 tests (2 skipped) và Alembic
  static upgrade đạt ngày 25/07/2026.
- [x] `npm run governance:check` — 75 canonical documents, 10 reports,
  12 guides, 24 capabilities, 90 work items và 61 routing scenarios đạt ngày
  25/07/2026.
