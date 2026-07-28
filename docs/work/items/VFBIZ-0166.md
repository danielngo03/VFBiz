---
id: VFBIZ-0166
title: Register AI Quality PostgreSQL release gate
status: review
mode: controlled
priority: P0
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
  - ai
allowed_paths:
  - package.json
  - tests/governance/check-ai-integration-discovery.mjs
  - docs/work/items/VFBIZ-0166.md
  - WORK.md
depends_on: []
controlled_signals:
  - ai-quality-platform
  - governance
  - ci
exclusive_resources: []
required_checks:
  - npm run verify:governance
revision: 4
review_date: "2026-08-28"
updated_at: "2026-07-28T14:51:36.785Z"
---

# Outcome

Make the release PostgreSQL gate discover every database-backed AI Quality
test even though AI Assurance owns those tests outside the shared integration
folder.

## Constraints

- Do not move tests into an unrelated bounded context to bypass ownership.
- Local fast verification may skip database tests; release CI must fail if the
  database flag or URL is absent.
- The discovery rule must be deterministic and covered by governance tests.

## Done when

- `verify:ai:integration` includes the governed evaluation registry test.
- Governance test fails if the explicit AI Quality integration target is removed.
- Existing knowledge, governance, dataset and platform integration tests remain included.

## Checkpoint

- Release integration now explicitly discovers the governed evaluation
  PostgreSQL test and retains the shared integration suite.
- Exact next action: keep the governance assertion in every release CI run.

## Evidence

- [x] `npm run verify:governance` — passed, including deterministic AI integration discovery
- [x] `npm run verify:ai:integration` with isolated database configuration — release command ran the shared and evaluation integration tests
- [x] Independent read-only reviewer — PASS; no P0/P1 remains

### ready — 2026-07-28T14:45:43.637Z

Cross-team CI discovery boundary scoped without moving tests.

### active — 2026-07-28T14:45:43.783Z

Begin governance test-first release command registration.

### review — 2026-07-28T14:51:36.785Z

Release integration discovery is governed and verified against PostgreSQL; independent review passed.
