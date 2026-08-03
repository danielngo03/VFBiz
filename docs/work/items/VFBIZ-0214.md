---
id: VFBIZ-0214
title: Correct synthetic ViVi tuning quality and authority
status: blocked
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - .agents/organization.json
  - backend/ai/app/modules/datasets/application/curation
  - backend/ai/app/modules/datasets/infrastructure/synthetic_tuning_candidate_store.py
  - backend/ai/dataset-specs/qualification/behavior-sft/v5
  - backend/ai/tests/unit/datasets
  - local-data/ai-datasets/candidate/tuning/vivi-behavior-synthetic-v4
  - local-data/ai-datasets/candidate/tuning/vivi-behavior-synthetic-v5
  - local-data/ai-datasets/candidate/tuning/rejected/vivi-behavior-synthetic-v4-*
  - local-data/ai-datasets/review-evidence/vertex-tuning-successor
  - docs/work/items/VFBIZ-0213.md
  - docs/work/items/VFBIZ-0214.md
  - WORK.md
depends_on:
  - VFBIZ-0213
controlled_signals:
  - ai-dataset
  - ai-evaluation
  - fine-tuning
  - pii
exclusive_resources:
  - agent-organization-registry
  - ai-source-registry
  - ai-dataset-registry
  - vivi-behavior-synthetic-v4
  - vivi-behavior-synthetic-v5
required_checks:
  - npm run contracts:lint
  - npm run verify:ai
  - npm run governance:check
revision: 15
review_date: "2026-08-31"
updated_at: "2026-08-02T03:56:00+07:00"
---

# Outcome

Build an immutable v4 candidate that closes every independent dataset-quality
finding on rejected v3 without weakening provider, release or human authority.

## Constraints

- V2 and v3 are immutable rejected evidence.
- Provider exports contain natural Vietnamese only: no record, family,
  scenario or variant identifiers.
- Every assistant response is grounded in the synthetic scenario request.
- The verifier enforces exact source class, labels, behavior-family coherence,
  seed identity, scenario identity and locked digests.
- A regression manifest maps and proves the four exact v2 word-limit failures.
- All eligibility/provider/upload flags remain false. No upload or Vertex call
  occurs in this dataset-builder lane.

## Done when

- At least 600 deterministic records pass schema, language, lineage, leakage,
  diversity, constraint and safety gates.
- A stratified language-quality review finds no P0/P1 issue.
- Tampering with source, labels, scenario or seed authority fails even after
  recomputing outer hashes.
- Independent dataset-quality and risk reviews bind exact digests.

## Checkpoint

- V3 manifest `3cde0a4af8ea7cdf477404547c0f17262fa36264795e10462a65dab61b489550`
  is rejected for tuning and remains unchanged.
- V4 contains 625 fact-free records with the locked 400/100/125 split. The
  verifier recomputes trusted source, authority, family/scenario, export and
  record digests instead of accepting candidate-issued authority.
- Four superseded V4 candidates are preserved read-only under `rejected/`.
  Their findings were used to bind the official rubric/domain-pack semantic
  digests, remove English implementation terms, correct the fourth V2 word
  count and replace awkward synthetic response constructions.
- The former stable successor is read-only and binds manifest
  `f442d29c6a0293d4d81897bfed9e22e4a60bbcf994b444078a33ff0c5617431f`,
  checksum file
  `eebf4eeedc8d81bbd2e3e49121ef0cd910307eb4e227281c8e54c566f22c6d14`
  and external authority
  `a9fb92d3075bb047083598b6939cc0631af8fe0738ae381cf45f8d1884812cce`.
- Independent risk review reproduced those exact digests and found no P0/P1
  authority, provenance, export or eligibility regression. It recommends
  local independent language/data review only; it grants no approval.
- Independent dataset-quality review rejected that exact candidate: the
  component-ID structural metric was ineffective, ten five-token response
  prefixes each reached 30/625, and semantic/template repetition crossed split
  boundaries. V4 remains immutable and ineligible; it must not be uploaded.
- A text-derived quality gate now measures rendered prefixes, cross-split
  response similarity and forbidden implementation terms without emitting raw
  content or candidate-controlled identifiers. It rejects V4 with prefix shares
  of 4–5%, five cross-split near-duplicate pairs and five implementation-term
  hits.
- The materializer now invokes that gate before atomic publication. External
  authority digest
  `474b4f84c1d35f20b773beeef8a5cfbde2d9b4f03005cbed3d8e6ce571bb62b3`
  pins the verifier, store and text-quality implementation sources, so a
  candidate cannot bypass the gate by rebuilding its manifest and checksums.
- Independent follow-up review found and then closed fingerprint
  `6bbb47060160f994f0aa05530ec2d3f813439ce8f94c6272b37fb24c98936c2c`.
  The former trigram-Jaccard heuristic is replaced by safe length and
  character-multiset upper bounds; a unique-prefix-padding probe now reports
  892 cross-split near duplicates instead of passing.
- V4 remains immutable, rejected and ineligible. Exact next action: design and
  render a replacement V5 candidate against this mandatory gate, then obtain
  accountable Vietnamese-language/data adjudication. No eligibility, upload
  or provider flag may change.
- The V5 design is manifest-driven: generic version-neutral composer/verifier
  code; versioned schema, policy, family lock, literal source-pack and external
  authority under `dataset-specs/qualification/behavior-sft`. V5 is exactly 25
  locked families × 25 literal Vietnamese pairs with 16/4/5 family isolation
  and 400/100/125 records. V1–V4 remain immutable compatibility evidence; no
  new version-named Python generator or authority module is allowed.
- Coordination
  `coord-1fb8ec93-fa93-426e-9ef9-94c91f238f4a` assigns governed V5
  schema/policy/manifest/authority artifacts to Data Governance. While that
  non-blocking lane is open, AI Knowledge Engineering has implemented only the
  version-neutral qualification loader. It verifies exact external manifest
  and input digests, source-digest bindings, 625/25 allocation, 400/100/125
  record splits, 16/4/5 family splits, the five-behavior family matrix and
  false-only eligibility flags. It cannot render, upload or dispatch V5.
- Independent loader review closed three findings after a bounded fix cycle:
  caller-pinned authority digest plus observed input/source digests defeat a
  coherent full-resign; returned digest maps are immutable; schema and all
  flat/nested counts reject booleans instead of relying on Python equality.
- Data Governance phase one now provides the V5 schema, policy, family lock and
  scenario lock as candidate-only governed specifications. Their exact SHA-256
  digests are respectively
  `b0c5b8f47ff1a52669f177d5b99153cd456346ecfba514c4c1d267c6df31348e`,
  `73655211c61396c00d657bbcfa3dce5d9a49c95c931a9ff239f78c5518253b93`,
  `2d062bc20e1bb5dd8650924ae833ee58eda70bad6e8a4392101dfe0ba8065643`
  and
  `77a47c1ab8c55f328883a9b348bbfc9a0253e272e2dd7f9fdd97c5a01a8e5418`.
  The locks expand deterministically to 625 unique scenarios across 25
  conversation families, five registers and five states with the exact
  400/100/125 record and 16/4/5 family splits.
- The literal source pack, final manifest and external authority are
  intentionally absent. The generic loader therefore remains fail-closed and
  no candidate can be materialized, uploaded, dispatched, tuned or released.
  Exact next action: author the content-addressed literal Vietnamese source
  pack outside Git, independently review its fact-free language and split
  isolation, then bind observed digests into the manifest and authority last.
- Coordination `coord-1fb8ec93-fa93-426e-9ef9-94c91f238f4a` is closed after
  the governed phase-one handoff. Ownership has returned to AI Knowledge
  Engineering for the isolated content-addressed source-pack lane; Data
  Governance retains authority over the final manifest and authority binding.
- The agent control plane previously had no shared-path classification for
  `local-data/ai-datasets`, so an otherwise declared V5 writer could not acquire
  a scoped claim. The path is now governed as `ai-dataset-registry`; the
  organization registry itself is declared as an exclusive resource for this
  correction.
- The first complete V5 literal pack, SHA-256
  `a9dbd1914155cdfa6e4c604e5c65a5bf4ed4e1f000e54ad8972a77e24a1aea3b`,
  has exact 625/25 allocation, zero configured assistant-side near duplicates,
  no PII, secret, prompt injection, VinFast fact, concrete price/specification,
  tool JSON or eligibility mutation. It is nevertheless rejected and must be
  archived: independent review found 328 cross-split pairs caused by two
  repeated user-message groups, and all 625 assistant targets describe how to
  respond rather than directly performing the behavior.
- The final bounded fix cycle for this cause ran under claim
  `claim-8de4290e-afbd-401e-8b6f-e4047da28240`, targeting self-contained
  prompts, direct natural Vietnamese responses, message-level cross-split
  isolation and body-template concentration checks.
- The final bounded fix cycle ended fail-closed without publishing a
  replacement. Its in-memory candidate reached 625 unique normalized prompts
  and 625 unique normalized responses, but the pre-write response-economy gate
  rejected `v5-next-step-summary--neutral--interrupted-request` for exceeding
  30 words. Claim and all five leases were released with no partial artifact.
- VFBIZ-0214 is blocked at accountable language/data authoring. The rejected
  `a9db...` pack remains immutable under
  `rejected/a9dbd1914155cdfa6e4c604e5c65a5bf4ed4e1f000e54ad8972a77e24a1aea3b/`;
  no accepted source pack, manifest or authority exists. Automated regeneration
  for the same cause must not be retried.

## Evidence

- [x] Focused verifier tests — 13 passed, including coherent full-resign,
  provider-export divergence and atomic/idempotent materialization.
- [x] Focused Ruff and Pyright — passed with zero errors.
- [x] V4 deterministic assessment — 625 records; train 400, validation 100,
  held-out 125; rejected for 4–5% prefix concentration, five cross-split
  near-duplicate pairs and five implementation-term hits.
- [x] `npm run contracts:lint` — 38 contracts and 67 dataset vectors passed on
  2026-08-02.
- [x] `npm run verify:ai` — Ruff, Pyright, 910 tests and Alembic offline replay
  through `0025` passed; 112 external-profile tests were explicitly skipped;
  one existing TestClient/httpx deprecation warning remains.
- [x] `npm run governance:check` — work, docs, authorization, dependency and
  provider-neutral agent-governance checks passed.
- [x] Independent risk review — technical pass bound to the stable manifest,
  checksum and authority digests; upload/training/release remain forbidden.
- [x] Independent dataset-quality review — rejected manifest
  `f442d29c6a0293d4d81897bfed9e22e4a60bbcf994b444078a33ff0c5617431f`
  with two P1 quality findings and one P2 evidence finding.
- [x] Mandatory text-derived gate — 21 focused tests passed in 8.66 seconds;
  Ruff and Pyright passed; failed verification leaves no published directory.
- [x] Independent follow-up review — external authority binding and mandatory
  materialization have no finding; unique-prefix-padding P1 is closed after the
  exact 100-record probe changed from accepted to 892 detected pairs.
- [x] Generic V5 qualification-loader foundation — 11 focused tests, Ruff and
  Pyright passed; coherent full-resign, observed artifact divergence,
  eligibility mutation, family-split relabeling, post-validation mutation and
  boolean count substitution fail closed.
- [x] Independent loader review cycle two — fingerprints
  `519c70fa2f306fc6072cb98646aa90bc079fb0e3c6bc215f23dc2eb45b1a4722`,
  `148b399f2d0fedfa83f342be1a462c70dcb245c093ca2c07883fc7cba96826f4`
  and
  `7ff5bac608338771e60e6c3b84978028457c0577d388262cf59bda9845c53468`
  are technically closed without granting dataset or release approval.
- [x] Data Governance coordination response — candidate-only work may proceed
  strictly under `dataset-specs/qualification/behavior-sft/v5` after acquiring
  `ai-source-registry` and `ai-dataset-registry`; response explicitly grants no
  approval, adjudication, upload, tuning or release authority.
- [x] Current phase ownership transferred to `data-governance` for the isolated
  governed-artifact lane. Ownership returns through a recorded handoff before
  any later curation/runtime integration; one path retains one writer.
- [x] Data Governance phase-one artifacts — Draft 2020-12 schema compiled;
  exact 25-family allocation and 625-scenario expansion reproduced; all
  authority and eligibility flags remain false; no V4 digest was inherited.
- [x] Independent Data Governance review cycle two — gates
  `VFBIZ0214-DG-PHASE1-SCHEMA-001` through
  `VFBIZ0214-DG-PHASE1-INCOMPLETE-006` passed. The missing literal source pack,
  manifest and authority are an expected fail-closed state, not acceptance.
- [x] Phase-one claim and the `ai-source-registry`, `ai-dataset-registry` and
  `vivi-behavior-synthetic-v4` leases were released with fencing token 377
  after recording exact artifact digests and review gates.
- [x] Data Governance handoff closed and work-item ownership returned to
  `ai-knowledge-engineering`; the exact V5 local candidate path and exclusive
  resource are now declared before any source-pack write.
- [x] Local dataset storage is mapped to the `ai-dataset-registry` shared
  resource so claims enforce one writer without granting the owning team broad
  root-path access.
- [x] Candidate-only V5 literal pack produced locally — exact SHA-256
  `a9dbd1914155cdfa6e4c604e5c65a5bf4ed4e1f000e54ad8972a77e24a1aea3b`;
  625 records; receipt `faa4eaaf29281e7261c310ddf742257cefedcf87eb99b6c1d9eb1cd37d958965`;
  report `baeda44083d3d4050688a4b401cafabcb19565acb032fcfa58d74e47456b8855`;
  all files mode `0600`, directory mode `0700`, checksums reproduced.
- [x] Independent dataset-quality review rejected the exact pack with P1
  fingerprints
  `8d2cde9d623ac37fe3999a9bf7ca27a51fe50aa9a7a38d4479c705ca7941a5de`
  (message-level cross-split leakage) and
  `ad13ed6a2a0581588c96a72f27a606d4884f491a0ce7a792b374da1c427e91fa`
  (formulaic meta-instructions), plus P2 fingerprint
  `78549796fb70ea8afe9338674eed3e481898a6dc2c90e0403fa5592669f1b436`
  (receipt check-scope mismatch).
- [x] Independent domain review rejected the same pack with P1 fingerprints
  `f65a4cc07ced3ecd6bc7f173ef0dbd193cd889aba2de59bc6f3ebf00fd314561`
  (all five behaviors are described rather than performed) and
  `bbf5b1d38c57319042a8bd1a2e2a0cd82a57f9a48758776376b706dcfde66f9a`
  (50 terse prompts expose no family intent). Both reviews are recommendation
  only and grant no adjudication or approval.
- [x] Final bounded replacement stopped before write: structural isolation
  reached 625 unique prompts and responses, but a concise-family response
  violated the 30-word guard. No partial pack or misleading report exists.
- [x] Rejected V5 evidence archived read-only — original object digest
  `a9dbd1914155cdfa6e4c604e5c65a5bf4ed4e1f000e54ad8972a77e24a1aea3b`;
  rejection-findings digest
  `edf01ea110b4f02cf6a25197733ed6390f673112b76b56acd43a259cde69a9ad`;
  files mode `0400`, directory mode `0500`.
- [ ] No accepted content-addressed literal source pack, final manifest or
  external authority exists. Rejected source packs cannot be materialized from
  candidate-issued metadata or used by any provider.
- [x] `contracts:lint` and `governance:check` passed before phase-one artifact
  creation; they must be rerun against revision 11.
- [ ] Accountable human language/data review and adjudication are absent.

## Blocker

The two permitted review/fix cycles for this cause are exhausted. A Vietnamese
language/data owner must author or adjudicate direct customer-facing targets
against the locked families and policy. Until an independently accepted pack
exists, manifest/authority binding, export, upload, provider dispatch and tuning
remain fail-closed. This blocker does not authorize fabricated approval and
does not prevent unrelated runtime/evidence work items from continuing.
