---
id: VFBIZ-0208
title: Build Vertex synthetic smoke authority and preflight ledger
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
  - backend/ai/app/infrastructure/model_providers/vertex_smoke_authority.py
  - backend/ai/tests/unit/inference/test_vertex_smoke_authority.py
  - docs/work/items/VFBIZ-0208.md
  - WORK.md
depends_on: []
controlled_signals:
  - ai-provider
  - ai-evaluation
  - ai-budget-policy
  - pii
exclusive_resources:
  - ai-provider-registry
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 5
review_date: "2026-08-30"
updated_at: "2026-07-30T17:13:15.209Z"
---

# Outcome

Create a deterministic, fail-closed authority boundary for one synthetic Vertex
generation request and one embedding request, with immutable fixture,
least-privilege identity, provider-data-control and budget-ledger preflight.

## Constraints

- This lane may inspect IAM and build sanitized preflight evidence but may not
  grant IAM, create service-account keys, change Terraform or call tuning,
  dataset, pipeline, deployment or activation APIs.
- Inputs are fixed content-free synthetic fixtures; VinFast facts, Golden cases,
  customer data, corpus text and external-source content are forbidden.
- Each capability has at most one provider attempt. Total reservation is below
  USD 1 and daily application admission remains below USD 5.
- The runner fails before token acquisition when fixture digest, PII/secret
  scan, project/location/model, pricing/retention evidence, IAM denial set or
  request-count ledger is incomplete.
- Evidence contains hashes, identity, model, usage, latency, typed outcome and
  cost only; never prompts, vectors, provider bodies or credentials.
- This work grants no Dataset, Golden, tuning, RAG bake-off, staging or release
  authority and does not unblock VFBIZ-0201/0202 by itself.

## Done when

- An immutable smoke manifest pins fixture hashes, exact model endpoints,
  positive pricing revision, retention decision reference and cost/request caps.
- A concurrency-safe local ledger reserves each capability once, reconciles
  success/failure/ambiguous outcome and rejects replay or overspend.
- Preflight rejects secrets/PII, unexpected fixture content, broad IAM,
  missing prediction permission, forbidden permissions and mutable operator
  inputs before a provider call.
- Deterministic tests cover tamper, replay, concurrency, expired packet,
  wrong project/location/model, pricing, IAM, cancellation and sanitized
  evidence.
- The local preflight either authorizes exactly one bounded synthetic smoke or
  emits a precise no-call operator packet.
- Required repository checks and independent recommendation-only review pass.

## Checkpoint

- Code-complete locally: the authority binds two canonical content-free
  fixtures, exact project/service-account/permission evidence, endpoint
  identity, pricing-derived token reservations, an application-owned
  ledger path/key ID, HMAC state/anchor, cancellation boundaries and sanitized
  audit evidence.
- No Vertex request was made. The no-call packet digest is
  `e84e65e7571ac97013f27e187ede50d1bfaefd4c4644784e17d866fea14d3006`;
  it records zero provider requests and zero spend.
- The final risk review accepted only the no-call checkpoint and found an
  execution-authorization bypass plus incomplete token-failure reconciliation.
  The current unreviewed remediation seals the full authorization binding and
  reconciles token acquisition failure in authority
  `20ba3cf3accd50a6ef83a3de4dc2eefe8f6f0737a9be36c75d9fbc1e33373990`
  with tests
  `153b71274a13b88941344ec83650b43c0d11cc254cda534559852001f9eb9c50`.
- The canonical dataset-quality review budget permits only one cycle, so agents
  cannot approve the remediated snapshot. This is not a substitute for the
  required human Data Owner, Privacy, Security, Engineering and spend
  decisions.
- Exact next action: the named human authorities review the packet and provide
  immutable model/location, data-control, exact fixture-digest, IAM and pricing
  evidence; only then may a fresh controlled item attempt the two live calls.

## Evidence

- [x] `npm run verify:ai` — 684 passed, 95 skipped; Ruff, Pyright and static
  Alembic upgrade through `20260730_0021` passed on 2026-07-30.
- [x] `npm run governance:check` — all governance checks passed on 2026-07-30.
- [x] `npm run contracts:lint` — five OpenAPI descriptions, runtime contracts,
  dataset vectors and workforce capabilities passed on 2026-07-30.
- [x] `npm run verify:api` — lint/typecheck, 379 unit/contract/integration
  tests, 67 E2E tests, Prisma validation and Nest build passed after pinning the
  API scripts to the workspace's Jest 30 binary.
- [x] focused smoke authority — Ruff/Pyright clean and 31 tests passed.

### ready — 2026-07-30T16:54:35.386Z

Synthetic-only preflight and ledger scope is decision-ready; provider calls and IAM mutations remain excluded.

### active — 2026-07-30T16:54:35.675Z

Begin deterministic authority implementation; no live spend before preflight passes.

### blocked — 2026-07-30T17:13:15.209Z

No-call checkpoint: local authority and 29 focused tests are green, but live Vertex requires immutable human model/location, Data/Privacy, Security IAM, pricing/spend and fixture-digest evidence; canonical agent review budget is exhausted and agents cannot approve those gates.
