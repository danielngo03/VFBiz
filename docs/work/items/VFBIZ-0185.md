---
id: VFBIZ-0185
title: Bind dataset release provenance to registry authority
status: active
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/modules/datasets/application/curation
  - backend/ai/app/modules/datasets/application/ports/registry.py
  - backend/ai/app/modules/datasets/infrastructure/postgres_registry.py
  - backend/ai/tests/unit/datasets/test_release_provenance.py
  - backend/ai/tests/integration/datasets/test_postgres_dataset_registry.py
depends_on: []
controlled_signals:
  - ai-dataset
  - data-governance
exclusive_resources:
  - ai-dataset-registry
required_checks:
  - uv run --directory backend/ai pytest tests/unit/datasets/test_release_provenance.py -q
  - VFBIZ_RUN_DB_INTEGRATION=1 uv run --directory backend/ai pytest tests/integration/datasets/test_postgres_dataset_registry.py -q
revision: 2
review_date: "2026-08-29"
updated_at: "2026-07-29T06:05:00Z"
---

# Outcome

Prevent a decision-ready or released Dataset Manifest from crossing the
activation boundary unless every exact source revision and source artifact
digest resolves to purpose-approved, scan-passed state in Dataset Registry.

## Constraints

- Manifest semantic validation remains synchronous and infrastructure-free.
- Registry provenance validation is a separate application authority.
- Human approval continues to resolve through the external approval registry.
- Candidate manifests may retain unresolved provenance but cannot be promoted.

## Done when

- Registry resolves source by stable source key and exact revision.
- Registry proves the requested allowed use was purpose-approved.
- Registry proves the referenced source artifact digest completed scan-passed.
- Missing, tombstoned, mismatched or unapproved provenance fails closed.
- PostgreSQL integration covers exact revision, purpose and digest matching.

## Checkpoint

- Exact next action: VFBIZ-0186 must wire this authority into an atomic
  PostgreSQL promotion boundary with row locking/fencing; this work item stays
  active until that production caller exists.

## Evidence

- [x] `uv run --directory backend/ai pytest tests/unit/datasets/test_release_provenance.py -q`
  — 7 passed on 2026-07-29.
- [x] `VFBIZ_RUN_DB_INTEGRATION=1 uv run --directory backend/ai pytest tests/integration/datasets/test_postgres_dataset_registry.py -q`
  — 3 passed against migrated PostgreSQL on 2026-07-29; no skip.

### active — 2026-07-29

The application authority and PostgreSQL resolver now fail closed on missing,
mismatched, unapproved, unscanned or invalid source evidence. Independent
review correctly rejected completion because no production promotion caller
exists and the read-only resolver is not atomic with release commit. VFBIZ-0186
owns that integration; human approval remains external.
