---
id: VFBIZ-0183
title: Enforce dataset v4 semantic authority
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
  - backend/ai/tests/unit/datasets/test_manifest_v4_migration.py
depends_on: []
controlled_signals:
  - ai-dataset
  - data-governance
exclusive_resources:
  - ai-dataset-registry
required_checks:
  - uv run --directory backend/ai pytest tests/unit/datasets/test_manifest_v4_migration.py -q
revision: 7
review_date: "2026-08-29"
updated_at: "2026-07-29T05:57:26.306Z"
---

# Outcome

Enforce content binding, complete/current quality evidence, resolved provenance
and schema-first legacy import in the canonical Python authority.

## Constraints

- Human approval still resolves against the external approval registry.
- Candidate placeholder provenance remains usable for curation but cannot cross
  decision-ready.

## Done when

- Artifact address equals SHA-256 and content hash is deterministically recomputed.
- Every artifact is covered by current verified evidence for release.
- Unresolved source revision cannot become decision-ready/released.
- Importer rejects malformed v3 before assigning v4 identity.

## Checkpoint

- Exact next action: VFBIZ-0185 binds decision-ready/released source revisions
  and artifact digests to the immutable Dataset Registry before activation.

## Evidence

- [x] `uv run --directory backend/ai pytest tests/unit/datasets/test_manifest_v4_migration.py -q`
  — passed 2026-07-29; focused suite now covers schema-first v3 import,
  address/hash binding, evidence coverage/expiry, duplicate artifacts,
  provenance sentinels and approval decision identity.

### active — 2026-07-29

Python release semantics now fail closed for the five reviewed authority gaps
except schema-first v3 import. The work item remains active.

### active — 2026-07-29

Schema-first v3 input and v4 output validation are now mandatory through an
injected contract authority. Dataset Registry resolution remains open and is
the exact activation blocker; syntactic manifest validation is not approval.

### active — 2026-07-28T17:54:55.481Z

Python semantics hardened; exact next action is schema-first v3 import and Node parity.

### active — 2026-07-29T05:57:26.306Z

Schema-first import and semantic parity complete; Dataset Registry provenance binding remains the exact blocker.

### checkpoint — 2026-07-29

The third same-cause implementation claim was correctly rejected by
agent-control. Registry binding is separated into VFBIZ-0185 rather than
bypassing retry fencing.
