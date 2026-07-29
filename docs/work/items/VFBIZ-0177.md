---
id: VFBIZ-0177
title: Enforce dataset v4 in runtime contract gate
status: review
mode: controlled
priority: P0
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
allowed_paths:
  - tools/check-runtime-contracts.mjs
  - tests/governance/check-dataset-v4-runtime-contract.mjs
depends_on: []
controlled_signals:
  - ai-dataset
  - governance
  - public-contract
exclusive_resources:
  - public-contract
required_checks:
  - node tests/governance/check-dataset-v4-runtime-contract.mjs
  - npm run contracts:lint
revision: 4
review_date: "2026-08-29"
updated_at: "2026-07-28T17:39:21.833Z"
---

# Outcome

Make the deterministic runtime-contract gate load Dataset Manifest v4 and
apply v4 semantic authority checks while retaining explicit v3 import vectors.

## Constraints

- Do not move schema authority into the governance test.
- V3 vectors remain compatibility evidence; v4 is the only runtime release
  manifest.
- Self-test must exercise an invalid v4 release, not source-code text matching.

## Done when

- Runtime contract output identifies v4 as the active dataset release schema.
- Duplicate approval actors and artifact-unbound quality evidence fail the v4
  semantic self-test.
- Existing conversation and dataset contract checks remain green.

## Checkpoint

- Exact next action: independent contract and risk review of the v4 runtime gate.

## Evidence

- [x] `node tests/governance/check-dataset-v4-runtime-contract.mjs` — passed
  2026-07-29; exercised duplicate approval actors and unbound quality evidence.
- [x] `npm run contracts:lint` — passed 2026-07-29; 31 registered AI
  contracts, 44 dataset vectors, Dataset Manifest v4 reported active.

### ready — 2026-07-28T17:33:29.133Z

V4 contract exists; root gate adoption is isolated from AI runtime code.

### active — 2026-07-28T17:33:29.414Z

Begin TDD for v4 runtime contract authority self-test.

### checkpoint — 2026-07-29

The deterministic gate now resolves the canonical v4 schema, retains explicit
v3 import vectors and fails its self-test when v4 release authority is invalid.
