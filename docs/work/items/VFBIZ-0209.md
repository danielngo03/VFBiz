---
id: VFBIZ-0209
title: Execute bounded Vertex development smoke and seal evidence
status: review
mode: controlled
priority: P0
owner_team: ai-model-platform
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
  - root
allowed_paths:
  - backend/ai/app/infrastructure/model_providers/vertex_smoke_authority.py
  - backend/ai/app/infrastructure/model_providers/vertex_smoke_runner.py
  - backend/ai/scripts/run_vertex_synthetic_smoke.py
  - backend/ai/tests/unit/inference/test_vertex_smoke_authority.py
  - backend/ai/tests/integration/inference/test_vertex_smoke_runner.py
  - infra/gcp/main.tf
  - infra/gcp/vertex_smoke.tf
  - docs/work/items/VFBIZ-0209.md
  - WORK.md
depends_on:
  - VFBIZ-0210
controlled_signals:
  - ai-provider
  - ai-evaluation
  - ai-budget-policy
  - iam
  - pii
exclusive_resources:
  - ai-provider-registry
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 5
review_date: "2026-08-31"
updated_at: "2026-07-31T03:49:00Z"
---

# Outcome

Execute exactly one content-free Vertex generation request and one
`gemini-embedding-001` request in the development project, with the request
body immutably bound to preflight authority, a sub-USD 0.50 daily admission
cap, least-privilege keyless identity and a sanitized sealed receipt.

## Constraints

- The user's development authorization selects `gemini-2.5-flash` for the
  regional generation smoke and `gemini-embedding-001` at `global`, solely for
  content-free synthetic evaluation. This is not a production model, privacy,
  Brand, Data, Legal or release decision.
- Use ADC/service-account impersonation only. Never create a service-account
  key, log an access token, provider body, vector, prompt or credential.
- VFBIZ-0210 first reconciles the existing OpenTofu state/configuration and
  provisions the dedicated identity without replacing existing resources.
- The dedicated smoke identity may hold only online prediction authority; it
  may not create datasets, tuning jobs, pipelines, endpoints, deployments,
  models or batch jobs.
- Exactly one attempt per capability, no retry. A cancellation or ambiguous
  outcome remains terminal. Total provider cost must fail closed below USD
  0.50/day and the operator packet must begin with zero prior requests.
- Raw VinFast documents, rehearsal/Golden cases, customer data and external
  source content are forbidden. Public Chat, retriever activation, managed
  dataset creation, tuning submission and release remain disabled.
- Agents may issue recommendation-only simulated development reviews. They
  cannot be recorded as human Product/Brand/Legal/Data/Privacy/Release
  approval.

## Done when

- VFBIZ-0210 supplies a reviewed no-destroy IaC plan plus the dedicated smoke
  service-account and exact-permission evidence.
- The runner obtains a token only after the manifest, canonical fixture,
  pricing, data-control evidence, exact IAM evidence, ledger and cancellation
  checks pass.
- The exact endpoint, fixture payload/digest, token caps and request body are
  derived from the sealed authorization; caller-supplied provider request
  bodies cannot bypass preflight.
- Tests cover direct-reserve/fabricated authorization, wrong endpoint/payload,
  token failure, cancellation before token/dispatch, provider timeout,
  duplicate execution, ledger/anchor loss and over-budget admission.
- One generation and one embedding request either produce sanitized usage,
  latency, cost and receipt digests or a precise no-call/ambiguous packet.
- Independent reviewer-verifier and risk-reviewer recommendations are recorded
  without authority escalation.
- Full AI, API-related, contract and governance checks remain green; public
  Chat and tuning remain disabled.

## Checkpoint

- The content-free live smoke completed exactly once as
  `vertex-smoke-20260731-001`: one generation and one embedding request,
  two successes, no retry and no raw prompt, response text, token or vector in
  the operator packet.
- The sealed packet SHA-256 is
  `78fe255ea6f01954beef58588b7e4f44c4f0a8da7bf7701a50ff660b866e3d62`.
  Observed usage was 37 input/7 output tokens for generation and four input
  tokens for embedding. Recorded reservation cost was 174 micro-USD.
- The evidence bucket now has unlocked 86,400-second retention and versioning.
  The smoke service account has a separate bucket-scoped custom role containing
  only `storage.buckets.get` and `storage.objects.create`; it has no read, list,
  update or delete permission.
- A network reset occurred after the cloud mutation and before remote state
  persistence. The exact generated recovery state was pushed once, the
  targeted reconciliation then returned `No changes`, and the local recovery
  file was moved to macOS Trash.
- The risk reviewer identified replay and missing failure-packet blockers.
  Both were fixed with production-witness dual-loss tests and sealed
  no-call/ambiguous packets. The reviewer-verifier could not finish its final
  pass because its provider quota was exhausted, so the item remains `review`
  rather than claiming independent acceptance.
- Exact next action: obtain a fresh read-only verifier recommendation when
  capacity is available; do not rerun the consumed provider smoke.

## Evidence

- [x] Focused smoke suite — 48 tests passed; Ruff and Pyright passed.
- [x] `npm run verify:ai` — passed on 2026-07-31 after the live receipt.
- [x] `npm run governance:check` — passed on 2026-07-31.
- [x] OpenTofu targeted post-apply reconciliation — 0 add, 0 change, 0 destroy.

### ready — 2026-07-31T02:28:44.909Z

Development-only Vertex smoke scope is explicit; user selected autonomous model choice and agent recommendation while production human gates remain closed.

### active — 2026-07-31T02:28:45.050Z

Begin IaC drift reconciliation and request-bound runner; no provider call before clean plan and sealed preflight.

### dependency evidence — 2026-07-31T02:45:38Z

The dedicated development smoke identity exists with only
`aiplatform.endpoints.predict`; ADC impersonation is keyless and the operator
binding is exact. This evidence opens offline runner implementation only. It
does not open production data, managed datasets, tuning, retriever activation
or public Chat.
