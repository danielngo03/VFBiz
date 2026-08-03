---
id: VFBIZ-0181
title: Persist conversation task context schema
status: done
mode: controlled
priority: P0
owner_team: api-foundation
accountable_role: engineering-lead
primary_workspace: api
affected_workspaces:
  - api
allowed_paths:
  - backend/api/prisma/migrations
depends_on: []
controlled_signals:
  - customer-chat
  - data-model
exclusive_resources:
  - database-migration
required_checks:
  - npm run prisma:validate --workspace @vfbiz/api
revision: 15
review_date: "2026-08-29"
updated_at: "2026-07-29T14:56:51.609Z"
---

# Outcome

Add a forward-only PostgreSQL migration for one versioned
`conversation_task_context` row per conversation session.

## Constraints

- Migration is additive and non-destructive.
- No raw PII, prompt or chain-of-thought columns.
- Version, expiry, release binding and authorization digest are database
  constrained where practical.

## Done when

- Table has one-to-one session ownership, version, bounded JSON slots, lifecycle,
  release/policy/authorization binding, expiry and audit timestamps.
- Index supports active non-expired lookup.
- Prisma validation remains green after the owning context adds its model.

## Checkpoint

- Additive migration and owning Prisma model are implemented under separate
  owner-team claims.
- Clean and legacy migration replay are drift-free.
- The first independent review found two P1 gaps. Both are now closed with a
  same-session composite foreign key and a database-enforced opaque slot
  envelope.
- Follow-up PostgreSQL evidence now covers update, close, active topic switch
  and terminal/stale replacement with a new task ID/version plus typed
  `replacedTaskId` and `replacementReason` audit evidence.
- A forward migration replaces the permissive reference envelope with
  `namespace:ref/v1/<sha256>` and validates all existing rows before the new
  constraint becomes authoritative.
- Exact next action: close with VFBIZ-0168 after the final independent review.

## Evidence

- [x] `npm run prisma:validate --workspace @vfbiz/api`
  — schema valid.
- [x] `npm run test:migrations --workspace @vfbiz/api`
  — clean replay, zero schema drift, 42 PostgreSQL tests and legacy replay
  passed; negative cases cover cross-session provenance, raw text, VIN, phone,
  plate, tax identifier, PII-shaped reference and nested prompt injection.
- [x] Final independent correctness/risk review — no P0/P1/P2 findings after
  the forward constraint remediation.

### active — 2026-07-29T14:56:00.000Z

Forward receipt-envelope migration and database negative cases close the final
P1 finding without rewriting migration history.

### review — 2026-07-29T08:20:54.000Z

The migration and owning repository now cover both active intent replacement
and terminal task closure without weakening same-session, OCC or fencing
constraints.

### active — 2026-07-29T07:14:57.858Z

Dataset provenance gates checkpointed; begin additive conversation task authority migration with public Chat API still disabled.

### blocked — 2026-07-29T14:52:21.483Z

Independent review found database opaque-reference validation too permissive; forward remediation is implemented and under final verification.

### active — 2026-07-29T14:52:21.626Z

Apply forward PostgreSQL receipt-envelope constraint and negative integration coverage.

### review — 2026-07-29T14:52:46.970Z

Forward receipt constraint passed clean and legacy migration replay; independent review reports no P0/P1/P2.

### blocked — 2026-07-29T14:54:52.154Z

Formalize the completed remediation writer ledger before closing controlled work.

### active — 2026-07-29T14:54:52.296Z

Record implementation evidence for the forward PostgreSQL receipt constraint.

### review — 2026-07-29T14:56:15.917Z

Checkpoint 7492d64 contains the forward migration and clean/legacy replay evidence.

### done — 2026-07-29T14:56:51.609Z

Forward receipt-envelope migration is validated by clean/legacy replay and independent correctness/risk review.
