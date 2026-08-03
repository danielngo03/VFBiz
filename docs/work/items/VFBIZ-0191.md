---
id: VFBIZ-0191
title: Add durable conversation slot authority
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
  - backend/api/src/modules/product
  - backend/api/src/integration
  - backend/api/src/app.module.ts
  - backend/api/src/platform/database/prisma.service.ts
  - backend/api/prisma/models/engagement.prisma
  - backend/api/prisma/migrations
  - backend/api/test
  - backend/ai/app/modules/assistant
  - backend/ai/app/api/internal_v1
  - backend/ai/tests/unit/assistant
  - backend/ai/tests/unit/api
  - contracts/ai/assistant
  - docs/INDEX.json
  - docs/architecture/customer-assistant-capability-maturity.json
  - docs/architecture/customer-assistant-capability-maturity.md
  - docs/work/items/VFBIZ-0191.md
  - WORK.md
depends_on:
  - VFBIZ-0190
  - VFBIZ-0168
  - VFBIZ-0181
controlled_signals:
  - customer-chat
  - conversation-state
  - authorization
  - migration
exclusive_resources:
  - public-contract
  - database-migration
  - conversation-runtime
required_checks:
  - npm run contracts:lint
  - npm run verify:api
  - npm run verify:ai
revision: 4
review_date: "2026-08-29"
updated_at: "2026-07-29T15:43:06.224Z"
---

# Outcome

Allow a clarification answer to update durable conversation task slots only
after NestJS resolves an API-owned authority receipt.

## Constraints

- FastAPI may propose slot candidates but cannot confirm business identity.
- Raw VIN, email, phone, prompt or chain-of-thought cannot enter graph state.
- Task delta, event and outbox commit atomically with OCC and fencing.

## Done when

- Canonical candidate and receipt contracts have cross-language vectors.
- Clarification, correction, topic switch, expiry and concurrent update tests pass.
- Stale task, subject, release or authorization bindings fail closed.
- Slot receipt provenance is auditable without storing sensitive raw values.

## Checkpoint

- Candidate/receipt boundary is implemented across JSON Schema, Python,
  TypeScript and PostgreSQL.
- FastAPI can emit only transient candidates; the API-owned authority issues
  a task/slot-bound opaque receipt or leaves the slot unresolved.
- Exact next action: record the independent review and checkpoint this
  controlled lane.

## Evidence

- [x] `npm run contracts:lint` — 33 registered AI contracts and 53 vectors
  validated on 2026-07-29.
- [x] `npm run verify:api` — lint, typecheck, 377 unit tests, 67 E2E tests,
  Prisma validation and production build passed on 2026-07-29.
- [x] `npm run verify:ai` — Ruff, Pyright, 536 tests and Alembic SQL replay
  passed on 2026-07-29; 90 external integration cases remain explicitly
  skipped by the local profile.
- [x] `npm run test:migrations --workspace @vfbiz/api` — clean and legacy
  replay plus 42 PostgreSQL integration cases passed on 2026-07-29.
- [x] `npm run governance:check` — maturity, dependency snapshot,
  documentation, reports, authorization, work ledger and agent governance
  passed on 2026-07-29.
- [x] Independent reviewer-verifier — PASS after remediation of advancing-clock,
  market-provenance and legacy-invalidation evidence findings; no remaining
  P0/P1/P2 on 2026-07-29.

### ready — 2026-07-29T14:58:32.677Z

VFBIZ-0190, VFBIZ-0168 and VFBIZ-0181 are complete; slot-authority contract lane is ready.

### active — 2026-07-29T14:58:32.817Z

Implement candidate/receipt contracts and API-owned slot resolution with fail-closed production composition.

### review — 2026-07-29T15:43:06.224Z

Implementation and migration gates passed; independent reviewer-verifier reported PASS with no remaining P0/P1/P2.
