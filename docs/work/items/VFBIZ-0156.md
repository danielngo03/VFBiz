---
id: VFBIZ-0156
title: Build resumable AI evaluation run registry
status: review
mode: controlled
priority: P0
owner_team: ai-assurance
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai/app/modules/evaluation
  - backend/ai/tests/evaluation
  - backend/ai/tests/integration/evaluation
  - backend/ai/migrations/versions
  - docs/work/items/VFBIZ-0156.md
  - WORK.md
depends_on: []
controlled_signals:
  - ai-quality-platform
  - benchmark-runner
  - experiment-registry
exclusive_resources:
  - database-migration
required_checks:
  - cd backend/ai && uv run pytest tests/evaluation
  - npm run verify:ai
revision: 5
review_date: "2026-08-28"
updated_at: "2026-07-28T14:51:36.652Z"
---

# Outcome

Persist an immutable evaluation plan and resume its lifecycle safely after
worker restart or duplicate delivery without allowing Evaluation to promote a
release.

## Constraints

- PostgreSQL is the durable authority; Redis may coordinate but cannot own run state.
- State transitions use optimistic concurrency and idempotent command identity.
- A runner may resume only the exact plan digest originally registered.
- Cancellation is durable and late worker updates cannot revive a terminal run.
- Evaluation emits evidence; Governance remains the sole promotion authority.
- Do not add benchmark-provider or model-specific runtime modules.

## Done when

- Run state validates the V12 lifecycle and rejects illegal transitions.
- Registering the same run and plan is idempotent; a conflicting plan fails closed.
- Repository writes use row-version OCC and immutable plan digest binding.
- Resume progress, cancellation and terminal outcomes survive PostgreSQL reload.
- Forward migration preserves legacy evaluation rows while enabling governed runs.
- Unit, PostgreSQL integration and full AI verification pass.

## Checkpoint

- Immutable plan digest, resumable state machine, PostgreSQL OCC, durable
  cancellation and guarded forward migration are implemented.
- Release integration discovers and runs the governed PostgreSQL test through
  VFBIZ-0166.
- Exact next action: VFBIZ-0192 adds controlled suite execution, benchmark
  adapters and evidence authority on top of this registry.

## Evidence

- [x] `cd backend/ai && VFBIZ_RUN_DB_INTEGRATION=1 uv run pytest tests/evaluation/test_postgres_evaluation_run_registry.py -q` — migrated PostgreSQL integration passed
- [x] `npm run verify:ai:integration` with isolated database configuration — shared integration suite and governed evaluation registry test passed
- [x] `npm run verify:ai` — 465 passed, 81 explicitly skipped in the local fast profile
- [x] Independent read-only reviewer — PASS after three review/fix cycles; no P0/P1 remains

### ready — 2026-07-28T14:30:43.850Z

Scoped durable run registry and forward migration.

### active — 2026-07-28T14:30:43.986Z

Begin test-first state machine and persistence boundary.

### active — 2026-07-28T14:36:33.913Z

State machine, plan digest, PostgreSQL OCC registry and forward migration implemented; unit/architecture/full AI checks pass. Next: real PostgreSQL integration and independent reviews.

### review — 2026-07-28T14:51:36.652Z

Durable run registry, migration, integration and independent review passed; no P0/P1 remains.
