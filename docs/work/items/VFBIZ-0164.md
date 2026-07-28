---
id: VFBIZ-0164
title: Resolve canonical AI contract vectors
status: review
mode: controlled
priority: P0
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
allowed_paths:
  - tools/check-runtime-contracts.mjs
  - docs/work/items/VFBIZ-0164.md
  - WORK.md
depends_on: []
controlled_signals:
  - ai-quality-platform
  - schema
exclusive_resources:
  - public-contract
required_checks:
  - node tools/check-runtime-contracts.mjs --self-test
  - npm run contracts:lint
revision: 4
review_date: "2026-08-28"
updated_at: "2026-07-28T14:05:36.638Z"
---

# Outcome

Make the canonical AI contract registry the single resolver for compatibility
vectors so a new contract can be validated without manufacturing a legacy
alias.

## Constraints

- Preserve legacy-basename compatibility for one registry revision.
- Canonical contract ID and canonical path must resolve directly.
- Ambiguous basenames remain fail-closed.
- Do not weaken schema validation or change contract payloads in this lane.

## Done when

- Vectors resolve by contract ID, canonical path or unambiguous basename.
- Canonical-only AI Quality contracts are compiled and their vectors execute.
- Negative self-tests cover unknown and ambiguous references.
- The complete contract gate passes.

## Checkpoint

- Contract IDs, exact canonical/legacy paths and basename-only references now
  resolve independently. Slash-qualified spoof paths and canonical symlinks
  escaping `contracts/ai` fail closed.
- Canonical Evaluation schemas now compile with strict Ajv. This immediately
  exposed a real strict-type defect in `case-result`; that payload belongs to
  VFBIZ-0154 and is intentionally not changed in this tooling lane.
- Exact next action: independent focused review of the resolver, then release
  this checkpoint so VFBIZ-0154 can repair and revalidate its schemas.

## Evidence

- [x] `node tools/check-runtime-contracts.mjs --self-test` — canonical ID/path,
      basename-only compatibility, path confusion and strict compilation passed.
- [x] `npm run contracts:lint` — passed 2026-07-28 after VFBIZ-0154 repaired the
      schema defect exposed by strict compilation.

### ready — 2026-07-28T13:42:04.110Z

Scope locked to the contract validator and canonical registry resolution.

### active — 2026-07-28T13:42:04.244Z

Implement canonical-only vector resolution test-first.

### review — 2026-07-28T14:05:36.638Z

Canonical resolver and strict schema checker independently reviewed PASS.
