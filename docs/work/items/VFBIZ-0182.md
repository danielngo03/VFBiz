---
id: VFBIZ-0182
title: Close dataset v4 authority gaps
status: review
mode: controlled
priority: P0
owner_team: data-governance
accountable_role: data-owner
primary_workspace: root
affected_workspaces:
  - root
allowed_paths:
  - contracts/ai/datasets/products/release-manifest.schema.json
  - contracts/ai/test-vectors/dataset-contracts.json
depends_on: []
controlled_signals:
  - ai-dataset
  - public-contract
  - data-governance
exclusive_resources:
  - public-contract
required_checks:
  - npm run contracts:lint
revision: 6
review_date: "2026-08-29"
updated_at: "2026-07-29T05:51:22.816Z"
---

# Outcome

Close fail-open Dataset Manifest v4 lifecycle and evidence-shape gaps identified
by independent review.

## Constraints

- Approval registry remains external authority.
- Contract encodes structural requirements; digest recomputation and evidence
  coverage remain semantic validator responsibilities.

## Done when

- Rolled-back requires rollback target and tombstoned requires tombstone revision.
- Released/decision-ready evidence cannot be expired by shape.
- Negative vectors cover lifecycle, unresolved provenance and digest binding.

## Checkpoint

- Exact next action: independent contract review; Node semantic parity is owned
  by VFBIZ-0184.

## Evidence

- [x] `npm run contracts:lint` — passed 2026-07-29 after fail-closed
  rollback/tombstone and unresolved-provenance conditions.
- [x] `uv run --directory backend/ai pytest tests/contract/test_dataset_contract_vectors.py -q`
  — passed 2026-07-29 after content hash and mandatory evidence-expiry vectors
  were aligned.

### active — 2026-07-29

Schema lifecycle gaps are closed. Work remains active because cross-language
negative vectors and Node semantic parity are not complete.

### checkpoint — 2026-07-29

Decision-ready/released quality evidence now requires an explicit expiry.
Canonical positive vectors bind the ordered artifact hash. Cross-runtime
semantic parity is delegated to VFBIZ-0184 and remains a release blocker.

### active — 2026-07-28T17:54:55.198Z

Lifecycle schema hardened; exact next action is cross-language vectors and Node parity.
