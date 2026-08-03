---
id: VFBIZ-0202
title: Build evidence-gated Vertex tuning candidate workflow
status: proposed
mode: controlled
priority: P0
owner_team: ai-model-platform
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai/app/modules/datasets
  - backend/ai/app/modules/evaluation
  - backend/ai/app/infrastructure
  - backend/ai/dataset-specs
  - backend/ai/tests
  - .agents/skills/build-tuning-candidate
  - docs/work/plans/vivi-gcp-ai-platform.md
  - docs/work/items/VFBIZ-0202.md
  - WORK.md
depends_on:
  - VFBIZ-0196
  - VFBIZ-0201
  - VFBIZ-0139
controlled_signals:
  - ai-dataset
  - fine-tuning
  - ai-evaluation
exclusive_resources:
  - ai-dataset-registry
  - ai-evaluation-suite-registry
  - ai-provider-registry
required_checks:
  - npm run contracts:lint
  - npm run verify:ai
  - npm run verify:ai:integration
  - npm run governance:check
revision: 1
review_date: "2026-08-30"
updated_at: "2026-07-30T00:00:00+07:00"
---

# Outcome

Create a human-authorized, budget-fenced Vertex SFT candidate workflow that
cannot consume knowledge, Golden or unapproved records and cannot self-promote.

## Constraints

- Fine-tuning never carries factual VinFast knowledge, prices, promotions,
  policy, freshness or authorization.
- Golden/evaluation records are permanently excluded from training.
- Submission is a separate human-authorized command; export never submits.
- Preference, embedding tuning, RFT, continuous and audio tuning remain closed
  until separate evidence opens them.

## Done when

- A released SFT dataset with at least 500 human-reviewed, family-isolated
  examples can be exported with immutable train/validation/test manifests.
- The job registry enforces one job, USD 20 cap and two attempts per cause.
- Tuned candidates run the full held-out suite and cannot promote on metric,
  latency, cost or hard-gate regression.
- Rollback, kill switch, retention and deletion lineage are proven.

## Checkpoint

- Proposed and human-blocked on VFBIZ-0196, VFBIZ-0201 and VFBIZ-0139.
- Exact next action: remain proposed; do not export or submit training.

## Evidence

- [ ] No dataset export, tuning job or provider spend is authorized while this
  item remains proposed and human-blocked.
