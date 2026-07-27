---
id: VFBIZ-0090
title: Harden Conversation Graph runtime after independent audit
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
  - backend/ai/app/platform/checkpoints
  - backend/ai/tests/unit/assistant
  - backend/ai/tests/architecture
  - backend/ai/docs/conversation-graph.md
depends_on:
  - VFBIZ-0021
  - VFBIZ-0091
controlled_signals:
  - ai-assistant
  - customer-conversation
  - session-concurrency
  - pii
  - migration
exclusive_resources:
  - ai-conversation-checkpoint-registry
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 6
review_date: "2026-07-24"
updated_at: "2026-07-24T20:40:04.525Z"
---

# Outcome

Conversation Graph runtime bind một execution envelope với đúng native
checkpoint, chỉ cho phép một resume thắng bằng CAS/nonce, dùng strict safe
serialization và giữ dependency direction `graph -> application/domain`.

## Constraints

- Không mở rộng Knowledge Release, retrieval, model provider hoặc public API.
- Không tin `thread_id`, factual classification hoặc evidence do worker/caller
  tự khai báo.
- Không sửa hoặc stage thay đổi riêng trong Customer Portal.

## Done when

- Runtime tự sinh checkpoint namespace từ session/turn/graph identity; config
  caller không thể chọn checkpoint khác.
- Hai resume đồng thời chỉ một request consume interrupt; request còn lại nhận
  typed conflict mà không chạy worker.
- Strict serializer từ chối type ngoài allowlist; checkpoint không chứa raw
  message, final answer, prompt hoặc PII.
- Deadline truyền timeout/cancellation xuống worker và late result bị drop.
- Grounding policy do graph/application policy quyết định; factual completion
  thiếu approved evidence bị từ chối.
- Security-boundary mismatch xóa entity; schema migration cùng identity chỉ giữ
  entity sau revalidation policy.
- Application/domain không import `graph`, LangGraph hoặc infrastructure; có
  architecture regression test.
- Cross-session, concurrent resume, tampered checkpoint, hung worker,
  ungrounded answer và entity conflict tests đạt.

## Checkpoint

- Conversation Graph hardening đã được commit tại `6d83e56` và `f21672a`.
- Hai vòng review độc lập đã hoàn tất; mọi finding thuộc Assistant boundary đã
  được đóng bằng regression test.
- PostgreSQL adapter mapping được commit tại `69a706d`; runtime/application
  contract không phụ thuộc concrete platform DTO.
- Exact next action: đóng work item và mở lại Knowledge Release `VFBIZ-0022`.

## Evidence

- [x] `npm run verify:ai` — 92 tests passed, Ruff/Pyright/Alembic dry-run đạt sau `69a706d`
- [x] `npm run governance:check` — 75 docs, 88 work items và 61 routing scenarios đạt sau `f21672a`

### active — 2026-07-24T20:22:58.702Z

Assistant boundary passed 73 AI tests and two independent review rounds at f21672a; waiting for VFBIZ-0091 durable PostgreSQL resume gate integration.

### review — 2026-07-24T20:40:04.232Z

Graph hardening and durable gate adapter complete; two review/fix cycles exhausted with 92 AI tests green.

### done — 2026-07-24T20:40:04.525Z

Conversation Graph runtime hardening accepted; Knowledge Release may resume.
