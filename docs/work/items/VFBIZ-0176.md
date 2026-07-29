---
id: VFBIZ-0176
title: Adopt dataset manifest v4 in AI runtime
status: review
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/modules/datasets
  - backend/ai/.agents/skills/generate-synthetic-dataset
  - backend/ai/tests/unit/datasets
  - backend/ai/docs/dataset-engineering.md
depends_on: []
controlled_signals:
  - ai-dataset
  - data-governance
  - public-contract
exclusive_resources:
  - ai-dataset-registry
required_checks:
  - uv run --directory backend/ai pytest tests/unit/datasets -q
  - uv run --directory backend/ai pyright app
revision: 4
review_date: "2026-08-29"
updated_at: "2026-07-28T17:32:12.528Z"
---

# Outcome

Provide the only supported v3-to-v4 Dataset Manifest migration path and make
all AI-side release validation use the canonical v4 schema and invariants.

## Constraints

- V3 input is never mutated in place and can only produce a v4 candidate.
- Import records a deterministic migration digest and source manifest digest.
- Import never copies approval evidence into release authority.
- Validation remains schema-first; semantic rules must not duplicate the JSON
  Schema shape by hand.

## Done when

- `LegacyDatasetManifestImporter` maps every legacy purpose explicitly or fails.
- V3 decision-ready/released input is rejected before transformation.
- V4 semantic validation checks count parity, partition parity, artifact-bound
  quality evidence and independent approval actors.
- Unit tests observe v3 rejection, deterministic candidate conversion and v4
  evidence failures before the implementation is added.

## Checkpoint

- Exact next action: write failing importer and v4 semantic-validator tests.

## Evidence

- [x] `uv run --directory backend/ai pytest tests/unit/datasets -q` — 58
  dataset unit tests passed, including v3 rejection, deterministic import and
  v4 semantic authority failures.
- [x] `uv run --directory backend/ai pyright app` — 0 errors, 0 warnings.

### ready — 2026-07-28T17:24:11.373Z

AI Knowledge Engineering accepts the v4 migration dependency from coord-60df9c7a-05ed-4acc-9d6a-346b8382f001.

### active — 2026-07-28T17:24:11.651Z

Begin TDD for import-only v3 compatibility and v4 evidence validation.

### review — 2026-07-28T17:32:12.528Z

Importer and canonical v4 semantics are code-complete with focused unit and type evidence; independent AI Assurance/risk review remains required.
