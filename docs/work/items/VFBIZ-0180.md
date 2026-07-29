---
id: VFBIZ-0180
title: Correct dataset v4 semantic vector authority
status: review
mode: controlled
priority: P0
owner_team: data-governance
accountable_role: data-owner
primary_workspace: root
affected_workspaces:
  - root
allowed_paths:
  - contracts/ai/test-vectors/dataset-contracts.json
depends_on: []
controlled_signals:
  - ai-dataset
  - public-contract
exclusive_resources:
  - public-contract
required_checks:
  - npm run contracts:lint
revision: 5
review_date: "2026-08-29"
updated_at: "2026-07-28T17:47:37.774Z"
---

# Outcome

Make the duplicate-human-approval negative vector exercise Dataset Manifest v4
semantic authority instead of failing incidentally against the v3 shape.

## Constraints

- Do not weaken v3 import-only validation.
- The vector must be schema-valid before semantic validation rejects it.

## Done when

- The vector resolves v4 and is rejected for duplicate human actors.
- Contract lint remains green.

## Checkpoint

- Exact next action: independent contract review.

## Evidence

- [x] `npm run contracts:lint` — passed 2026-07-29; duplicate-human vector
  resolves v4 and the 44-vector contract suite remains green.

### checkpoint — 2026-07-29

The negative vector now fails v4 semantic authority for the intended
separation-of-duties reason rather than incidental v3 shape mismatch.
