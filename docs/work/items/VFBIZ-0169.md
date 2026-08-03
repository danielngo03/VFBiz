---
id: VFBIZ-0169
title: Add governed semantic routing
status: blocked
mode: controlled
priority: P0
owner_team: ai-assistant-orchestration
accountable_role: engineering-lead
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/.env.example
  - backend/ai/app/bootstrap
  - backend/ai/app/infrastructure/model_providers
  - backend/ai/app/modules/assistant
  - backend/ai/app/modules/governance/infrastructure
  - backend/ai/app/platform/config
  - backend/ai/tests/contract
  - backend/ai/tests/integration/platform
  - backend/ai/tests/unit/bootstrap
  - backend/ai/tests/unit/governance
  - backend/ai/tests/unit/inference
  - backend/ai/tests/unit/platform
  - backend/ai/tests/unit/assistant
  - backend/ai/docs/conversation-graph.md
  - contracts/ai
  - docs/architecture/customer-assistant-capability-maturity.json
  - docs/architecture/customer-assistant-capability-maturity.md
  - docs/INDEX.md
  - docs/work/items/VFBIZ-0169.md
  - WORK.md
depends_on: []
controlled_signals:
  - customer-chat
  - ai-orchestration
  - model-routing
  - grounding
exclusive_resources:
  - conversation-graph
required_checks:
  - npm run verify:ai
  - npm run contracts:lint
  - npm run governance:check
revision: 10
review_date: "2026-08-29"
updated_at: "2026-08-03T00:18:00+07:00"
---

# Outcome

Add a release-bound two-tier supervisor that uses deterministic routing as the
safe fallback and an independently evaluated semantic classifier only when the
active Assistant Release explicitly pins its identity, schema and thresholds.

## Constraints

- Routing policy, confidence thresholds, clarification and tool eligibility
  remain code-owned.
- Classifier output is a strict bounded schema: intent, confidence, required and
  missing slots, multi-intent, out-of-domain and abuse signals.
- Provider/model/dataset names do not become top-level modules.
- A classifier timeout, invalid output, budget failure or release mismatch
  falls back deterministically; it cannot bypass authorization or grounding.
- Public Chat API remains disabled.

## Done when

- Assistant Release authority pins classifier artifact digest, output schema,
  threshold policy and evaluation evidence.
- VI/EN, no-diacritics, typo, slang, code-switch, implicit intent,
  multi-intent, OOD and injection slices have immutable benchmark evidence.
- Low confidence and missing slots produce terminal clarification.
- Model output cannot select an unregistered worker or tool.
- Fallback behavior is observable, bounded and covered by outage tests.

## Checkpoint

- Checkpoint `c057cd8` adds a strict two-tier supervisor application boundary.
  A release-bound semantic classifier is the routing authority for both
  keyword-matched and implicit inputs; the deterministic keyword router is
  only a bounded fallback. Keyword confidence is capped at `0.6`, so a
  healthy classifier gets a chance to validate/override the match and a
  classifier outage cannot turn a heuristic into an authoritative decision.
  Timeout or invalid output falls back deterministically without removing
  abuse signals.
- Review fix `c678d6c` enforces `missingSlots ⊆ requiredSlots`, binds the
  threshold-policy digest and values, and rejects unregistered abuse signals.
- Contract `a402e79` adds the canonical additive classifier binding; Manifest
  v3 alone remains deterministic-only. Python authority checkpoints `7deee8b`
  and `a191f88` verify canonical digests, lifecycle, artifacts and evidence.
- Runtime implementation now composes a PostgreSQL-resolved, evidence-verified
  classifier binding per turn. The provider-neutral HTTP adapter requires an
  exact deployment artifact match, a canonical strict output contract, bounded
  request/response/concurrency, no redirects and no environment proxy.
- Missing, revoked, stale, mismatched or unavailable classifier authority
  falls back to `KeywordSupervisor`; cancellation still propagates.
- PostgreSQL integration now exercises both the classifier binding store and
  the factual graph composition. Public Chat API remains disabled.
- Exact next action: produce immutable VI/EN routing-slice evidence through the
  VFBIZ-0192 evaluation executor before any classifier activation.

- Revision-9 routing hardening — `KeywordSupervisor` now emits at most `0.6`
  confidence for a single keyword match. Focused regression tests prove a
  release-bound semantic classifier is called for a keyword route and that a
  timeout returns the capped deterministic fallback with an explicit
  `classifier_unavailable` reason. The application-layer policy also rejects
  any release binding whose semantic activation threshold is not strictly
  above the fallback cap, preventing threshold drift. This is local policy
  evidence only; the semantic classifier remains inactive until immutable
  routing-slice evidence is accepted.

- The post-change repository AI gate passes 967 tests with 112 explicit
  conditional skips and the same known Starlette/httpx warning. No semantic
  classifier request or public Chat activation occurred.

## Evidence

- [x] `npm run governance:check` — docs, reports, authorization, work-control
  and agent-governance checks passed.
- [x] `npm run verify:ai` — 550 local tests passed; Ruff, Pyright and migration
  replay passed.
- [x] `VFBIZ_RUN_DB_INTEGRATION=1 uv run pytest tests -q` — the complete AI
  test suite passed with PostgreSQL integrations enabled.
- [x] `npm run contracts:lint` — 34 registered AI contracts and 55 vectors
  passed, including the strict semantic route output contract.

### ready — 2026-07-29T08:35:58.456Z

Durable task authority checkpoint 43d9cc3 is available; semantic routing contract scope is decision-ready.

### active — 2026-07-29T08:35:58.738Z

Begin release-bound classifier contract with negative vectors before runtime composition.

### blocked — 2026-07-29T08:46:31.526Z

Blocking coordination coord-8f252c69-1785-462a-8f2f-6dc876ae25fd must add classifier authority to the canonical Assistant Release contract before bootstrap composition.

### active — 2026-07-29T08:55:30.169Z

Resume active remediation of independent P1 review findings while classifier authority coordination is implemented in its separate contract lane.

### blocked — 2026-07-29T09:24:06.433Z

Provider-neutral classifier/policy adapter, PostgreSQL binding persistence, bootstrap composition and immutable routing-slice evidence are owned by open coordination requests coord-05b2d84c-2482-4cc3-a20a-1494b570bee9 and coord-155ef386-d53c-4ce8-a9a0-d6d357644ff4; semantic runtime remains disabled.

### blocked — 2026-07-29T17:23:56.394Z

Semantic routing runtime, PostgreSQL binding adapter, canonical output contract and fail-closed provider composition passed full AI plus DB integration. Remaining blocker is immutable VI/EN slice evidence through VFBIZ-0192 before activation.
