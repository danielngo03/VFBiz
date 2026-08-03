---
id: VFBIZ-0200
title: Establish ViVi text voice evaluation authority
status: review
mode: controlled
priority: P0
owner_team: ai-assurance
accountable_role: product-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai/app/modules/datasets
  - backend/ai/app/modules/evaluation
  - backend/ai/dataset-specs/evaluation
  - backend/ai/tests
  - local-data/ai-datasets/review-evidence/VFBIZ-0200
  - contracts/ai/datasets/evaluation
  - contracts/ai/index.json
  - contracts/ai/test-vectors/dataset-contracts.json
  - docs/work/plans/vivi-gcp-ai-platform.md
  - docs/work/items/VFBIZ-0200.md
  - WORK.md
depends_on:
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
revision: 5
review_date: "2026-08-30"
updated_at: "2026-08-03T00:18:00+07:00"
---

# Outcome

Create a digest-bound ViVi text voice v1 candidate and measurable evaluation
rubric without inventing VinFast Brand approval or adjudicated Golden evidence.

## Constraints

- Public ViVi pages are references, not training rights or Brand authority.
- Text voice is separate from ASR/TTS gender, accent and prosody.
- Style can never compensate for citation, ACL, PII, authorization or state
  hard-gate failure.
- Golden and calibration held-out cases remain evaluation-only.

## Done when

- Domain pack, rubric and board policy have immutable revisions and digests.
- Suite/case validation rejects unknown or mismatched voice artifacts.
- Rubric anchors Vietnamese register, response economy, recovery,
  task transparency and brand-safe naturalness on a 0–3 scale.
- Candidate thresholds require every dimension at least 2 and mean at least
  2.5 after hard gates pass.
- A 60-case calibration packet and 120-case held-out plan exist as
  human-blocked specifications, not fabricated cases.
- Independent Golden-domain and risk reviews record remaining human decisions.

## Checkpoint

- Golden candidate now contains 1,000 cases, but remains 0/1,000 adjudicated
  and has no Golden Release authority.
- ViVi text voice v1 candidate now has digest-bound rubric, domain pack, board
  policy, calibration plan and held-out plan.
- Runtime-side voice authority validates the exact suite bindings and rejects
  tampered or unknown voice revisions.
- `golden_smoke.py` now references `vivi-text-voice-v1`.
- Product/Design/VinFast Content authority is still missing; the candidate is
  not a Brand-approved policy and cannot release a public assistant.
- Independent Golden-domain review returned `needs-human-decision`. Risk review
  agrees the voice packet is review material only and cannot authorize release,
  data/training rights, Dataset Release, Golden adjudication or public assistant
  activation.
- Human routing for the pinned voice artifacts:
  - Product Owner + Design Lead: confirm tone, response economy and UX
    behaviour.
  - VinFast Content/Brand SME: confirm brand-safe wording and “ViVi” usage.
  - Legal Owner: confirm no hidden claims or unauthorized product promises.
  - Data/Privacy Owner: confirm the evaluation packet contains no PII or
    training leakage.
  - Release Owner: confirm the review packet, not the candidate, is what gets
    promoted into the next gate.
- The first materialized packet
  `6afec38749a8c4bc27a35d938a9ed7bdbdae1261005984efb6a16c2adb9d4460`
  is superseded review evidence after independent review found five P1 gaps.
  The corrected exact 60-case fact-free packet is materialized at bundle
  digest `4c39920634b2a2d3ca3c379dd7ed3e0d539a06d0ed0d18e9d72ced083626e7f9`.
  It contains 12 locked families with five cases each, remains
  `human-blocked`, evaluation-only and ineligible for Golden, training,
  release or public serving. Atomic materialization writes `0700/0600` and
  verifies canonical bytes before replay.
- Golden-isolation diagnostic
  `660c3bd9f6a1b6b3081d8692efa27e66c28650342a59e3872cc336fd33423a9c`
  labels the data product as `calibration`, compares 1,320 Golden conversation
  surfaces with 130 calibration surfaces and
  found zero exact or accent-insensitive token-Jaccard overlap at 0.85. It is
  lexical diagnostic evidence only and does not claim semantic equivalence.
- The fix packet pins trusted artifact byte digests, enforces all six named
  human roles, rejects permissive replay permissions and unbound files, and
  adds scoreable assistant candidates plus direct cases for ViVi identity,
  default address, emoji, humour and sales-language policy.
- Second/final independent Golden-domain review closed all five scoped P1
  findings with no new P0/P1. The recommendation remains
  `needs-human-decision`; human labels are 0/60 and no Product, Design,
  Brand/Content, Legal, Data/Privacy or Release decision is present.
- Exact next action: route the exact packet and pinned artifact digests to the
  named human reviewers below.

- Revision-4 continuation audit — the packet and its six-role human routing
  remain unchanged; no decision IDs or adjudication were invented. The
  repository-wide AI gate now passes 965 tests with 112 explicit conditional
  skips and one known Starlette/httpx warning. This is regression evidence for
  the surrounding runtime only; it does not convert the 60-case calibration
  packet or the 1,000-case Golden candidate into approved evidence.

- Revision-5 regression audit — the repository-wide AI gate now passes 967
  tests with 112 explicit conditional skips and the same known warning. The
  retrieval manifest tests are local integrity evidence only; they do not
  create Product, Brand, Legal, Data/Privacy or Release approval.

## Human operator packet

Before any promotion decision, provide:

- the pinned ViVi voice artifact digests for rubric, domain pack, board policy,
  calibration plan and held-out plan;
- a Product Owner note on tone, response economy and clarification/refusal
  behaviour;
- a Design Lead note on UX clarity and task transparency;
- a VinFast Content/Brand SME note on safe wording, use of “ViVi” and any
  prohibited phrasing;
- a Legal Owner note that no hidden claims, promises or authorization gaps
  were introduced;
- a Data/Privacy Owner note that the packet contains no PII, secrets or
  training leakage;
- a Release Owner decision ID once the packet itself is accepted.

The operator then creates the 60-case calibration packet outside the Golden
set, keeps the 1,000-case held-out suite immutable and records the reviewer
decision IDs separately. This packet does not authorize release.

Safe operator wording:

> VFBIZ-0200 ViVi text voice v1 is a digest-pinned review candidate only.
> These artifacts are not Brand approval, release approval, data/training
> rights, Dataset Release, Golden adjudication or public assistant
> authorization. Review notes and decision IDs must bind to the pinned digests.
> The 60-case calibration packet must be created outside the 1,000-case Golden
> set and must not include PII, secrets, production conversations,
> unauthorized VinFast corpus content or held-out Golden cases.

## Evidence

- [x] Focused voice/linkage tests —
  `backend/ai/tests/evaluation/test_vivi_voice_artifacts.py` passes, including
  digest linkage, smoke rubric, authority load, tamper rejection and unknown
  revision rejection.
- [x] Calibration packet — exactly 60 fact-free pending cases across 12
  families, content-addressed and privately materialized; 20 focused voice
  tests pass including tamper, full-resign, split-overlap and store replay.
- [x] Independent calibration review — two bounded review cycles closed trusted
  content binding, six-role enforcement, filesystem replay, calibration
  lineage and scoreable voice-policy coverage findings. Recommendation is
  `needs-human-decision`, not approval.
- [x] Voice artifact revisions — rubric
  `548051aab2d5f019693c0a45d94dfc421296300555de5ea1e424a4807c9e9f2d`,
  domain pack `23b16f3cf148f456c8ffd8c510fa7e44352e56baf7925b17b6b727b856414b57`,
  board policy `d16524120b5613b991672d9d57b36554deb1c4746b2b6f1d42e2b667bb19f3a1`,
  calibration plan `819c2286d2503098f1f8f42818488a579da0f02c7d916cd0c498b745693805b6`,
  held-out plan `bcdbf4d928a221b837ed9ca9c8460d6ca3a8f54eb7dfc625d2944bcf7ed5f2e2`,
  suite voice digest `b223c5394201ae67c3ce0a88d05da1850ae51018b8e85129b030c60854cdeb5e`.
- [x] Golden-domain reviewer — returned `needs-human-decision`, confirmed role
  routing and safe packet wording, and confirmed no approval or release claim.
- [x] Risk reviewer — confirmed corpus upload, Dataset Release, Golden binding,
  factual staging, supply-chain and public activation remain human-blocked.
- [x] `npm run verify:ai` — passed with 824 tests and 101 explicit skips; Ruff,
  Pyright and Alembic dry-run through `20260801_0023` passed.
- [x] PostgreSQL integration — 215 tests pass on fresh PostgreSQL 17/pgvector.
- [x] `npm run contracts:lint` — passed with 38 contracts, 67 dataset vectors,
  8 isolated operations and 24 workforce capabilities.
- [x] `npm run governance:check` — passed with 195 canonical work items and 75
  provider-neutral context scenarios.
