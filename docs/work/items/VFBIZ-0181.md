---
id: VFBIZ-0181
title: Persist conversation task context schema
status: proposed
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
revision: 2
review_date: "2026-08-29"
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

- Exact next action: coordinate the Prisma model with VFBIZ-0168, then add the
  additive migration under an exclusive lease.

## Evidence

- [ ] `npm run prisma:validate --workspace @vfbiz/api` — add evidence reference
