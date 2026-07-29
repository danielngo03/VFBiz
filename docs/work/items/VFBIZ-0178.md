---
id: VFBIZ-0178
title: Align Python dataset contract parity with v4
status: review
mode: controlled
priority: P0
owner_team: ai-platform-foundation
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/tests/contract/test_dataset_contract_vectors.py
depends_on: []
controlled_signals:
  - ai-dataset
  - public-contract
  - ai-quality-platform
exclusive_resources:
  - public-contract
required_checks:
  - uv run --directory backend/ai pytest tests/contract/test_dataset_contract_vectors.py -q
revision: 5
review_date: "2026-08-29"
updated_at: "2026-07-28T17:40:02.951Z"
---

# Outcome

Make the Python contract-vector gate apply the same canonical Dataset Manifest
semantic authority to v3 compatibility imports and v4 runtime releases.

## Constraints

- Do not duplicate release semantics in the test.
- Resolve schemas through the canonical contract registry.
- V3 remains import-only; v4 is the only release-capable contract.

## Done when

- Python contract vectors execute the production manifest semantic validator for
  both v3 and v4 contract IDs.
- A v4 duplicate-approval or unbound-quality-evidence vector cannot pass merely
  because its JSON Schema shape is valid.
- The focused contract suite is green.

## Checkpoint

- Exact next action: independent contract and risk review of Python/Node parity.

## Evidence

- [x] `uv run --directory backend/ai pytest tests/contract/test_dataset_contract_vectors.py -q`
  — passed 2026-07-29; both tests passed and v3/v4 use the canonical semantic
  validator.

### checkpoint — 2026-07-29

Python contract parity now applies the production semantic validator to both
the v3 compatibility schema and the v4 runtime release schema.
