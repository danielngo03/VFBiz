---
id: VFBIZ-0168
title: Add durable conversation task authority
status: review
mode: controlled
priority: P0
owner_team: customer-engagement
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
  - ai
  - root
allowed_paths:
  - backend/api/src/modules/engagement
  - backend/api/prisma/models/engagement.prisma
  - backend/api/test/integration/engagement
  - backend/api/docs/conversation-runtime.md
  - backend/api/src/platform/security
  - backend/api/test/integration/access
  - backend/ai/app/api/internal_v1
  - backend/ai/app/modules/assistant
  - backend/ai/app/platform/security
  - backend/ai/tests
  - backend/ai/docs/conversation-graph.md
  - contracts/ai/assistant/execution-assertion.schema.json
depends_on: []
controlled_signals:
  - customer-chat
  - ai-orchestration
  - public-contract
exclusive_resources:
  - conversation-protocol
required_checks:
  - npm run typecheck --workspace @vfbiz/api
  - npm run test --workspace @vfbiz/api
revision: 8
review_date: "2026-08-29"
updated_at: "2026-07-29T08:20:54.000Z"
---

# Outcome

Make NestJS the durable authority for active task, pending/collected slots and
clarification continuity across independent customer turns.

## Constraints

- Persist only typed, bounded, non-PII task state.
- Task delta, public event and outbox must commit under the same OCC/fencing
  transaction.
- FastAPI may propose a delta but cannot authoritatively persist task state.
- Public Chat API remains disabled.

## Done when

- Turn execution context includes a release- and authorization-bound task
  context.
- Clarification persists a versioned task; later turn can continue it.
- Stale task version, subject/release/auth change and late fencing result fail
  closed.
- Topic switch closes the prior task and correction is audited.

## Checkpoint

- VFBIZ-0181 migration and owning Prisma model now pass clean/legacy replay
  without schema drift.
- Typed task context/delta validates bounded opaque references and rejects raw
  prompt, nested payload and PII-shaped references.
- Claimed turn execution now projects only active, unexpired task context bound
  to the session release.
- `authorizationContextDigest` is pinned in both the canonical request and
  short-lived execution assertion. FastAPI revalidates release/expiry and maps
  the API-owned task into graph state.
- Terminal clarification emits a typed task delta; NestJS validates and commits
  it with the completion event/outbox. A known intent switch atomically replaces
  the active task and records a typed replacement reason; ambiguous multi-intent
  clarification preserves the current task authority.
- NestJS, not the model, creates the deterministic close delta for answered,
  refused, handoff and tool-refusal terminal outcomes. Task close, completion
  event and outbox share the same serializable transaction.
- Exact next action: final independent P0/P1 review followed by a cohesive
  checkpoint.

## Evidence

- [x] `npm run typecheck --workspace @vfbiz/api` — pass.
- [x] `npm run test --workspace @vfbiz/api` — 355 unit tests passed.
- [x] Focused API domain/transport/application/security tests — 44 passed.
- [x] AI unit/contract task-continuity tests — pass.
- [x] `npm run verify:ai` — Ruff, Pyright, Alembic and 504 tests passed;
  84 environment-gated tests skipped by the local fast suite.
- [x] `npm run test:migrations --workspace @vfbiz/api`
  — 42 PostgreSQL tests, clean/legacy replay and zero schema drift passed.
- [x] Lifecycle regression evidence covers active topic switch plus automatic
  close after answer, refusal and handoff.

### review — 2026-07-29T08:20:54.000Z

Independent review found two P1 lifecycle gaps. Active topic switch now has an
explicit atomic replacement path and terminal successful/policy outcomes close
the API-owned task deterministically.

### active — 2026-07-29T07:17:09.521Z

VFBIZ-0181 migration clean replay exposed expected Prisma drift; implement the owning engagement model and durable repository contract while public Chat remains disabled.
