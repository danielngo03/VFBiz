---
id: VFBIZ-0144
title: Normalize ViVi dataset specification architecture
status: done
mode: controlled
priority: P0
owner_team: data-governance
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai/dataset-specs
  - backend/ai/docs/dataset-engineering.md
  - docs/work/items/VFBIZ-0144.md
  - WORK.md
depends_on:
  - VFBIZ-0143
controlled_signals:
  - dataset-source
  - dataset-release
  - architecture
exclusive_resources:
  - ai-dataset-registry
  - ai-source-registry
required_checks:
  - npm run contracts:lint
  - npm run verify:ai
  - npm run governance:check
revision: 5
review_date: "2026-08-28"
updated_at: "2026-07-28T10:12:01.609Z"
---

# Outcome

Replace temporal/mixed Dataset Factory specifications with a capability-owned
catalog in which source definitions, portfolios, product specifications,
evaluation assets and generated evidence each have one authority.

## Constraints

- Preserve all source IDs, exact revisions, selectors and quarantine bindings.
- Do not move or modify payloads under `local-data`.
- Generated fetch, scan and reconciliation evidence must leave source-spec
  folders; Git retains only a compact immutable evidence index.
- No public source becomes purpose-approved or released through this work item.
- Do not change runtime persistence or canonical contracts in this lane.

## Done when

- `dataset-specs` has capability-based catalog, product, evaluation and domain
  pack boundaries without temporal `wave-*` names.
- Each public source has one independent manifest and portfolios reference IDs.
- Generated evidence is represented by compact digest/URI checkpoints rather
  than large machine-generated payloads in source folders.
- Empty placeholder folders are removed and no new folder lacks a consumer.
- Existing source selection, quarantine and security tests continue to pass.

## Checkpoint

- Exact next action: complete independent architecture and provenance reviews,
  then close the catalog-normalization checkpoint.

## Evidence

- [x] `npm run contracts:lint` — passed at `consolidated-checkpoint`; 18 dataset
  contract vectors validated.
- [x] `npm run verify:ai` — passed at `consolidated-checkpoint`; 433 tests passed and
  80 environment-bound integration tests remained explicitly skipped.
- [x] `npm run governance:check` — passed at `consolidated-checkpoint`; documentation,
  reports, authorization, work-control and 72 provider-neutral routing
  scenarios validated.

### ready — 2026-07-28T09:52:46.792Z

Plan V11.2 approved; VFBIZ-0143 is complete and dataset specification paths are clean.

### active — 2026-07-28T09:52:46.925Z

Begin capability-based catalog migration without touching payloads, runtime persistence or canonical contracts.

### review — 2026-07-28T10:11:07.070Z

Catalog migration committed at consolidated-checkpoint; contract, AI and governance gates passed. Begin independent architecture and provenance review.

### done — 2026-07-28T10:12:01.609Z

Independent architecture and risk reviews found no unresolved finding. Capability catalog, immutable historical evidence index and evaluation boundaries are accepted at consolidated-checkpoint.
