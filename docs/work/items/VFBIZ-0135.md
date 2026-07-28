---
id: VFBIZ-0135
title: Golden case v2 annotation workflow
status: active
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai/app/modules/datasets
  - backend/ai/tests/unit/datasets
  - docs/work/items/VFBIZ-0135.md
  - WORK.md
depends_on:
  - VFBIZ-0133
  - VFBIZ-0134
controlled_signals:
  - ai-evaluation
  - dataset-release
exclusive_resources:
  - ai-dataset-registry
required_checks:
  - npm run verify:ai
  - npm run contracts:lint
  - npm run governance:check
revision: 5
review_date: "2026-08-28"
updated_at: "2026-07-28T04:26:19.102Z"
---

# Outcome

Golden case v2 có annotation/adjudication workflow, locked held-out families và
immutable human-review evidence cho Customer Assistant.

## Constraints

- Automated judge tạo evidence, không thay human SME/Data Owner.
- Evaluation case chỉ có `allowed_use=evaluation`.

## Done when

- Workflow rejects self-review/self-adjudication and cases without independent evidence.
- Every case is evaluation-only and locks a split family before annotation.
- Deterministic smoke generation produces exactly 100 schema-ready candidates across the approved suite allocation.
- Release selection rejects duplicate family fingerprints and any non-adjudicated case.

## Checkpoint

- Implemented an evaluation-only state machine with independent author,
  reviewer and adjudicator roles. A deterministic generator now emits 100
  schema-valid synthetic smoke candidates across the approved allocation.
- These records remain `review.status=pending`; they are not Golden evidence and
  are not training data.
- Exact next action: add durable annotation persistence and assign human SMEs
  before any case can become adjudicated.

## Evidence

- [x] `npm run verify:ai` — 396 tests passed; 100 generated cases validated against Golden v2 schema
- [x] `npm run contracts:lint` — passed before the workflow checkpoint
- [x] `npm run governance:check` — passed after Dataset Platform registration

### ready — 2026-07-28T04:22:37.856Z

Dataset Registry foundation is complete; Golden workflow can now enforce held-out lineage.

### active — 2026-07-28T04:22:38.136Z

Implementing Golden v2 workflow and deterministic 100-case smoke pack.

### active — 2026-07-28T04:26:19.102Z

Golden v2 domain workflow and 100 schema-valid pending smoke candidates implemented in consolidated-checkpoint. Human SME assignment and durable annotation persistence remain next.
