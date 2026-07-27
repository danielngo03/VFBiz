---
id: VFBIZ-0021
title: LangGraph Conversation Graph state machine
status: done
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
revision: 6
review_date: "2026-08-23"
updated_at: "2026-07-24T19:17:51.065Z"
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
- Node có `interrupt` chỉ thực hiện side effect idempotent vì node được chạy lại
  từ đầu khi resume; migration không deserialize mù checkpoint schema cũ.
- Real retrieval/inference/tool execution vẫn là port, không bị nhúng vào graph.

## Checkpoint

- Implementation commit: `6e7f4b0`.
- Hai lượt review độc lập đã hoàn tất; các finding về final-answer delivery,
  resume binding, late result, checkpoint privacy, grounding và state bounds
  đã được xử lý trong cùng lane.
- Exact next action: đóng work item; Knowledge Release tiếp tục ở VFBIZ-0022.

## Evidence

- [x] `npm run verify:ai` — 59 tests, Ruff, Pyright và Alembic dry-run đạt
  ngày 2026-07-25.
- [x] `npm run governance:check` — docs, reports, authorization, work schema,
  provider-neutral routing và Agent OS gates đạt ngày 2026-07-25.
