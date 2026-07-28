---
id: VFBIZ-0165
title: Align Python AI contract vectors with canonical registry
status: review
mode: controlled
priority: P0
owner_team: ai-platform-foundation
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai/tests/contract/test_dataset_contract_vectors.py
  - docs/work/items/VFBIZ-0165.md
  - WORK.md
depends_on: []
controlled_signals:
  - ai-quality-platform
  - schema
exclusive_resources: []
required_checks:
  - cd backend/ai && uv run pytest tests/contract/test_dataset_contract_vectors.py
  - npm run verify:ai
revision: 4
review_date: "2026-08-28"
updated_at: "2026-07-28T14:05:36.770Z"
---

# Outcome

Make Python contract compatibility tests resolve the same stable contract IDs
and canonical registry paths as Node tooling.

## Constraints

- Do not add Python-specific contract aliases.
- Reject unknown IDs, missing schemas and registry `$id` mismatches.
- Preserve dataset semantic validation parity.

## Done when

- Contract vectors may use stable `contractId`.
- Python loads the canonical path from `contracts/ai/index.json`.
- Focused and full AI verification pass.

## Checkpoint

- Python now resolves stable contract IDs through `contracts/ai/index.json`,
  verifies `$id` binding and preserves semantic validation parity.
- Single-class calibration fails closed identically in Node and Python.
- Independent focused review returned PASS.
- Exact next action: move to controlled review with the recorded evidence.

## Evidence

- [x] `cd backend/ai && uv run pytest tests/contract/test_dataset_contract_vectors.py` — passed.
- [x] `npm run verify:ai` — Ruff, Pyright, 442 tests and Alembic SQL generation
      passed 2026-07-28.

### ready — 2026-07-28T13:52:22.959Z

Cross-language registry scope locked.

### active — 2026-07-28T13:52:23.093Z

Repair Python canonical contract resolution test-first.

### review — 2026-07-28T14:05:36.770Z

Cross-language contractId and semantic parity independently reviewed PASS.
