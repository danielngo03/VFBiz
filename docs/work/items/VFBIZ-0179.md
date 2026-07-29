---
id: VFBIZ-0179
title: Emit canonical dataset v4 candidate manifests
status: review
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/.agents/skills/generate-synthetic-dataset/scripts/build_manifest.py
depends_on: []
controlled_signals:
  - ai-dataset
  - public-contract
exclusive_resources:
  - public-contract
required_checks:
  - uv run --directory backend/ai pytest tests/skills/test_dataset_skill_scripts.py -q
revision: 5
review_date: "2026-08-29"
updated_at: "2026-07-28T17:44:25.482Z"
---

# Outcome

Make the synthetic Dataset Manifest builder emit canonical v4 candidates that
can enter curation without a legacy compatibility hop.

## Constraints

- Candidate creation must remain fail-closed and cannot manufacture approval.
- Pending quality evidence must bind to the generated artifact.
- Legacy `--purpose` may map input dimensions but must not change output back to
  the v3 shape.

## Done when

- Generated candidates validate against Dataset Manifest v4.
- Output includes canonical trust zone, processing stage, payload schema,
  provenance, split lock and pending quality evidence.
- Existing duplicate-shard and candidate-only protections remain green.

## Checkpoint

- Exact next action: independent dataset-contract and risk review.

## Evidence

- [x] `uv run --directory backend/ai pytest tests/skills/test_dataset_skill_scripts.py -q`
  — passed 2026-07-29; 8 tests passed.
- [x] `npm run verify:ai` — passed 2026-07-29; Ruff and Pyright clean,
  479 tests passed, 81 environment-gated tests skipped, Alembic offline upgrade
  chain generated successfully.

### checkpoint — 2026-07-29

The builder now emits canonical v4 candidate fields and pending,
artifact-bound quality evidence. It does not create approval authority.
