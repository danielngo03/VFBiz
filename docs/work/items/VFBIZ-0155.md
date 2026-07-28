---
id: VFBIZ-0155
title: Build AI Quality benchmark and grader registries
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
  - docs/work/items/VFBIZ-0155.md
  - WORK.md
depends_on: []
controlled_signals:
  - ai-quality-platform
  - benchmark-runner
  - grader-calibration
  - experiment-registry
exclusive_resources: []
required_checks:
  - cd backend/ai && uv run pytest tests/evaluation
  - npm run verify:ai
revision: 4
review_date: "2026-08-28"
updated_at: "2026-07-28T14:27:17.769Z"
---

# Outcome

Build the domain and application foundation that resolves an immutable
benchmark plan from exact metric, grader and calibration revisions without
promoting a release.

## Constraints

- Evaluation emits a reproducible plan/evidence only; Governance owns decisions.
- No provider, storage SDK, CLI or SQLAlchemy dependency enters domain/application.
- Public diagnostics and VinFast acceptance benchmarks remain distinct.
- Model/NLI graders require current calibration bound to exact implementation.
- Do not add persistence or runner mechanics before the planning behavior passes.

## Done when

- Benchmark, metric, grader and calibration domain values validate invariants.
- Application ports resolve exact immutable revisions.
- Planner pins suite, harness, runner, environment, graders, metrics and budgets.
- Missing, expired or mismatched calibration fails closed.
- Public diagnostics cannot become acceptance-authority plans.
- Focused and full AI verification pass.

## Checkpoint

- Implemented immutable benchmark planning over exact benchmark, metric, grader
  and calibration revisions.
- Calibration evidence is bound to grader definition and implementation
  digests; NLI/model-judge calibration cannot be bypassed.
- Evaluation emits no promotion state; Governance remains the decision
  authority.
- Exact next action: add durable registries and resumable execution under
  VFBIZ-0156 after this boundary is accepted.

## Evidence

- [x] `cd backend/ai && uv run pytest tests/evaluation tests/architecture/test_module_boundaries.py -q` — passed
- [x] `npm run verify:ai` — 456 passed, 80 integration tests explicitly skipped by the local fast profile
- [x] Independent read-only review — PASS after resolving five prioritized fail-closed and ownership findings

### ready — 2026-07-28T14:16:31.658Z

Domain/application planning scope locked; persistence and runner deferred.

### active — 2026-07-28T14:16:31.793Z

Begin test-first benchmark/grader registry foundation.

### checkpoint — 2026-07-28

Benchmark/grader planning boundary implemented and independently reviewed.
PostgreSQL registries and runner mechanics remain deliberately deferred to
VFBIZ-0156.

### review — 2026-07-28T14:27:17.769Z

Immutable benchmark/grader planning passed focused and full AI verification; independent read-only review returned PASS. Persistence and runner remain in VFBIZ-0156.
