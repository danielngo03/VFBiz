---
id: VFBIZ-0201
title: Add Vertex model adapters and execute governed RAG bake-off
status: proposed
mode: controlled
priority: P0
owner_team: ai-model-platform
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai/app/infrastructure
  - backend/ai/app/modules/inference
  - backend/ai/app/modules/evaluation
  - backend/ai/tests
  - backend/ai/dataset-specs
  - .agents/skills/operate-gcp-ai
  - docs/work/plans/vivi-gcp-ai-platform.md
  - docs/work/items/VFBIZ-0201.md
  - WORK.md
depends_on:
  - VFBIZ-0199
  - VFBIZ-0200
  - VFBIZ-0110
controlled_signals:
  - ai-provider
  - ai-evaluation
  - ai-budget-policy
exclusive_resources:
  - ai-provider-registry
  - ai-evaluation-suite-registry
required_checks:
  - npm run verify:ai
  - npm run verify:ai:integration
  - npm run governance:check
revision: 12
review_date: "2026-08-30"
updated_at: "2026-08-02T23:27:16+07:00"
---

# Outcome

Implement release-pinned Vertex embedding and generation candidates and select
a RAG baseline through cost-bounded, independently reviewed bake-off evidence.

## Constraints

- Provider/model names stay in infrastructure and release descriptors.
- Provider stays disabled until a matching release is accepted.
- No Pro live traffic, GPU or Provisioned Throughput in this work item.
- Real-provider tests have explicit pre-spend cost caps.

## Done when

- Vertex adapters enforce project, region, model revision, budget, cancellation,
  response bounds, exact model identity and normalized usage.
- `gemini-embedding-001` 768/1536 and Flash-Lite/Flash candidates are compared
  on pinned Vietnamese retrieval/generation suites.
- Hard gates, Recall/nDCG/MRR, latency and cost evidence select or reject each
  candidate without automatic promotion.

## Checkpoint

- Proposed until VFBIZ-0199 cloud execution, VFBIZ-0200 voice linkage and the
  approved retrieval suite are available.
- The earlier 2026-08-01 no-model observation is superseded by official Google
  lifecycle and model-card evidence updated on 2026-07-30/31:
  `gemini-3.5-flash` is GA through at least 2027-05-19 and
  `gemini-3.5-flash-lite` is GA through at least 2027-07-21.
- The two candidates do not have equivalent residency or tuning capability.
  `gemini-3.5-flash` supports `asia-southeast1` and supervised tuning.
  `gemini-3.5-flash-lite` supports only `global`, `us` and `eu` endpoints and
  does not support tuning. Therefore the strict Singapore regional baseline
  candidate is `gemini-3.5-flash`; Flash-Lite may enter a cost bake-off only
  after a separate Data/Privacy residency decision allows a non-Singapore
  endpoint.
- A read-only project preflight with the active development identity listed
  both publisher model resources. This proves catalog visibility only; it does
  not prove quota, dispatch permission, retention acceptance or runtime
  readiness and incurred no inference spend.
- `gemini-embedding-001` remains the embedding candidate. Official lifecycle
  evidence commits availability no sooner than 2028-05-20; the 768/1536
  output-dimensionality comparison remains required.
- The 2026-08-02 runtime-readiness audit initially found the production
  composition was not Vertex-wired. Revision 7 closes that documentation/code
  mismatch: `Settings`, both provider factories and the release-bound
  `build_turn_runtime` path now accept Vertex only with pinned deployment and
  approval evidence. This proves composition and negative-path behavior only;
  no real provider request, model selection or release activation is claimed.
- Dependency disposition remains closed for execution:
  VFBIZ-0199 has restricted synthetic packet acceptance but cloud execution is
  incomplete; VFBIZ-0200 remains `review` with zero human labels; VFBIZ-0110
  remains `proposed` because no approved Vietnamese held-out retrieval suite is
  bound. VFBIZ-0215 improved authenticated-staging fail-closed control but its
  independent risk gate is held on Redis enabled-snapshot replay authority.
- Exact next action: keep dispatch disabled while VFBIZ-0199 and the governed
  retrieval-suite dependency remain incomplete; prepare the release-bound
  runtime wiring against the exact Singapore `gemini-3.5-flash` identity only
  after this work item becomes active.
- Revision-5 implements the provider-neutral Vertex runtime composition without
  enabling it: settings now accept `vertex` only with a pinned project,
  location, model allowlist, data-control digest, pricing revision and token
  prices; generation and embedding factories instantiate the existing Vertex
  adapters; and ADC/workload identity is refreshed lazily without user-managed
  keys. Focused configuration tests and the full AI gate pass. The item remains
  proposed, no provider call occurred, and no release/approval state changed.
- Revision-6 reruns the full AI gate after the residency-binding correction:
  954 tests pass, 112 are explicit conditional skips and one existing
  Starlette/httpx warning remains. No provider request or spend occurred.
- Revision-7 continuation audit confirms provider-neutral release composition:
  Vertex settings validation, ADC/workload-identity factories and
  release-bound model-mesh construction are covered by the current AI suite;
  the work item remains proposed because GCP ingestion, approved retrieval
  suite, voice authority, quota, pricing and cost gates are incomplete.
- The focused no-spend Vertex/runtime regression set collected 52 cases and
  completed with 50 passed and 2 explicit skips. It exercised provider
  configuration, Vertex generation/embedding adapters, conversation runtime
  composition and authenticated-staging fail-closed behavior; no network
  request or provider charge occurred.

## Operator packet (preflight only)

When the dependencies open, the operator must bind one exact Assistant Release
Manifest before any live request. The packet must include:

- VFBIZ-0199 synthetic ingestion evidence and a clean, approved retrieval suite
  from VFBIZ-0110; no raw VinFast PDF may be used as a substitute;
- the VFBIZ-0200 voice decision IDs and held-out/calibration isolation
  evidence, without treating agent recommendations as approval;
- generation identity `gemini-3.5-flash` in `asia-southeast1` and embedding
  identity `gemini-embedding-001` with one declared dimension per run;
- numeric pricing revision, retention/data-control decision digest, quota
  proof, application cost reservation and a create-only dispatch witness;
- a rollback pointer and kill-switch receipt. Missing or mismatched fields
  produce `no-dispatch`; the runtime must not change model, region or endpoint
  automatically.

The operator runs the no-spend contract and deterministic suite first, records
the exact packet digest, and only afterward may request a separately authorized
live bake-off. This packet does not create a managed Dataset, submit tuning,
activate a retriever or enable public Chat.

Revision-9 evaluation hardening closes a false-pass path in the provider-neutral
retrieval summary: empty evidence/refusal metric slices now score `0.0`, and
the Vietnamese bake-off validator requires both at least one evidence case and
one refusal case in addition to the language/risk tags. Focused retrieval tests
pass. The full AI gate now reports 967 passed, 112 conditional skips and the
known Starlette/httpx warning. Observations now reject an evidence/non-evidence
outcome mismatch with its expected chunk set, preventing malformed rows from
inflating retrieval metrics. No provider request or evaluation spend occurred.

Revision-11 adds a frozen `RetrievalBakeoffManifest` authority envelope. It
rejects duplicate case IDs, mixed source-release digests, non-held-out cases
and any suite digest that does not match the canonical ordered case projection.
Revision-12 adds a separate `RetrievalSuiteAuthority` record and validator: a
manifest digest alone cannot stand in for provenance, held-out status or
release authority, and every source/index/evaluator revision must match the
external record. The focused manifest/authority suite passes; the external
VFBIZ-0110 retrieval-suite authority, quota, pricing and data-control gates
remain unresolved, so no bake-off or provider request is authorized.

The current full AI gate passes 969 tests with 112 conditional skips and the
known Starlette/httpx deprecation warning; Alembic offline SQL generation still
reaches `20260802_0025`. This is local contract evidence only and does not
authorize a provider request or a release.

## Evidence

- [ ] No implementation or provider spend is authorized while this item remains
  proposed and its dependencies are incomplete.
- [x] Official-model preflight corrected the nonexistent 3.5 aliases and sealed
  the earlier no-dispatch decision.
- [x] 2026-08-02 official lifecycle/model-card refresh — Google now lists both
  3.5 models as GA. Only `gemini-3.5-flash` satisfies the current Singapore
  endpoint constraint and supports supervised tuning. The official embedding
  lifecycle and configurable output dimensionality also remain compatible
  with the planned 768/1536 bake-off. Sources:
  [model lifecycle](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions),
  [Gemini 3.5 Flash](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-flash),
  [Gemini 3.5 Flash-Lite](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-flash-lite)
  and
  [text embeddings](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings).
- [x] Read-only Model Garden catalog preflight —
  `gcloud ai model-garden models list` with the development project as quota
  project returned exact resources
  `publishers/google/models/gemini-3.5-flash` and
  `publishers/google/models/gemini-3.5-flash-lite`. No generation, embedding,
  evaluation or tuning request was submitted.
- [ ] Quota, data-control, exact pricing revision and real dispatch remain
  unproven and blocked by the work-item dependencies and cost gate.
- [x] Read-only composition audit after VFBIZ-0215 — historical evidence
  confirmed no product runtime path could select or instantiate Vertex; that
  finding is superseded by the release-gated factory wiring recorded in
  Revision 5/7. No provider call or spend occurred.
- [ ] Activation/readiness gate — VFBIZ-0199 cloud completion, VFBIZ-0200
  authority decision, VFBIZ-0110 approved suite and VFBIZ-0215 risk disposition
  remain required before this item can move from `proposed` to `active`.
- [x] Release-gated Vertex factory wiring — provider settings, ADC token
  boundary, generation/embedding composition and negative configuration tests;
  no network call or spend.
- [x] Current AI regression evidence — the full AI gate exercises the Vertex
  settings/factory/model-mesh paths and release mismatch negatives. This is
  local composition evidence only; it is not a live Vertex Evaluation or
  tuning result.
- [x] Focused runtime regression evidence — 52 collected cases, 50 passed and
  2 explicit skips across Vertex adapters, release-bound conversation
  composition and authenticated-staging guards; no provider request or spend.
