---
id: VFBIZ-0198
title: Add local-first VinFast document intake and PDF OCR
status: review
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai/app/modules/datasets
  - backend/ai/app/modules/knowledge
  - backend/ai/ops/local-pdf-worker
  - backend/ai/scripts
  - backend/ai/tests
  - backend/ai/dataset-specs/catalog/sources
  - contracts/ai/datasets/sources
  - contracts/ai/index.json
  - contracts/ai/test-vectors/dataset-contracts.json
  - tools/check-runtime-contracts.mjs
  - tools/check-agent-governance.mjs
  - docs/work/items/VFBIZ-0198.md
  - WORK.md
  - local-data/ai-datasets
depends_on:
  - VFBIZ-0136
controlled_signals:
  - ai-dataset
  - dataset-source
  - knowledge-ingestion
  - public-contract
exclusive_resources:
  - ai-dataset-registry
  - ai-source-intake-contract
required_checks:
  - npm run contracts:lint
  - npm run verify:ai
  - npm run verify:ai:integration
  - npm run governance:check
revision: 2
review_date: "2026-08-30"
updated_at: "2026-07-30T13:54:16+07:00"
---

# Outcome

Import the user-supplied VinFast customer-document corpus into immutable local
quarantine and produce a developer-only, citation-preserving PDF/OCR knowledge
candidate through a format- and origin-aware intake contract.

## Constraints

- Local bootstrap, managed upload and external HTTPS are distinct origins;
  storage location is not provenance.
- Local processing never creates Content, Legal, Data or Release approval.
- The candidate is developer-only, release-ineligible and unreachable from the
  active/public retriever.
- VinFast binaries, extracted text, chunks and vectors remain outside Git.
- The corpus is knowledge-only and cannot enter Golden, evaluation, red-team or
  training/fine-tuning products.

## Done when

- The two explicitly rejected extensionless PDFs are recoverably moved to
  Trash and exactly 79 PDFs remain in the source landing tree.
- All retained PDFs are copied atomically into content-addressed local
  quarantine with hash parity, private permissions and an immutable batch
  receipt.
- Contracts distinguish external HTTPS, managed upload and local bootstrap;
  content SHA-256 is the immutable revision.
- The bounded PDF pipeline performs structure/malware checks, native extraction,
  per-page OCR fallback, hostile-content scan, citation-preserving chunking and
  deterministic test embedding.
- Every page has an observed terminal disposition and the local candidate is
  explicitly release-ineligible.
- Focused, contract, AI integration and governance checks pass.

## Checkpoint

- User authorized the approved plan for local development processing on
  2026-07-30. This is processing scope, not production release authority.
- The immutable batch has 79 distinct receipts and 79 distinct
  content-addressed PDF objects with post-copy SHA-256 parity. The completed
  report records 78 processed documents and one safely rejected document whose
  PDF contained an active or embedded object.
- The processed corpus contains 3,800 pages: 2,003 native-text pages, 1,325 OCR
  pages, 472 `review-required` pages, zero rejected pages inside accepted
  documents and 10,805 deterministic local test chunks under pipeline digest
  `aa09281aecdd0ce5b024daa906de2fb94d855dc051f0325e4fded571979d3588`.
  Every review/rejected page has zero chunks; every emitted chunk carries
  source hash, content revision, receipt/path lineage, page citation,
  developer-only ACL and inactive/release-ineligible flags.
- The two extensionless files are recoverably in macOS Trash and the landing
  tree contains exactly 79 retained PDFs. Source binaries and derived
  artifacts remain outside Git.
- Exact source URLs are optional for local bootstrap/managed upload. Production
  release remains human-blocked on Content/Legal/Data evidence under
  VFBIZ-0136. Public Chat API and active retriever remain disabled for this
  candidate.
- Re-running the same import completed from validated checkpoints without
  creating another object, receipt, job or pipeline candidate. Obsolete local
  pipeline digests were moved recoverably to
  `/Users/anhtuan/.Trash/VFBiz-vinfast-obsolete-pipelines-20260730`; quarantine
  originals were retained.
- GCP development foundation is provisioned in project `vinfast-503003`,
  region `asia-southeast1`: private versioned buckets
  `vinfast-503003-intake-dev`, `vinfast-503003-derived-dev` and
  `vinfast-503003-evidence-dev`; Pub/Sub topic
  `vinfast-document-intake-dev` with subscription
  `vinfast-document-worker-dev`; least-privilege development worker identity
  `vfbiz-ai-dev-worker@vinfast-503003.iam.gserviceaccount.com`; and enabled
  Document AI OCR processor
  `projects/81588547131/locations/asia-southeast1/processors/4d2384d940a52fa5`.
  No source files were uploaded and no public IAM bindings exist.
- A 4,000,000 VND monthly development budget alert was created with 50%, 75%,
  90% and 100% thresholds. It is an alert, not a hard spend cutoff; application
  quotas and worker budgets remain required.
- VFBIZ-0198 is code-complete and moved to review; this does not grant
  production release authority. Exact next action: a human Knowledge/Data
  reviewer inspects the one rejected document and the 472-page manual-review
  queue, then records Content/Legal/Data evidence or requests bounded fixes.
  VFBIZ-0199 owns the separate GCS/Pub/Sub/Document AI adapter. Do not activate
  production retrieval or use this corpus for Golden/evaluation/training.

## Evidence

- [x] Focused unit/security/tamper/tombstone tests — observed green.
- [x] Full corpus validation — 79 receipts/objects and hash parity; 78 processed,
  one safely rejected; all 10,805 chunks have revision/page/ACL lineage and are
  inactive/release-ineligible.
- [x] Idempotent rerun — observed the same 79 objects, receipts, terminal
  records and pipeline digest without reprocessing completed artifacts.
- [x] `npm run contracts:lint` — observed green (35 contracts, 61 vectors).
- [x] `npm run verify:ai` — observed green (577 passed, 93 skipped; Alembic
  SQL generation completed through `20260730_0020`).
- [x] `npm run verify:ai:integration` — observed green against an isolated,
  ephemeral PostgreSQL 17 + pgvector database; the container was removed after
  the run.
- [x] `npm run governance:check` — observed green.
- [x] Final VFBIZ-0198-focused lint, pyright and 20
  unit/contract/security tests — observed green after the active-object
  document-rejection continuation fix.
- [ ] A later repository-wide rerun is temporarily red on in-progress,
  disjoint VFBIZ-0199/VFBIZ-0200 files (GCP adapter/voice type errors and two
  incomplete skill manifests). This does not reopen a VFBIZ-0198 finding; rerun
  the shared gate after those active writer lanes finish.
