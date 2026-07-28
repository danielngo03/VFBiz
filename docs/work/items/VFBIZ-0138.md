---
id: VFBIZ-0138
title: Synthetic candidate factory and independent review
status: active
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai
  - contracts/ai
  - docs/work/items/VFBIZ-0138.md
  - WORK.md
depends_on:
  - VFBIZ-0133
controlled_signals:
  - synthetic-dataset
  - dataset-release
exclusive_resources:
  - ai-dataset-registry
required_checks:
  - npm run verify:ai
  - npm run contracts:lint
  - npm run governance:check
revision: 4
review_date: "2026-08-28"
updated_at: "2026-07-28T06:18:00Z"
---

# Outcome

Synthetic factory sinh resumable disjoint shards theo approved job, budget và
coverage, rồi chuyển independent reviewer mà không tự release.

## Constraints

- Held-out split phải khóa trước generation; không production PII/customer chat.
- Generator và reviewer không cùng role trong một release.

## Done when

- Schema, dedup, contamination, coverage, lease và review gates có deterministic evidence.

## Checkpoint

- V10.1 writers now emit orthogonal classification dimensions and reject
  deprecated purpose-only candidate records.
- Golden adjudication requires three distinct evidence-bearing human roles.
- Export requires schema, DLP, dedup, contamination and independent-review
  gates to pass.
- Held-out split lock covers source record, content hash, split family and
  contamination fingerprint; the CLI additionally checks MinHash similarity.
- Google SFT, preference and embedding artifacts use destination-specific
  schemas and split-specific outputs. This work item does not upload or submit
  a training job.
- Local object storage is private by default; GCS create-only conflicts verify
  immutable metadata before being treated as idempotent success.
- Exact next action: move the downloaded Wave A inputs through canonical fetch
  plans/results and content-addressed quarantine under VFBIZ-0134/0143 before
  any purpose approval or release.

## Evidence

- [x] `npm run verify:ai` — 411 passed, 79 fast-suite external-integration skips;
      Ruff, Pyright and Alembic SQL generation passed.
- [x] `npm run contracts:lint` — five OpenAPI contracts, six runtime schemas,
      fourteen dataset vectors and capability contract checks passed.
- [ ] `npm run governance:check` — deferred to the contract/source-register
      lane because the repository has pre-existing documentation-index drift.
