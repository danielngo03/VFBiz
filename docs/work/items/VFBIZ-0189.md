---
id: VFBIZ-0189
title: Persist semantic classifier binding lifecycle
status: done
mode: controlled
priority: P0
owner_team: ai-platform-foundation
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/migrations
  - backend/ai/tests/architecture
  - backend/ai/tests/integration/platform
  - docs/work/items/VFBIZ-0189.md
  - WORK.md
depends_on: []
controlled_signals:
  - customer-chat
  - model-routing
  - ai-release
  - migration
exclusive_resources:
  - database-migration
  - ai-release-registry
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 5
review_date: "2026-08-29"
updated_at: "2026-07-29T10:43:36.487Z"
---

# Outcome

Persist canonical semantic-classifier bindings as lifecycle-bearing authority
records tied to one immutable Assistant Release activation, with explicit
trusted-evidence kinds and database constraints that prevent v3-only,
cross-activation or revoked records from being treated as active.

## Constraints

- Migration extends the existing AI PostgreSQL release authority; it does not
  create a service or public API.
- Canonical JSON remains validated by the Python authority from VFBIZ-0188;
  PostgreSQL additionally enforces identity, digest, scope, window and lifecycle
  projections.
- At most one currently usable classifier binding exists for an activation;
  supersession is atomic and requires an effective, unexpired replacement.
- Revoked/superseded records are retained for audit; destructive delete is
  forbidden.
- Existing Assistant Release and trusted-evidence records remain compatible.
- Semantic classifier provider and bootstrap composition remain disabled.

## Done when

- Alembic creates `ai_semantic_classifier_binding` with exact activation FK,
  binding/core/stack/envelope digests, canonical document, effective window,
  lifecycle state and positive revision.
- A partial unique index permits at most one active binding per activation.
- Trusted release evidence accepts distinct `classifier_evaluation` and
  `classifier_approval` kinds without weakening existing evidence kinds.
- Database guards reject direct delete, identity mutation, digest/document
  mismatch, invalid transitions and revision gaps; lifecycle changes require
  trusted `live_control` evidence and immutable history/outbox audit.
- Architecture and PostgreSQL integration tests cover active, revoke,
  supersede, duplicate, cross-activation and rollback-safe migration behavior.

## Checkpoint

- VFBIZ-0188 is done at `a191f88`; formal reviewer and risk-reviewer found no
  P0/P1 in the bounded authority.
- Implementation and independent correctness/risk review are complete with no
  remaining P0/P1; exact next action is checkpoint and formal closure.

## Evidence

- [x] `npm run verify:ai` — 534 passed; Ruff, Pyright and Alembic static SQL passed.
- [x] `npm run governance:check` — docs, reports, authorization, work and Agent OS checks passed.
- [x] `npm run verify:ai:integration` — all PostgreSQL integration and evaluation-registry tests passed without skip.
- [x] Focused PostgreSQL acceptance — 6 passed, including concurrency, supersede cutover and downgrade/re-upgrade.
- [x] Independent reviewer and risk-reviewer — no remaining P0/P1.

### active — 2026-07-29T09:29:04.559Z

Begin migration contract tests for immutable classifier binding lifecycle and dedicated trusted-evidence kinds.

### review — 2026-07-29T10:32:10.928Z

Implementation checkpoint 169ff65 passed AI, governance and full PostgreSQL integration; independent correctness and risk re-review report no remaining P0/P1.

### done — 2026-07-29T10:43:36.487Z

Completed at 169ff65. AI and governance gates passed; PostgreSQL integration ran without skips; formal reviewer-verifier and risk-reviewer ledger evidence report no remaining P0/P1.
