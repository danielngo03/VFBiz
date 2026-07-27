---
id: VFBIZ-0098
title: Durable support handoff and contact-center integration
status: proposed
mode: controlled
priority: P0
owner_team: customer-engagement
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/src/modules/engagement
  - backend/api/docs/conversation-runtime.md
  - backend/api/test/e2e/engagement
  - backend/api/test/integration/engagement
depends_on:
  - VFBIZ-0095
controlled_signals:
  - support-handoff
  - customer-conversation
  - authorization
  - pii
  - customer-privacy
exclusive_resources:
  - support-handoff-contract
required_checks:
  - npm run verify:api
  - npm run verify:apps
  - npm run governance:check
revision: 1
review_date: "2026-07-25"
---

# Outcome

AI handoff recommendation chỉ trở thành durable support case sau API policy,
consent và queue checks; customer và workforce reconnect được cùng lifecycle
qua contact-center adapter có reconciliation.

## Constraints

- AI không tự chọn agent/queue, không tuyên bố connected và không mở lại case.
- Handoff create/callback đều idempotent, versioned và object-authorized.
- Customer PII được minimize; notification chỉ dùng channel đã consent.
- Contact-center outage không rollback conversation hoặc làm AI tự tiếp quản.

## Done when

- Application decision service kiểm scope, consent, reason, urgency, safety,
  queue availability và duplicate request trước durable create.
- Lifecycle requested/queued/assigned/connected/transferred/resolved cùng
  expired/cancelled được enforce bằng OCC và audit.
- Outbox adapter, signed callback replay protection, reconciliation, timeout,
  DLQ và operator retry tồn tại.
- Offline customer response được persist và notification không chứa PII.
- Workforce contract expose case lifecycle theo capability/scope; UI thuộc
  VFBIZ-0102.
- Provider timeout, callback out-of-order, duplicate, cross-customer và consent
  revoked đạt integration/E2E.

## Checkpoint

- Exact next action: start sau public Chat contract VFBIZ-0095; chọn contact
  center provider qua adapter/config, không hardcode vendor vào domain.

## Evidence

- [ ] `npm run verify:api` — add evidence reference
- [ ] `npm run verify:apps` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
