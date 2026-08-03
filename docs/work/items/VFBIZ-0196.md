---
id: VFBIZ-0196
title: Adjudicate the 1,000-case ViVi Golden staging suite
status: active
mode: controlled
priority: P0
owner_team: ai-assurance
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai/dataset-specs/evaluation
  - backend/ai/app/modules/datasets
  - backend/ai/app/modules/evaluation
  - backend/ai/tests
  - local-data/ai-datasets/candidate/evaluation/customer-assistant-golden-v1
  - local-data/ai-datasets/candidate/red-team/customer-assistant-adversarial-v1
  - local-data/ai-datasets/review-evidence/VFBIZ-0196
  - docs/work/items/VFBIZ-0196.md
  - WORK.md
depends_on:
  - VFBIZ-0135
  - VFBIZ-0162
  - VFBIZ-0192
controlled_signals:
  - ai-evaluation
  - human-adjudication
  - dataset-release
exclusive_resources:
  - ai-evaluation-suite-registry
  - ai-dataset-registry
required_checks:
  - npm run verify:ai
  - npm run contracts:lint
  - npm run governance:check
revision: 15
review_date: "2026-08-29"
updated_at: "2026-08-03T22:12:00+07:00"
---

# Outcome

Create the 1,000-case ViVi Golden staging suite with immutable split locks,
independent technical recommendations and genuine human adjudication evidence.

## Constraints

- The 100 generated smoke cases are runner-development candidates, not Golden
  acceptance evidence.
- Agents prepare digest-bound review packets; only named human SME, Data and
  Release authorities can adjudicate or approve.
- Golden cases are permanently excluded from training, synthetic seeds and the
  knowledge index.

## Done when

- All 1,000 cases have schema-valid ground truth, rubric revision, split-family
  lock, provenance digest and human adjudication evidence.
- Author, generator, technical reviewer and human adjudicator independence is
  enforced at the registry boundary.
- The Evaluation executor can reproduce the suite and bind every result to its
  immutable suite digest.
- Contamination, duplication, broken-case and leakage reports have no unresolved
  hard-gate finding.

## Checkpoint

- Candidate generation is active under the locked 1,000-case taxonomy. Every
  generated case remains `human_adjudicated=false`, training-excluded and
  release-ineligible.
- VFBIZ-0192 is technically code-complete for public-diagnostic evidence but
  real VinFast acceptance authority remains fail-closed. Candidate generation
  does not consume or imply that authority.
- The active candidate is content-addressed by bundle digest
  `7189b908c558ef60c8b7c8a418a0d97803d7c60ff52facb228ade2e8d4c2e020`
  and generator-source digest
  `94e00138c806bf12dae088900619dbfd04d04eb9864de8b98f3ef0a8ce68f0cc`.
  It contains exactly 1,000 cases and 100 held-out candidate families with the
  locked 240/160/160/160/120/100/60 distribution.
- Two independent-review fix cycles rejected and archived three superseded
  packets. The active packet has zero exact/accent-insensitive input conflict,
  zero cross-family token-Jaccard pair at or above 0.85, maximum five-token
  prefix share 1% and maximum scenario-template share 0.1%.
- Scenario depth now includes 16 distinct ambiguity slot sets and three-turn
  contexts, four routing outcomes/five routing decisions, 12 distinct typed
  resilience state/delta/forbidden contracts, and 70 typed tool cases covering
  three allow and four deny tool families.
- The packet snapshots the exact generator source plus suite, Golden rubric,
  ViVi rubric/domain/board/calibration/held-out authority bytes. The verifier
  rebuilds expected cases/family lock and rejects coherent label, rubric,
  lineage, family and authority full-resign attacks.
- Filesystem materialization lives in dataset infrastructure, is atomic and
  content-addressed, and writes directories `0700` and files `0600`. Raw
  candidate data remains under `local-data`, outside Git.
- Independent final review closed
  `VFBIZ-0196-R2-GOLDEN-SCENARIO-DEPTH-001` with no scoped P0/P1. This is a
  technical recommendation only. Global fingerprint registry comparison and
  named-human adjudication remain pending; adjudicated count is still 0/1,000.
- The governed contamination builder independently rehashed and parsed the
  exact Golden packet plus 17 current canonical training JSONLs. Report
  `d793dc9f037f8575ea6b5d2bcfafc6cd8c72dc1c670a12bc28aa0003160af6e0`
  observed 1,320 Golden conversation surfaces and 8,080 training message
  surfaces with zero exact or accent-insensitive token-Jaccard overlap at
  threshold 0.85. That historical report was explicitly `incomplete` because
  knowledge and red-team data products were absent; the lexical method makes
  no semantic-equivalence claim.
- Independent re-review closed forged-report persistence finding
  `VFBIZ-0196-R2-GLOBAL-CONTAMINATION-STORE-DIGEST-002`. Finding
  `VFBIZ-0196-R2-GLOBAL-CONTAMINATION-BINDING-001` remains P1 after the second
  review/fix cycle: the 17-file input inventory is still caller-declared rather
  than resolved from a content-addressed Data Governance registry. The current
  incomplete report is reproducible diagnostic evidence, but cannot become a
  global `passed` authority until that external inventory manifest is bound.
- Data Governance inventory candidate
  `global-contamination-source-inventory-v1` now pins byte digest
  `131af17ba9d637a6637f80fb8f0c1798e77bf74bba3521c99cc7f67590daded4`
  and semantic digest
  `edbec46564dfb6386325d7e450ae55e2b996f006fdee717b2bc3ab26ea1d7757`.
  The authority entrypoint no longer accepts a caller-provided source tuple:
  it resolves the exact Golden file and every canonical training JSONL from
  locked roots/globs, rejects inventory tamper, aliases and symlinks, and binds
  the inventory digests into the report.
- Independent closure review reproduced P1
  `VFBIZ-0196-R3-GLOBAL-CONTAMINATION-AUTHORITY-BYPASS-001`: the raw projector
  and digest-only store could still accept a caller-raised threshold and
  zero-surface product evidence. Revision 6 removes the raw projector from the
  public facade, rejects zero-surface evidence, locks threshold 0.85 in the
  governed builder and makes the store rebuild the complete report from the
  pinned inventory before writing it.
- Replacement report
  `7f682ad7e1ca1386ff78dff9a0b5d812f5cb28d805cbb9c77ce528d810ac00af`
  binds authority class `inventory-governed-v1` and reproduces the current
  1,320-by-8,080 zero-overlap result. At that checkpoint it remained
  `incomplete` because governed knowledge and red-team products did not yet
  exist. The bounded two-cycle review budget is exhausted, so this remediation
  remains pending a later independent acceptance rather than being self-closed.
- Revision 7 opens one disjoint synthetic red-team builder lane. Its output is
  fact-free, restricted, family-locked and permanently excluded from training,
  knowledge, provider upload and release; it cannot satisfy the still-missing
  governed knowledge product.
- The resulting restricted packet is content-addressed by digest
  `4822afbe2e509e7081f0fd0405ef369a8240f3c4e52d37728a32f8957c576497`.
  It contains 200 fact-free Vietnamese adversarial cases in 40 locked families
  and eight attack classes (25 cases each), with zero normalized duplicate,
  zero cross-family token-Jaccard pair at or above 0.85 and zero forbidden
  content match. All adjudication, training, upload, release and knowledge
  eligibility flags remain false; the packet is stored `0700/0600`.
- Governed contamination report
  `87a478cc26591685460acb62800a68a4d80ece79f1e188fea6c8a95ec57d8e3a`
  now observes 1,320 Golden surfaces against 8,080 training and 200 red-team
  surfaces with zero exact/lexical overlap. Status remains correctly
  `incomplete`, now only because governed knowledge is absent.
- The requested independent dataset-quality review could not execute because
  the review provider reported its usage limit. This is an unavailable review,
  not acceptance; technical checks do not replace the pending independent
  recommendation.
- A restricted synthetic knowledge packet now supplies 12 fact-free,
  page-anchored surfaces under exact bundle digest
  `50026ed91aa6dfce5b1fa8bebe8aef80e351da3ea151e0892295c8fc6aa595d1`.
  Governed report
  `25c05bbc13d27821edbd6a1cf8684d0823bee8a87603d8d9edd0830355873622`
  observes all three required products: 1,320 Golden surfaces against 8,080
  training, 200 red-team and 12 synthetic knowledge surfaces. It reports zero
  exact and zero lexical overlap and technical status `passed`. This remains a
  lexical, synthetic-only check and creates no semantic, data-rights, human or
  release authority.
- Exact next action: obtain the pending independent red-team/knowledge and
  contamination recommendation, then hand the exact active candidate digest
  to named human SMEs. No eligibility, upload, release or provider flag may
  change before those evidence and authority gates close.
- Revision-11 local dataset inspection reran after fixing nested Hugging Face
  transport-cache handling. The content-free manifest has 57 artifacts,
  4,376,809 records and 2,227,143,867 bytes; candidate pass count is zero.
  All 57 require a production malware scan, 25 additionally require PII review
  and one contains a secret finding. Manifest digest is
  `bdb73a3bd7b7198cbe9b649910d58a902c2436bb44a10239533c08528c2b4436`.
  These downloaded public-source artifacts remain quarantine-only and are not
  used for Golden, training, knowledge release or provider upload.
- Revision-12 full AI verification passes 951 tests, 112 conditional skips and
  one existing Starlette/httpx warning; Ruff, Pyright and Alembic offline
  replay remain green. The nested-cache scanner regression is included in this
  result and did not alter any candidate eligibility or authority flags.
- Revision-13 re-generated the same quarantine inspection after removing an
  absolute local path from the manifest. It remains 57 artifacts, 4,376,809
  records, 2,227,143,867 bytes and zero candidate-pass; the portable manifest
  digest is now `70ab9a013f8fa06cc96d8fe839aeba06b486c273c4d332ee29f83ed13e0b53aa`.
  The report stores `download_root=local-downloads` and contains no workspace
  absolute path or raw record content.
- Revision-14 rerun of `verify:ai` passes 951 tests, 112 conditional skips and
  one existing Starlette/httpx warning after the portable-manifest fix.
- Revision-15 rerun after release-gated Vertex factory wiring passes 954 tests,
  112 conditional skips and the same known Starlette/httpx warning; no Golden
  flags, provider calls or human-adjudication state changed.

## Evidence

- [x] Candidate generator/verifier/store focused checks — Ruff and Pyright pass;
  12 focused Golden tests and the full dataset unit suite pass.
- [x] Independent dataset review — two bounded fix cycles closed input-label,
  rubric authority, generator reproducibility, semantic full-resign and
  scenario-depth findings. Final recheck observed 24 Golden/architecture tests,
  exact authority snapshots, schema validity, content hashes and filesystem
  permissions with no scoped P0/P1.
- [x] Candidate artifact integrity — `SHA256SUMS` verifies generator, authority
  snapshot, cases, family lock, fingerprint report and manifest for exact bundle
  `7189b908c558ef60c8b7c8a418a0d97803d7c60ff52facb228ade2e8d4c2e020`.
- [ ] Global contamination gate — the inventory-bound technical report now
  observes knowledge, red-team and training and returns `passed` with zero
  exact/lexical match. Semantic equivalence is not claimed. Independent
  acceptance of the source-authority remediation and current product packets
  is still required before this checkbox can close.
- [ ] Independent red-team dataset-quality review — provider usage limit
  prevented execution; no reviewer recommendation is recorded.
- [ ] Named human SME adjudication — 0/1,000; Product/Brand/Data/Release
  authority remains absent.
- [x] `npm run verify:ai` — 859 passed, 101 explicitly skipped; Ruff, Pyright
  and offline Alembic chain through `0023` pass against revision 10.
- [x] `npm run contracts:lint` — 38 AI contracts, 7 runtime schemas and 67
  dataset vectors pass against revision 4.
- [x] PostgreSQL integration — 215 tests pass on a fresh PostgreSQL 17 /
  pgvector database with the required asyncpg URL and zero unexpected skip.
- [x] `npm run governance:check` — 195 work items and 75 provider-neutral
  context scenarios pass against revision 6.
