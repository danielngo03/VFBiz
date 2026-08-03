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
revision: 6
review_date: "2026-08-28"
updated_at: "2026-07-30T23:22:54+07:00"
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
- Added a content-addressed Vietnamese Golden-grade rehearsal lane for local
  plumbing and policy evaluation. Review rejected v1 and v2 for semantic family
  and store-dispatch defects; both immutable digests remain local rejected
  evidence.
- Current v3 candidate is
  `sha256:bf33480e1ad55c8374930ce53a63a16b04857921c5a6c16f70cf0f49d26b9279`.
  It contains exactly 100 pending evaluation-only cases across 9 suites and 85
  semantic families. Exact fact keys prevent `5 mét`/`1,5 mét` collision; the
  v3 store invokes the v3 semantic verifier before write and on read.
- The manifest pins generator, suite, rubric, domain-pack and board-policy
  digests, keeps all human/independent approval arrays empty, and declares
  `golden=false`, `human_adjudicated=false`, `training_eligible=false`,
  `release_eligible=false` and `public_serving_eligible=false`.
- Two independent review cycles were exhausted on rejected v1/v2. Deterministic
  CI verifies the v3 corrections; v3 is not independently accepted and cannot
  produce metrics, Golden progress, training, retrieval or release evidence.
- Exact next action: add durable human annotation persistence and issue the
  Product/Brand/Data/Privacy/Legal SME assignment packet. Do not convert any
  rehearsal case to Golden evidence before those named humans act.

## Evidence

- [x] `npm run verify:ai` — 396 tests passed; 100 generated cases validated against Golden v2 schema
- [x] `npm run contracts:lint` — passed before the workflow checkpoint
- [x] `npm run governance:check` — passed after Dataset Platform registration
- [x] `npm run verify:ai` — 629 passed, 95 external-integration skips; Ruff,
      Pyright, pytest and Alembic SQL generation passed with rehearsal v3
- [x] `npm run contracts:lint` — 35 AI contracts, 7 runtime schemas, 61 dataset
      vectors, 8 isolated operations and 24 workforce capabilities passed
- [x] `npm run governance:check` — 186 work items and 75 provider-neutral
      context scenarios passed
- [x] focused v3 tests — exact semantic families, schema validity, re-hash
      substitution rejection, v3 verifier dispatch and idempotent private store
      passed

### ready — 2026-07-28T04:22:37.856Z

Dataset Registry foundation is complete; Golden workflow can now enforce held-out lineage.

### active — 2026-07-28T04:22:38.136Z

Implementing Golden v2 workflow and deterministic 100-case smoke pack.

### active — 2026-07-28T04:26:19.102Z

Golden v2 domain workflow and 100 schema-valid pending smoke candidates implemented in consolidated-checkpoint. Human SME assignment and durable annotation persistence remain next.
