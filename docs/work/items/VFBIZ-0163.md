---
id: VFBIZ-0163
title: Repair Dataset tooling after runtime boundary refactor
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
  - backend/ai/scripts/inspect_datasets.py
  - backend/ai/tests/architecture
  - docs/work/items/VFBIZ-0163.md
  - WORK.md
depends_on: []
controlled_signals:
  - ai-dataset
  - architecture
exclusive_resources:
  - ai-dataset-registry
required_checks:
  - npm run verify:ai
  - node tools/check-agent-governance.mjs
revision: 5
review_date: "2026-08-28"
updated_at: "2026-07-28T14:05:36.501Z"
---

# Outcome

Restore the Dataset inspection entrypoint and add central architecture
enforcement after the V11.2 runtime boundary refactor, without reintroducing
network, filesystem, scanner or CLI mechanics into the application layer.

## Constraints

- Preserve all downloaded objects, registry metadata and active WIP.
- The script remains a presentation adapter and may not contain business rules.
- Do not add compatibility modules under the removed application paths.

## Done when

- `inspect_datasets.py` imports the canonical presentation/application facades.
- A central architecture test rejects forbidden Dataset application imports and
  cross-context deep imports.
- Focused tests and the full AI verification pass.

## Checkpoint

- Exact next action: update the stale Dataset inspection import and extend the
  central architecture suite with the enforced dependency rules.

## Evidence

- [x] `npm run verify:ai` — passed 2026-07-28 after the final alias hardening:
      Ruff, Pyright, 442 tests and Alembic SQL generation.
- [x] `node tools/check-agent-governance.mjs` — passed 2026-07-28 with 75 provider-neutral scenarios

### active — 2026-07-28T13:26:41.979Z

Repair post-refactor Dataset tooling and central architecture enforcement.

### active — 2026-07-28T13:28:36.226Z

Dataset inspection entrypoint uses the presentation worker, central architecture tests enforce application boundaries, and verify:ai passes 437 tests. Exact next action: independent focused review, then move to review.

### review — 2026-07-28T14:05:36.501Z

Full AI verification and focused boundary review pass.
