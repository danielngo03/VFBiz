---
id: VFBIZ-0184
title: Align Node dataset v4 semantic authority
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
  - public-contract
exclusive_resources:
  - public-contract
required_checks:
  - node tests/governance/check-dataset-v4-runtime-contract.mjs
  - npm run contracts:lint
revision: 5
review_date: "2026-08-29"
updated_at: "2026-07-29T05:57:26.005Z"
---

# Outcome

Make Node and Python enforce the same Dataset Manifest v4 semantic authority.

## Constraints

- Self-test must execute invalid manifests, not inspect source text.
- Approval registry binding remains external to manifest validation.

## Done when

- Node rejects mismatched artifact address/hash, invalid content hash, missing or
  expired evidence, duplicate artifacts/decisions and unresolved provenance.
- Existing v3 import vectors remain supported.

## Checkpoint

- Exact next action: independent contract and risk review.

## Evidence

- [x] `node tests/governance/check-dataset-v4-runtime-contract.mjs` — passed
  2026-07-29 with executable mutations for address/hash, evidence
  coverage/expiry, duplicate artifact/decision and unresolved provenance.
- [x] `npm run contracts:lint` — passed 2026-07-29 with 44 dataset vectors.

### checkpoint — 2026-07-29

Node now enforces the same v4 semantic invariants as Python while preserving
v3 import-only semantics.
