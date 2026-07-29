---
id: VFBIZ-0188
title: Resolve semantic classifier runtime authority
status: done
mode: controlled
priority: P0
owner_team: ai-assurance
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/modules/governance
  - backend/ai/tests/unit/governance
  - backend/ai/tests/integration/governance
  - backend/ai/docs/evaluation-and-release.md
  - docs/work/items/VFBIZ-0188.md
  - WORK.md
depends_on: []
controlled_signals:
  - customer-chat
  - model-routing
  - ai-release
exclusive_resources:
  - ai-release-registry
required_checks:
  - npm run verify:ai
  - npm run contracts:lint
  - npm run governance:check
revision: 5
review_date: "2026-08-29"
updated_at: "2026-07-29T09:27:52.776Z"
---

# Outcome

Add a fail-closed Python authority that resolves one canonical semantic
classifier binding for an exact active Assistant Release activation without
allowing the model, environment variables or a stale evidence record to enable
semantic routing.

## Constraints

- The additive
  `assistant-release-classifier-binding/v1` contract at `a402e79` is canonical.
- Assistant Release Manifest v3 remains deterministic-only.
- The binding must target the exact activation ID and activation-envelope
  digest resolved for the turn.
- Threshold values remain in a code-owned routing-policy artifact; this work
  item validates its identity but does not compose a classifier provider.
- No public Chat API composition, provider endpoint or database migration is
  introduced in this lane.

## Done when

- Domain parsing rejects unknown fields, malformed references, invalid digests,
  stale or inverted effective windows and mismatched evidence/approval targets.
- Classification-stack, binding-core and binding-envelope digests are
  recomputed from canonical projections rather than trusted from the caller.
- Application resolution verifies the target activation, assistant profile,
  environment and all trusted artifacts/evidence within one freshness scope.
- A missing, revoked, expired or mismatched binding returns a typed fail-closed
  outcome; Manifest v3 alone can never enable semantic routing.
- Cancellation, timeout and bounded-concurrency behavior are tested.

## Checkpoint

- Contract authority `a402e79` is available and VFBIZ-0169 application policy
  fixes are checkpointed at `c678d6c`.
- Checkpoints `7deee8b` and `a191f88` add canonical digest recomputation, the
  bounded fail-closed resolver, the real Draft 2020-12 schema adapter,
  lifecycle-aware revocation and concurrency/permit-recovery tests.
- Manifest v3 without the additive binding deterministically returns
  `CLASSIFIER_BINDING_NOT_FOUND`.
- Exact next action: complete independent reviewer and risk-reviewer evidence;
  PostgreSQL persistence and bootstrap composition remain separate follow-up
  work and are not implied by this bounded authority item.

## Evidence

- [x] `npm run verify:ai` — Ruff and Pyright passed; 531 tests passed and 84
  environment-gated tests were skipped by the local fast suite; Alembic static
  SQL generation passed through revision `20260729_0018`.
- [x] `npm run contracts:lint` — five OpenAPI descriptions, 32 registered AI
  contracts, 49 dataset/authority vectors and 24 workforce capabilities
  passed.
- [x] `npm run governance:check` — docs, reports, authorization, 168 work items,
  provider adapters, skills and 75 context scenarios passed.
- [x] Focused authority suite — 14 tests passed, including digest tampering,
  schema rejection, revoke/not-found distinction, queue timeout, permit
  recovery and cancellation.
- [x] Independent reviewer-verifier — run
  `codex-vfbiz-0188-review-1` found no remaining P0/P1 at `a191f88`.
- [x] Independent risk-reviewer — evidence
  `review://VFBIZ-0188/codex-vfbiz-0188-risk-1/a191f88` found no P0/P1 in the
  bounded authority; production evidence-kind verification, pre-invocation
  freshness recheck and upstream admission caps remain mandatory follow-up
  controls for persistence/bootstrap composition.

### active — 2026-07-29T09:06:17.088Z

Implement canonical binding domain and fail-closed authority resolver from contract a402e79 before any provider or bootstrap composition.

### review — 2026-07-29T09:22:20.829Z

Implementation checkpoints 7deee8b and a191f88 passed required checks; independent reviewer and risk-reviewer formal evidence are in progress.

### done — 2026-07-29T09:27:52.776Z

Bounded semantic classifier authority accepted at a191f88 with completed implementer, reviewer-verifier and risk-reviewer evidence; persistence/provider/bootstrap remain separate follow-up gates.
