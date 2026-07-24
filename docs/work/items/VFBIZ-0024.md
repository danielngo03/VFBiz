---
id: VFBIZ-0024
title: API–AI Conversation Transport integration
status: proposed
mode: controlled
priority: P0
owner_team: customer-engagement
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/engagement/application
  - backend/api/src/modules/engagement/infrastructure
  - backend/api/docs/ai-gateway-and-tools.md
  - backend/api/test/integration/engagement
  - backend/api/test/e2e/engagement
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
revision: 1
review_date: "2026-08-23"
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
- Error mapping không làm lộ prompt, tool payload hoặc internal stack.
- Integration test dùng fake FastAPI server; provider outage/cancel/replay đạt.

## Checkpoint

- Exact next action: chỉ start sau VFBIZ-0019 và VFBIZ-0021; implement một
  provider-neutral private client, chưa bật model thật.

## Evidence

- [ ] `npm run verify:api` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
