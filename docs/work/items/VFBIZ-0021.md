---
id: VFBIZ-0021
title: LangGraph Conversation Graph state machine
status: proposed
mode: controlled
priority: P0
owner_team: ai-assistant-orchestration
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/modules/assistant
  - backend/ai/docs/conversation-graph.md
  - backend/ai/tests/unit/assistant
  - backend/ai/tests/contract/assistant
depends_on:
  - VFBIZ-0020
controlled_signals:
  - ai-assistant
  - customer-conversation
  - session-concurrency
  - pii
exclusive_resources: []
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 1
review_date: "2026-08-23"
---

# Outcome

LangGraph Conversation Graph xử lý một customer turn bằng typed state machine,
bounded Supervisor và deterministic fake ports, giữ global entity qua context
switch nhưng không tự mở quyền hoặc side effect.

## Constraints

- State tách `GlobalEntities`, `ActiveTask`, `Control` và `Evidence`.
- Supervisor có bounded reflection/clarification; tối đa ba attempt, không có
  autonomous loop.
- Checkpoint pin `graph_version`; mismatch giữ global entity đã validate và
  reset active task theo migration policy.
- Cancellation/fencing thắng mọi provider result đến muộn.

## Done when

- Graph route, clarify, retry, refuse và handoff bằng structured outcome.
- Context switch VF 8 → tài chính → “xe lúc nãy” giữ đúng confirmed entity.
- Missing tool argument tạo clarification; schema/auth/anomaly failure không
  được model tự sửa thành fact.
- Retry exhaustion, interrupt, stale checkpoint và stale fencing tests đạt.
- Real retrieval/inference/tool execution vẫn là port, không bị nhúng vào graph.

## Checkpoint

- Exact next action: start bằng typed state/reducer và fake ports; không triển
  khai Knowledge Release trong lane này.

## Evidence

- [ ] `npm run verify:ai` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference
