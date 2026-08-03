---
id: VFBIZ-0213
title: Build the governed ViVi synthetic behavior tuning successor
status: blocked
mode: controlled
priority: P0
owner_team: ai-model-platform
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai/app/modules/datasets/application/curation
  - backend/ai/app/modules/datasets/infrastructure/synthetic_tuning_candidate_store.py
  - backend/ai/tests/unit/datasets
  - local-data/ai-datasets/candidate/tuning/vivi-behavior-synthetic-v3
  - local-data/ai-datasets/review-evidence/vertex-tuning-successor
  - docs/work/items/VFBIZ-0213.md
  - WORK.md
depends_on:
  - VFBIZ-0212
controlled_signals:
  - ai-dataset
  - ai-evaluation
  - fine-tuning
  - pii
exclusive_resources:
  - ai-dataset-registry
  - vivi-behavior-synthetic-v3
required_checks:
  - npm run contracts:lint
  - npm run verify:ai
  - npm run governance:check
revision: 2
review_date: "2026-08-31"
updated_at: "2026-07-31T16:00:00+07:00"
---

# Outcome

Create a new immutable synthetic ViVi behavior candidate that corrects the
rejected v2 lineage, label, split-isolation and diversity defects, then produce
an exact no-upload/provider preflight decision.

## Constraints

- V2 remains immutable rejected evidence and is never edited or reclassified.
- Records contain no VinFast facts, PDF content, customer conversations,
  production PII, prices, policy, authorization or freshness claims.
- Family partitioning and component allocation happen before rendering.
- Golden, test and security-held-out records are never exported for training.
- Every record and manifest is content-addressed and independently
  recomputable.
- All eligibility and provider/upload flags remain false until deterministic
  gates and independent recommendations pass.
- Baseline or tuning dispatch additionally requires an external immutable GCS
  witness before credential acquisition; a local ledger is insufficient.
- Development authorization does not represent Product, Brand, Legal, Privacy,
  Data acceptance or Release approval.

## Done when

- At least 600 byte-reproducible records have per-record governed lineage,
  immutable family lock and split manifests.
- Held-out response constraints, including the four former 15-word failures,
  validate with zero errors.
- Exact, normalized, semantic, family and component leakage are zero.
- Response composition uniqueness is at least 95% per split and maximum
  normalized template share is at most 1%.
- PII, secret, prompt-injection and unsupported-brand-fact scans are zero.
- Independent dataset-quality and risk reviewers return recommendation-only
  dispositions against exact digests.
- A sealed packet records whether baseline upload/provider dispatch is allowed;
  no tuning job is submitted by the dataset builder.

## Checkpoint

- VFBIZ-0212 v2 is immutable and rejected. Its 17 governed files still match
  `SHA256SUMS`; it has 600 records but lacks per-record lineage, contains four
  held-out references over their 15-word limit and concentrates 400 train
  responses into only 25 templates.
- The user authorized a separate development successor cycle. This authorizes
  synthetic generation and local verification only; it does not counterfeit
  accountable organizational approval or provider submission authority.
- V3 was sealed at manifest
  `3cde0a4af8ea7cdf477404547c0f17262fa36264795e10462a65dab61b489550`.
  Its deterministic and security gates pass, but the independent dataset
  reviewer rejected it for tuning: prompts expose synthetic IDs, several
  response families are robotic or not scenario-grounded, authority metadata
  can be self-resigned after tampering, and the four v2 regressions are not
  explicitly mapped.
- V3 is immutable rejected evidence. It must not be uploaded or tuned.
- Exact next action: VFBIZ-0214 builds a separate v4 correction candidate.

## Evidence

- [x] Deterministic generator and byte-identical rerun
- [x] Per-record lineage, family lock and split-isolation verification
- [x] Constraint, diversity, PII/secret/injection/fact scans
- [x] Independent dataset-quality and risk recommendations
- [x] Exact no-upload or dispatch preflight packet
- [ ] Dataset-quality acceptance (blocked; successor VFBIZ-0214)
