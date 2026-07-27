---
id: VFBIZ-0109
title: Synchronize generated knowledge documentation index
status: done
mode: bounded
priority: P1
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
  - ai
allowed_paths:
  - docs/INDEX.md
  - docs/INDEX.json
  - docs/work/items/VFBIZ-0109.md
  - WORK.md
depends_on: []
controlled_signals:
  - documentation
exclusive_resources:
  - generated-doc-index
required_checks:
  - npm run governance:check
revision: 5
review_date: "2026-07-25"
updated_at: "2026-07-25T15:29:44.297Z"
---

# Outcome

Generated documentation catalogs reflect the reviewed Knowledge Release revision
without manual index edits or unrelated documentation changes.

## Constraints

- Index content is generated only by `tools/docs-index.mjs`.
- This lane does not change canonical architecture content.

## Done when

- `docs/INDEX.md` and `docs/INDEX.json` match a clean deterministic generation.
- Governance check passes without leaving generated drift.

## Checkpoint

- Exact next action: generate catalogs, verify drift and close the bounded lane.

## Evidence

- [x] `npm run governance:check` — passed after deterministic index generation;
      reports, guides, authorization, 106 work items and 61 routing scenarios
      remained current.
