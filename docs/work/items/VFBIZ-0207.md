---
id: VFBIZ-0207
title: Build Vertex synthetic-only adapter baseline and bounded smoke
status: blocked
mode: controlled
priority: P0
owner_team: ai-model-platform
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai/app/infrastructure/model_providers/vertex_generation.py
  - backend/ai/app/infrastructure/embedding_providers/vertex_embedding.py
  - backend/ai/tests/integration/inference/test_vertex_generation_provider.py
  - backend/ai/tests/integration/inference/test_vertex_embedding_provider.py
  - backend/ai/scripts/run_vertex_synthetic_smoke.py
  - docs/work/items/VFBIZ-0207.md
  - WORK.md
depends_on: []
controlled_signals:
  - ai-provider
  - ai-evaluation
  - ai-budget-policy
exclusive_resources:
  - ai-provider-registry
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 4
review_date: "2026-08-30"
updated_at: "2026-07-30T16:52:39.402Z"
---

# Outcome

Provide provider-neutral Vertex generation and embedding adapters plus one
cost-bounded synthetic live smoke, without using governed corpus, Golden cases,
or creating release/tuning authority.

## Constraints

- GCP project is pinned to `vinfast-503003`; each adapter location must match
  reviewed model availability and its immutable deployment descriptor.
  Credentials come only from Application Default Credentials.
- Live smoke uses content-free synthetic prompts, at most three generation and
  three embedding requests, and fails closed before an estimated USD 1 cap.
- No V3 rehearsal case, VinFast document, managed dataset, tuning submission,
  model activation, retriever activation or public Chat API activation.
- Returned model identity, usage, latency and request bounds are recorded
  without prompts, credentials or provider payloads.
- This work does not satisfy VFBIZ-0201 dependencies and cannot approve Product,
  Brand, Data, Privacy, Legal or Release decisions.

## Done when

- Generation and embedding adapters enforce exact project, region, model,
  deadline, request/response bounds and normalized typed failures.
- Deterministic fake tests cover success, wrong model, timeout, quota/provider
  failure, malformed output and cancellation/budget rejection.
- A one-request-per-capability synthetic smoke either records sanitized evidence
  under local review evidence or records the exact external blocker.
- `npm run verify:ai` and `npm run governance:check` have observed results.
- Independent engineering/risk review records recommendation-only findings.

## Checkpoint

- Deterministic adapters and focused fake-provider tests are implemented.
- Official model availability does not list `gemini-2.5-flash-lite` in
  `asia-southeast1`; the existing GCP foundation region therefore cannot be
  reused as an assumed generation location.
- Exact next action: finish the second independent review, rerun repository
  checks and record a no-live-smoke blocker unless a human authority accepts an
  exact supported location, retention/pricing packet and ADC/IAM run ledger.

## Evidence

- [x] `npm run verify:ai` — 653 passed, 95 skipped; Ruff, Pyright and
  migration SQL through `20260730_0021` passed.
- [x] `npm run governance:check` — instruction, role, work-schema, provider,
  document and 75 context-scenario checks passed.
- [x] `npm run contracts:lint` — 35 AI contracts, 61 dataset vectors, 8
  isolated operations and 24 workforce capabilities passed.
- [x] Focused adapter checks — Ruff and Pyright passed; 24 fake-provider tests
  passed without a live provider call.
- [x] Provider contract research — official Vertex documentation confirms
  `gemini-embedding-001` uses one input per request and does not echo a model
  version in the REST response; Flash-Lite availability currently excludes
  `asia-southeast1`.
- [x] Spend state — zero live Vertex requests and zero provider spend by this
  work item.
- [x] Two independent risk review cycles — pre-spend cost, generation
  region-policy binding, embedding response/truncation, ADC failure typing and
  in-flight cancellation/timeout findings were remediated. Review remains
  recommendation-only and grants no provider/release authority.
- [ ] Live synthetic smoke — blocked because Flash-Lite is not available in the
  pinned foundation region, and the reviewed ADC/IAM identity, pricing/
  retention packet, fixture gate and run-level reservation ledger do not yet
  exist.
- [ ] `npm run verify:api` — stops at the pre-existing
  `resolve-conversation-task-slots.service.spec.ts:95:18`
  `@typescript-eslint/no-unsafe-return`; no Vertex path is mounted publicly.

### ready — 2026-07-30T16:38:08.521Z

Controlled synthetic-only adapter scope is decision-ready; human approvals and tuning remain out of scope.

### active — 2026-07-30T16:38:08.832Z

Begin deterministic adapter implementation; no live spend until focused tests pass.

### blocked — 2026-07-30T16:52:39.402Z

Code-complete synthetic adapters are verified, but live smoke is stopped: gemini-2.5-flash-lite is not available in asia-southeast1 and no human-reviewed alternative location, ADC/IAM principal packet, provider data-controls/pricing decision, synthetic fixture authority or run ledger exists. Do not switch to global or call Vertex until those exact controls are recorded.
