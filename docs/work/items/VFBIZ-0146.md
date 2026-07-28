---
id: VFBIZ-0146
title: Enforce canonical ViVi source catalog
status: done
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
  - backend/ai/dataset-specs
  - backend/ai/docs/knowledge-data-governance.md
  - backend/ai/.agents/skills/onboard-dataset
  - backend/ai/tests/skills/test_dataset_skill_scripts.py
  - tools/check-agent-governance.mjs
  - tests/governance/scenarios.json
  - docs/work/items/VFBIZ-0146.md
  - WORK.md
depends_on:
  - VFBIZ-0145
controlled_signals:
  - dataset-source
  - dataset-release
  - contract
exclusive_resources:
  - public-contract
  - ai-source-registry
required_checks:
  - npm run contracts:lint
  - npm run verify:ai
  - npm run verify:governance
revision: 8
review_date: "2026-08-28"
updated_at: "2026-07-28T10:31:46.086Z"
---

# Outcome

Replace the deprecated public-source monolith with independently validated
source catalog entries whose registry status never exceeds available approval
evidence.

## Constraints

- Preserve source IDs, upstream revisions, selectors, bindings and immutable
  quarantine evidence references.
- Quarantine checksum or scan evidence is not Legal/Data approval.
- Do not fabricate approval actors, rights decisions or purpose approval.
- Do not modify downloaded payloads under `local-data`.
- Catalog status and runtime Source Register status remain distinct concepts.

## Done when

- One canonical catalog-entry schema validates every public source manifest.
- Active quarantine candidates without approval envelopes are represented as
  `candidate`, not `fetch-approved` or `purpose-approved`.
- Governance and dataset skill tests read per-source manifests through a
  deterministic catalog index.
- `public-source-candidates.json` is removed without losing any candidate or
  source-register metadata.
- No source becomes usable for training, evaluation or knowledge release as a
  side effect of the migration.

## Checkpoint

- Exact next action: independently review approval-state downgrades, source
  preservation and catalog isolation before closure.

## Evidence

- [x] `npm run contracts:lint` — passed at `consolidated-checkpoint`; 21 registered AI
  contracts and 18 dataset vectors validated.
- [x] `npm run verify:ai` — passed at `consolidated-checkpoint`; 433 tests passed and
  80 environment-bound tests remained explicitly skipped.
- [x] `npm run verify:governance` — passed at `consolidated-checkpoint`; catalog entries,
  embedded Source Register snapshots, adapters, work-control and routing
  scenarios validated.

### ready — 2026-07-28T10:23:33.048Z

VFBIZ-0145 is complete; catalog authority and approval-evidence gap are bounded.

### active — 2026-07-28T10:23:33.180Z

Begin fail-closed source catalog migration; no payload or approval mutation is authorized.

### review — 2026-07-28T10:28:56.651Z

Fail-closed catalog migration committed at consolidated-checkpoint. Begin independent verification of metadata preservation, approval boundaries and evaluation isolation.

### blocked — 2026-07-28T10:30:05.668Z

Independent preservation check found overlapping MASSIVE and Bitext research snapshots omitted by the prior catalog merge.

### active — 2026-07-28T10:30:05.801Z

Restore both Source Register snapshots exactly, retain Legal Hold, and update canonical governance documentation.

### review — 2026-07-28T10:31:25.142Z

Preservation finding fixed at consolidated-checkpoint; all 11 legacy Source Register snapshots now match exactly and Legal Hold remains fail-closed. Begin final independent review.

### done — 2026-07-28T10:31:46.086Z

Final reviews verified 28 indexed manifests, exact preservation of all 11 legacy Source Register snapshots, zero approval escalation and strict separation between catalog state and runtime approval.
