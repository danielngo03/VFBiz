---
id: VFBIZ-0195
title: Open the Customer Assistant staging path
status: proposed
mode: controlled
priority: P0
owner_team: customer-web-experience
accountable_role: release-owner
primary_workspace: customer-portal
affected_workspaces:
  - customer-portal
  - workforce-portal
  - api
  - ai
  - root
allowed_paths:
  - apps/customer-portal
  - apps/workforce-portal
  - backend/api/src/app.module.ts
  - backend/api/src/modules/engagement
  - backend/api/test
  - backend/ai/app
  - backend/ai/tests
  - docs/work/items/VFBIZ-0195.md
  - WORK.md
depends_on:
  - VFBIZ-0194
  - VFBIZ-0196
  - VFBIZ-0197
controlled_signals:
  - customer-chat
  - public-contract
  - shadow-canary
  - staging-release
exclusive_resources:
  - public-contract
  - conversation-runtime
  - ai-release-registry
required_checks:
  - npm run verify:api
  - npm run verify:ai
  - npm run verify:apps
  - npm run verify:apps:e2e
revision: 3
review_date: "2026-08-29"
updated_at: "2026-07-29T18:45:46Z"
---

# Outcome

Compose the public Chat API and customer/workforce experiences only after the
factual runtime gate has passed and staging release authority approves it.

## Constraints

- Browsers never receive provider credentials or call FastAPI directly.
- Final responses persist before completion events.
- Continuous evaluation is sampled or batch, never a synchronous judge on every request.

## Done when

- Portal to API to AI to PostgreSQL to SSE runs end to end.
- Citation, clarification, refusal, cancellation, reconnect and handoff have browser evidence.
- Public composition fails closed when release readiness is absent.
- Rollback and outage drills have durable evidence.
- The 1,000-case Golden staging suite has immutable human-adjudication evidence.
- The production dependency graph has zero unexcepted high or critical findings.

## Checkpoint

- Exact next action: remain proposed and human-blocked until VFBIZ-0194,
  VFBIZ-0196 and VFBIZ-0197 are done.

## Human operator packet

Staging may be considered only when the Release Owner receives:

- VFBIZ-0194 factual-runtime acceptance with exact Assistant, Knowledge,
  Dataset and Evaluation release/evidence digests;
- VFBIZ-0196 evidence for exactly 1,000 immutable Golden cases, each with
  schema-valid ground truth, rubric/split/provenance digest and a named human
  adjudication decision; count today remains 0/1000;
- contamination, duplication, broken-case and leakage reports with zero open
  hard-gate findings;
- VFBIZ-0197 live dependency evidence showing zero unexcepted high/critical
  production findings;
- named Release Owner staging decision, rollback target, kill switch,
  monitoring window, privacy/cost caps and expiry.

Only after those records resolve may an operator enable the candidate
composition and run `npm run verify:api`, `npm run verify:ai`,
`npm run verify:apps` and `npm run verify:apps:e2e`, followed by the
portal→API→AI→PostgreSQL→SSE staging drills for citation, clarification,
refusal, cancellation, reconnect, handoff, outage and rollback. Until then the
public Chat API stays disabled.

### human-blocked — 2026-07-29T18:45:46Z

VFBIZ-0194 is not accepted, Golden adjudication is 0/1000 and production
supply-chain blockers remain. No staging enablement or Release Owner approval
is represented.

## Evidence

- [ ] `npm run verify:api` — add observed evidence.
- [ ] `npm run verify:ai` — add observed evidence.
- [ ] `npm run verify:apps` — add observed evidence.
- [ ] `npm run verify:apps:e2e` — add observed evidence.
