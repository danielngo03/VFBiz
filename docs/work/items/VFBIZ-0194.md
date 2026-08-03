---
id: VFBIZ-0194
title: Complete grounded factual assistant baseline
status: proposed
mode: controlled
priority: P0
owner_team: ai-assistant-orchestration
accountable_role: product-owner
primary_workspace: ai
affected_workspaces:
  - ai
  - api
  - root
allowed_paths:
  - backend/ai/app/modules/assistant
  - backend/ai/app/modules/knowledge
  - backend/ai/app/modules/inference
  - backend/ai/tests
  - backend/api/src/modules/engagement
  - backend/api/test
  - contracts/ai/assistant
  - docs/work/items/VFBIZ-0194.md
  - WORK.md
depends_on:
  - VFBIZ-0136
  - VFBIZ-0169
  - VFBIZ-0191
  - VFBIZ-0192
  - VFBIZ-0193
controlled_signals:
  - customer-chat
  - grounding
  - ai-tool
  - knowledge-release
exclusive_resources:
  - conversation-graph
  - ai-tool-registry
  - knowledge-release
required_checks:
  - npm run contracts:lint
  - npm run verify:api
  - npm run verify:ai
revision: 3
review_date: "2026-08-29"
updated_at: "2026-07-29T18:45:46Z"
---

# Outcome

Complete a factual multi-turn assistant path with released evidence and two
customer-scoped read-only tool proposals while keeping the public API disabled.

## Constraints

- Human Content, Legal and Data approval cannot be synthesized.
- NestJS remains tool execution and object-authorization authority.
- EV, charging and mutation tools remain disabled.

## Done when

- Factual claims pass citation, revision and deterministic grounding gates.
- Missing or unsafe evidence produces refusal or handoff recommendation.
- Vehicle profile and garage tool proposals are schema-bound and audited.
- A real internal multi-turn integration test passes against an approved release.

## Checkpoint

- Exact next action: remain proposed until the human-approved first-party
  Knowledge Release in VFBIZ-0136, VFBIZ-0169 and VFBIZ-0191–0193 are done.

## Human operator packet

Before activation, provide:

- the VFBIZ-0136 first-party Knowledge Release ID, immutable manifest/source
  digests, Content/Legal/Data decision IDs, rollback target and kill-switch
  evidence;
- accepted VFBIZ-0192 evidence-policy decision and a released Dataset
  authority from VFBIZ-0193;
- named internal test subject/vehicle fixtures approved for staging, with no
  production customer data;
- Product Owner acceptance criteria for factual claims, refusal/handoff and
  the two read-only vehicle-profile/garage tool proposals.

The operator then runs `npm run contracts:lint`, `npm run verify:api` and
`npm run verify:ai`, records the exact release and evidence digests, and
executes the internal multi-turn test. Any missing citation, stale revision,
authorization mismatch or disabled tool must fail closed. Public Chat API
composition remains disabled; this packet does not authorize activation.

### human-blocked — 2026-07-29T18:45:46Z

No first-party VinFast Content/Legal/Data-approved Knowledge Release exists.
The work item remains proposed and no approval or staging result is claimed.

## Evidence

- [ ] `npm run contracts:lint` — add observed evidence.
- [ ] `npm run verify:api` — add observed evidence.
- [ ] `npm run verify:ai` — add observed evidence.
