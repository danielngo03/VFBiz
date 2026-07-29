---
id: VFBIZ-0167
title: Harden dataset release contract authority
status: review
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
depends_on: []
controlled_signals:
  - ai-dataset
  - data-governance
  - public-contract
exclusive_resources:
  - ai-dataset-registry
required_checks:
  - npm run contracts:lint
  - npm run verify:ai
revision: 5
review_date: "2026-08-29"
updated_at: "2026-07-28T17:45:19.101Z"
---

# Outcome

Make the canonical Dataset Release Manifest fail closed so legacy `purpose`
payloads cannot become decision-ready or released, while preserving one
explicit import-only path from v3 candidate data into canonical v4 candidates.

## Constraints

- Do not rewrite or silently reinterpret an existing released artifact.
- V3 is input to a compatibility importer only; runtime release validation uses
  v4 exclusively.
- Preserve stable contract IDs through the contract registry and migrate every
  consumer atomically.
- Human approval evidence remains external authority and must not be fabricated.

## Done when

- V4 requires canonical classification, payload, provenance, quality evidence
  and split-lock fields for `decision-ready` and `released`.
- A v3 manifest containing only deprecated `purpose` cannot validate as
  decision-ready or released.
- Positive and negative vectors cover v3 import, canonical candidate,
  decision-ready, released, evaluation isolation and red-team isolation.
- Contract lint and AI contract consumers pass without duplicate authorities.

## Checkpoint

- Exact next action: independent contract, data-governance and risk review.

## Evidence

- [x] `npm run contracts:lint` — passed 2026-07-29; v4 is the active
  runtime schema and 44 dataset vectors passed.
- [x] `npm run verify:ai` — passed 2026-07-29; Ruff and Pyright clean,
  479 tests passed, 81 environment-gated tests skipped, Alembic offline upgrade
  chain generated successfully.

### ready — 2026-07-28T17:14:02.269Z

Approved V13 scope translated into a fail-closed contract work item.

### active — 2026-07-28T17:14:02.552Z

Begin test-first v3 bypass regression and v4 authority implementation.

### active — 2026-07-28T17:23:27.412Z

V4 canonical schema and v3 import-only contract are drafted; contracts:lint passes with 44 vectors. Blocking coordination coord-60df9c7a-05ed-4acc-9d6a-346b8382f001 owns Python/runtime consumer migration. Exact next action: implement v3 importer and v4 semantic validator in AI Assurance.

### checkpoint — 2026-07-29

The canonical schema, compatibility importer, Node/Python parity gates and
candidate producer now use Dataset Manifest v4. No approval authority is
fabricated; all implementation work remains pending independent review.
