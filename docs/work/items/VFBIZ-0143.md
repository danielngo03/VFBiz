---
id: VFBIZ-0143
title: Normalize canonical ViVi dataset contracts
status: done
mode: controlled
priority: P0
owner_team: data-governance
accountable_role: data-owner
primary_workspace: root
affected_workspaces:
  - root
  - ai
allowed_paths:
  - contracts/ai
  - backend/ai/dataset-specs/contracts
  - docs/work/items/VFBIZ-0143.md
  - WORK.md
depends_on:
  - VFBIZ-0133
controlled_signals:
  - dataset-source
  - dataset-release
  - contract
exclusive_resources:
  - ai-dataset-contracts
  - ai-source-registry
required_checks:
  - npm run contracts:lint
  - npm run verify:ai
revision: 7
review_date: "2026-08-28"
updated_at: "2026-07-28T09:51:52.396Z"
---

# Outcome

Replace conflated dataset purpose fields with independent asset kind, allowed
use, task family, modality and split role contracts.

## Constraints

- One primary allowed use per release.
- Golden, held-out evaluation and red-team records can never become training,
  knowledge-index or synthetic seed artifacts.
- Contract vectors must validate identically in TypeScript and Python.

## Done when

- The canonical schemas express all V10.1 dimensions.
- Duplicate local schema copies are removed.
- Positive and negative cross-language vectors pass.

## Evidence

- [x] `npm run contracts:lint` — 18 cross-language dataset vectors passed.
- [x] `npm run verify:ai` — 411 tests passed; 79 fast-suite integration skips.

## Checkpoint

- Canonical release/source/record contracts now expose the V10.1 dimensions.
- Fetch Plan và Fetch Result là hai contract riêng; schema copy trùng trong
  `dataset-specs/contracts` đã bị loại.
- Payload contracts đã tách classifier, conversation, preference, tool,
  embedding và reranker.
- Export profile pin destination/format/shard limits và bắt buộc
  `training_submission=false`.
- Checkpoint: `consolidated-checkpoint`.
- Legacy `purpose` and candidate-example fields remain deprecated only to keep
  the current synthetic skill runnable; VFBIZ-0138 must migrate that skill and
  remove this compatibility window before any dataset release.

### review — 2026-07-28T09:51:52.247Z

Implementation checkpoint consolidated-checkpoint entered final review after contracts:lint and verify:ai passed.

### done — 2026-07-28T09:51:52.396Z

Canonical contracts now express trust_zone and processing_stage; post-fix reviewer-verifier and risk-reviewer evidence is complete.
