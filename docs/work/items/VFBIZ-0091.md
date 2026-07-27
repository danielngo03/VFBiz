---
id: VFBIZ-0091
title: Implement durable AI resume gate
status: done
mode: controlled
priority: P0
owner_team: ai-platform-foundation
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/platform/checkpoints
  - backend/ai/app/platform/database/model_registry.py
  - backend/ai/migrations
  - backend/ai/tests/unit/platform
depends_on:
  - VFBIZ-0021
controlled_signals:
  - customer-conversation
  - session-concurrency
  - migration
  - pii
exclusive_resources:
  - database-migration
  - ai-conversation-checkpoint-registry
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 8
review_date: "2026-07-24"
updated_at: "2026-07-24T20:40:03.943Z"
---

# Outcome

AI Platform cung cấp PostgreSQL resume gate durable với atomic CAS cho start,
interrupt activation, single resume claim và finalize, để nhiều process không
thể chạy cùng một turn hoặc mở lại turn đã terminal.

## Constraints

- Không lưu raw message, answer, prompt, token hoặc PII.
- Adapter triển khai application protocol, nhưng platform không import graph.
- Migration và registry giữ exclusive lease; không sửa Knowledge Release.

## Done when

- Bảng resume gate có key duy nhất, state check, deadline, fencing token và opaque
  digest/nonce/checkpoint ID.
- `reserve_start` dùng insert-if-absent; duplicate start không chạy graph.
- `claim_once` là một conditional update `waiting -> claimed`; chỉ một connection
  nhận claim token.
- `prepare`, `close_start` và `finalize` validate state/token/fencing và fail closed.
- Adapter có unit/SQL contract tests cho duplicate start, concurrent claim,
  expiry, token mismatch và terminal non-reopen.
- Model registry, Alembic SQL, AI verify và governance gate đạt.

## Checkpoint

- PostgreSQL model, CAS repository, model registry và Alembic migration được
  commit tại `b1b542a`; architecture registry integration tại `55e0620`.
- Fix cycle cuối tại `4ca306e` bổ sung expired-reservation recovery và
  idempotent finalize khi expiry đua với claimant.
- Exact next action: đóng work item và giữ multi-connection PostgreSQL race test
  cho integration environment có isolated database.

## Evidence

- [x] `npm run verify:ai` — 92 tests, Ruff/Pyright và Alembic SQL đạt sau `4ca306e`
- [x] `npm run governance:check` — docs, work schemas, provider adapters và routing scenarios đạt

### review — 2026-07-24T20:32:16.763Z

Durable PostgreSQL resume gate committed at b1b542a; 89 AI tests and governance gate pass; independent integration review requested.

### blocked — 2026-07-24T20:35:08.654Z

Independent integration review found reserved-state crash recovery and claimed-expiry/finalize race gaps; reopen for bounded fix cycle.

### active — 2026-07-24T20:35:08.935Z

Fix durable gate crash recovery and expiry/finalize race with regression tests.

### review — 2026-07-24T20:40:03.665Z

Fix cycle 2 closed all integration findings; 92 AI tests and governance pass.

### done — 2026-07-24T20:40:03.943Z

Durable PostgreSQL resume gate accepted at b1b542a/4ca306e with integration registry 55e0620.
