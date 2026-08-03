---
id: VFBIZ-0212
title: Run an isolated synthetic Vertex evaluation and tuning rehearsal
status: blocked
mode: controlled
priority: P0
owner_team: ai-model-platform
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - infra
  - root
allowed_paths:
  - backend/ai/app/modules/datasets
  - backend/ai/app/modules/evaluation
  - backend/ai/app/infrastructure
  - backend/ai/scripts
  - backend/ai/tests
  - backend/ai/dataset-specs
  - local-data/ai-datasets/candidate/tuning
  - local-data/ai-datasets/review-evidence/vertex-tuning-rehearsal
  - infra/gcp
  - docs/work/items/VFBIZ-0212.md
  - WORK.md
depends_on:
  - VFBIZ-0209
controlled_signals:
  - ai-dataset
  - ai-provider
  - ai-evaluation
  - fine-tuning
  - ai-budget-policy
  - pii
exclusive_resources:
  - ai-provider-registry
  - ai-dataset-registry
  - ai-evaluation-suite-registry
required_checks:
  - npm run contracts:lint
  - npm run verify:ai
  - npm run governance:check
revision: 3
review_date: "2026-08-31"
updated_at: "2026-07-31T19:10:00+07:00"
---

# Outcome

Prove the development plumbing for labeled data, Vertex baseline evaluation and
optional supervised tuning using a new synthetic-only Vietnamese behavior
candidate, without using VinFast documents, customer conversations, Golden
cases or production release authority.

## Constraints

- The candidate teaches response structure, clarification, refusal and
  handoff only. It must not encode VinFast facts, prices, policies, vehicle
  specifications, authorization or freshness.
- All records are synthetic, developer-only and partitioned by conversation
  family before generation. Golden, held-out evaluation and training splits
  are mutually exclusive by exact and semantic fingerprints.
- Dataset generation, quality review and risk review are distinct lanes.
  Agent recommendations are not recorded as human Product, Brand, Legal,
  Privacy, Data or Release approval.
- No raw secret is written to `.env`, Git, logs or packets. Local `.env`
  contains only Secret Manager coordinates; runtime resolves credentials
  through ADC.
- Cloud artifacts are private, content-addressed, create-only and carry
  `training=false` until deterministic scans and independent reviews pass.
- A provider evaluation or tuning call requires a sealed preflight packet,
  one attempt, no retry, a USD 5 total rehearsal cap and explicit cancellation
  and deletion references.
- A provider-created tuning endpoint is temporary, isolated and has no product
  route. It must be included in post-evaluation deletion evidence; the model
  remains unregistered for product use and ineligible for public Chat.
  VFBIZ-0202 remains the production candidate authority and is not bypassed by
  this rehearsal.

## Done when

- At least 500 synthetic SFT examples have immutable train/validation/test
  manifests, family isolation, schema/PII/secret/prompt-injection scans and
  contamination evidence.
- An untouched synthetic evaluation split measures the untuned baseline and
  records repeated error families without claiming human adjudication.
- Independent dataset-quality and risk reviewers return recommendation-only
  findings on the exact digests.
- Only a technically eligible candidate is uploaded to a dedicated private
  development prefix with generation, CRC32C and SHA-256 verification.
- If the measured behavior gap and cost gate justify it, one bounded tuning
  job is submitted and evaluated; otherwise the packet records an exact
  no-submit decision.
- Full AI, contract and governance gates pass. Production corpus, retriever,
  anonymous Chat and release remain closed.

## Checkpoint

- Synthetic v1 was rejected for cross-split template leakage. Correction cycle
  1 produced immutable v2 manifest
  `3a9b8dd51d56acfa3cac42b99868295d2c5480323b4e213d6f0c10e7ee050260`
  with 600 records, 120 families, 400/100/100 split counts and no test SFT
  export. A separate 60-case security held-out suite has manifest
  `0a6bada0113852ee99f0fe76e2ba36c24cfbaa15948570e3d532e394ad67b92c`.
- The second and final independent review cycle rejected v2 for incomplete
  governed per-record lineage, four incorrect held-out reference labels,
  concentrated response templates and the absence of an accepted baseline.
- The local hard-cost ledger now derives reservations from pinned numeric
  prices and rejects tamper, deletion, single-file rollback, retry and more
  than one training dispatch. Risk review proved that restoring the valid
  ledger and colocated anchor together still reopens dispatch, so live
  baseline and tuning remain fail-closed until an external create-only witness
  is integrated before credential acquisition.
- No GCS upload, infrastructure apply, live baseline, tuning job, endpoint,
  product registration, public Chat activation or human approval claim was
  made. The immutable no-submit packet digest is
  `cf92b5f989b840c5ee5c3122c5d8da4d1bd282c402030639e7c8a675d4f57006`.
- Exact next action: do not mutate or silently reopen v2. A human Data Owner
  must authorize a separate successor candidate cycle that fixes lineage,
  held-out labels and diversity; that cycle must integrate an external
  immutable dispatch witness before any provider call.

## Evidence

- [x] Candidate and split manifests
- [x] Deterministic data-quality scans
- [x] Independent dataset-quality and risk recommendations
- [x] Immutable GCS upload receipt or exact no-upload packet
- [x] Baseline/evaluation and tuning/no-tuning decision packet
- [x] Required repository checks
