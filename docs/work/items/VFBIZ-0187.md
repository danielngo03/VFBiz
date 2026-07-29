---
id: VFBIZ-0187
title: Align Dataset Registry transactions with release authority
status: review
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/modules/datasets/infrastructure/postgres_registry.py
  - backend/ai/tests/integration/datasets/test_postgres_dataset_registry.py
depends_on: []
controlled_signals:
  - ai-dataset
  - data-governance
  - concurrency
exclusive_resources:
  - ai-dataset-registry
required_checks:
  - >-
    VFBIZ_RUN_DB_INTEGRATION=1 uv run --directory backend/ai pytest
    tests/integration/datasets/test_postgres_dataset_registry.py -q
revision: 5
review_date: "2026-08-29"
updated_at: "2026-07-29T07:12:49.584Z"
---

# Outcome

Make production Dataset Registry source/fetch transitions compatible with the
SERIALIZABLE PostgreSQL release-provenance authority boundary.

## Constraints

- Retry only PostgreSQL serialization failure `40001`.
- Retry is bounded and exponential; authorization, invariant and other
  database failures are never retried.
- OCC remains the application-level lost-update authority.

## Done when

- Source and fetch transitions execute in SERIALIZABLE transactions.
- Serialization conflicts retry at most three attempts with bounded backoff.
- Existing optimistic-concurrency and exact-provenance behavior remains intact.
- Real PostgreSQL integration exercises production repository methods after
  migration `20260729_0018`.

## Checkpoint

- Implementation and PostgreSQL integration are complete.
- Retry taxonomy now has deterministic tests for success, exhaustion,
  non-retryable failures, OCC and cancellation.
- Exact next action: independent re-review, then checkpoint.

## Evidence

- [x] `VFBIZ_RUN_DB_INTEGRATION=1 uv run --directory backend/ai pytest tests/integration/datasets/test_postgres_dataset_registry.py -q`
  — 8 passed against migrated PostgreSQL, including five retry-policy cases.
- [x] `uv run --directory backend/ai pytest tests/integration/datasets/test_postgres_dataset_registry.py -q`
  — 5 retry-policy tests passed; 3 PostgreSQL cases skipped explicitly.
- [x] `npm run verify:ai` — Ruff, Pyright, offline Alembic SQL and 500 tests
  passed; 84 environment-gated tests were reported separately.

### active — 2026-07-29T07:00:48.053Z

P0 review of VFBIZ-0186 exposed the cross-team production transaction compatibility requirement; implementation is isolated to AI Knowledge Engineering paths.

### review — 2026-07-29T07:12:49.584Z

Independent reviewer-verifier approved retry taxonomy and transaction boundary with no remaining P0/P1; deterministic and real PostgreSQL evidence passed.
