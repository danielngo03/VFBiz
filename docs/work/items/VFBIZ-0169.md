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
revision: 4
review_date: "2026-08-29"
updated_at: "2026-07-29T08:46:31.526Z"
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
- `RouteDecision` now rejects unregistered intent, malformed/duplicate slot and
  required/missing-slot overlap before graph routing.
- Runtime composition remains disabled because Assistant Release Manifest v3
  does not pin classifier identity, schema, thresholds or evaluation evidence.
  Blocking coordination
  `coord-8f252c69-1785-462a-8f2f-6dc876ae25fd` owns the canonical contract.
- Exact next action: accept the versioned classifier release contract, then
  compose the governed supervisor from the resolved active release.

## Evidence

- [x] `npm run verify:ai` — Ruff and Pyright passed; 513 tests passed and 84
  environment-gated tests were skipped by the local fast suite.
- [ ] `npm run contracts:lint` — add evidence reference
- [ ] `npm run governance:check` — add evidence reference

### ready — 2026-07-29T08:35:58.456Z

Durable task authority checkpoint 43d9cc3 is available; semantic routing contract scope is decision-ready.

### active — 2026-07-29T08:35:58.738Z

Begin release-bound classifier contract with negative vectors before runtime composition.

### blocked — 2026-07-29T08:46:31.526Z

Blocking coordination coord-8f252c69-1785-462a-8f2f-6dc876ae25fd must add classifier authority to the canonical Assistant Release contract before bootstrap composition.
