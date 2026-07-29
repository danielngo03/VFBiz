---
id: VFBIZ-0168
title: Add durable conversation task authority
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
  - backend/api/prisma/models/engagement.prisma
  - backend/api/test/integration/engagement
  - backend/api/docs/conversation-runtime.md
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
revision: 2
review_date: "2026-08-29"
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

- Exact next action: wait for VFBIZ-0181 migration, then implement domain and
  atomic repository behavior test-first.

## Evidence

- [ ] `npm run typecheck --workspace @vfbiz/api` — add evidence reference
- [ ] `npm run test --workspace @vfbiz/api` — add evidence reference
