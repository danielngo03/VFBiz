---
id: VFBIZ-0088
title: Candidate conversation contract isolation gate
status: done
mode: controlled
priority: P0
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
allowed_paths:
  - tools/check-runtime-contracts.mjs
  - package.json
depends_on: []
controlled_signals:
  - public-contract
  - ai-assistant
exclusive_resources: []
required_checks:
  - node tools/check-runtime-contracts.mjs --self-test
  - npm run contracts:lint
revision: 5
review_date: "2026-08-25"
updated_at: "2026-07-24T18:33:40.910Z"
---

# Outcome

Deterministic contract gate validates the isolated Customer Conversation
candidate OpenAPI without leaking unreleased operations into the released
public SDK.

## Constraints

- Only the checker and root contract-lint command may change.
- Do not modify contracts, generated clients, dependencies or lockfiles.
- Candidate operations remain unreleased until their own integration gate.

## Done when

- Candidate OpenAPI is linted and contains all eight required Conversation
  operation IDs.
- Released `packages/api-client/src/generated.ts` contains none of those eight
  operation IDs.
- Positive and negative in-memory self-tests prove both isolation directions
  fail closed.
- Contract lint exits zero once the candidate specification exists.

## Checkpoint

- Exact next action: implement checker isolation, then wait for the candidate
  specification before running the full contract gate.

## Evidence

- [x] `node tools/check-runtime-contracts.mjs --self-test` — PASS; negative
  scenarios cover missing candidate operation, released-SDK leakage, `allOf`
  envelope and missing typed event data.
- [x] `npm run contracts:lint` — PASS; five OpenAPI specifications, six runtime
  schemas and 24 workforce capabilities validated.

### active — 2026-07-24T18:30:00.697Z

Agent Platform implementing candidate/released contract isolation in the deterministic checker only.

### review — 2026-07-25

Agent Platform completed scoped implementation and released its claim. Diff
inspection confirms only `package.json` and `tools/check-runtime-contracts.mjs`
changed in the worker lane.

### review — 2026-07-24T18:33:40.626Z

Candidate/released isolation implementation independently inspected; all required checks passed.

### done — 2026-07-24T18:33:40.910Z

Candidate Conversation contract is linted separately and unreleased operations are fail-closed from the released SDK.
