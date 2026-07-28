---
id: VFBIZ-0154
title: Define ViVi AI Quality Platform contracts and boundaries
status: review
mode: controlled
priority: P0
owner_team: data-governance
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - contracts/ai/evaluation
  - contracts/ai/index.json
  - contracts/ai/test-vectors
  - docs/work/items/VFBIZ-0154.md
  - WORK.md
depends_on: []
controlled_signals:
  - ai-quality-platform
  - benchmark-runner
  - grader-calibration
exclusive_resources:
  - public-contract
required_checks:
  - npm run contracts:lint
revision: 4
review_date: "2026-08-28"
updated_at: "2026-07-28T14:05:36.366Z"
---

# Outcome

Lock the canonical AI Quality contracts for reproducible
benchmark planning, grader calibration, baseline comparison and immutable
evaluation evidence without granting Evaluation release authority.

## Constraints

- Evaluation produces evidence only; Governance and named humans decide release.
- Dataset suites and execution policy remain separate artifacts.
- Public diagnostics cannot become VinFast acceptance authority.
- No runner, provider adapter or database migration is added before the contract
  vectors and domain invariants fail for the intended reason.

## Done when

- Stable contract IDs cover benchmark definition, run request/result, case
  result, grader definition/calibration, baseline policy, evidence and drift.
- Contract vectors reject unpinned suite, harness, grader, environment, budget,
  seed, invalid lifecycle and composite-score-only decisions.
- Contract IDs and compatibility vectors are the single authority consumed by
  the later Evaluation runtime work item.
- Follow-up documentation must distinguish Implemented, Candidate, Target-only
  and Human-blocked capabilities without overstating this contract foundation.

## Checkpoint

- Nine canonical schemas and 41 shared vectors now cover immutable suite and
  release identity, bounded attempts/budgets, case evidence, calibrated graders,
  quantitative baseline comparison, privacy-safe drift and evidence-only
  recommendations.
- Independent review findings were addressed: public diagnostics cannot
  recommend a release, valid cases require output and grader evidence,
  incomplete runs cannot become decision-ready, and calibration matrix totals
  are checked semantically.
- Exact next action: final independent re-review, then move the contract
  foundation to review without claiming the benchmark runner is implemented.

## Evidence

- [x] `npm run contracts:lint` — 30 registered AI contracts, 41 shared vectors,
      five OpenAPI documents and 24 Workforce capabilities passed 2026-07-28.

### active — 2026-07-28T13:29:32.851Z

Begin test-first canonical AI Quality contracts and domain boundary implementation.

### review — 2026-07-28T14:05:36.366Z

Implementation gates pass; independent reviewer closed all contract and parity blockers.
