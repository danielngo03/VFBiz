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
  - backend/ai/app/modules/assistant
  - backend/ai/tests/unit/assistant
  - backend/ai/docs/conversation-graph.md
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
revision: 6
review_date: "2026-08-29"
updated_at: "2026-07-29T09:24:06.433Z"
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
  Exact deterministic routes avoid classifier cost; implicit/low-confidence
  inputs use a release-bound semantic prediction; timeout or invalid output
  falls back deterministically without removing abuse signals.
- Review fix `c678d6c` enforces `missingSlots ⊆ requiredSlots`, binds the
  threshold-policy digest and values, and rejects unregistered abuse signals.
- Contract `a402e79` adds the canonical additive classifier binding; Manifest
  v3 alone remains deterministic-only. Python authority checkpoints `7deee8b`
  and `a191f88` verify canonical digests, lifecycle, artifacts and evidence.
- Runtime composition remains disabled. Coordination
  `coord-05b2d84c-2482-4cc3-a20a-1494b570bee9` owns the provider-neutral
  classifier/routing-policy adapter and immutable benchmark evidence.
  Coordination `coord-155ef386-d53c-4ce8-a9a0-d6d357644ff4` owns PostgreSQL
  binding persistence and bootstrap composition.
- Exact next action: implement those two owner-scoped lanes, then run the
  required routing slices before composing the supervisor.

## Evidence

- [x] `npm run verify:ai` — Ruff and Pyright passed; 531 tests passed and 84
  environment-gated tests were skipped by the local fast suite.
- [x] `npm run contracts:lint` — runtime contracts and registered classifier
  binding vectors passed.
- [x] `npm run governance:check` — docs, reports, authorization, work-control
  and agent-governance checks passed.

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
