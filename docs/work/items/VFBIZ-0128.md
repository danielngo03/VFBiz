---
id: VFBIZ-0128
title: Agent control reconciliation and runtime integrity
status: active
mode: controlled
priority: P1
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
allowed_paths:
  - tools/agent-control.mjs
  - tools/lib/agent-control.mjs
  - tools/check-agent-control.mjs
  - docs/work/items/VFBIZ-0128.md
  - WORK.md
depends_on: []
controlled_signals:
  - agent-control
  - concurrency
exclusive_resources: []
required_checks:
  - npm run verify:governance
revision: 4
review_date: "2026-07-27"
updated_at: "2026-07-27T03:57:58.669Z"
---

# Outcome

Agent control can reconcile expired claims/leases deterministically and report
the resulting state without an unrelated mutation or a manual edit of Git's
common-directory state.

## Constraints

- Reconciliation only expires records whose TTL has elapsed; it never releases
  a live claim or closes a Coordination Request.
- The command does not alter work-item status, evidence, run history or
  fencing counters.
- Claim acquisition remains the authority for path/resource collision checks.

## Done when

- `npm run agent:control -- state reconcile` persists expiry transitions and
  returns a count grouped by claim/lease.
- Re-running reconciliation is idempotent.
- A live claim remains active; an expired claim/lease is no longer active.
- Agent-control deterministic tests cover the command's state transition.

## Checkpoint

- Exact next action: mark ready, then implement the reconciliation command and
  its deterministic coverage.

## Evidence

- [ ] `npm run verify:governance` — add evidence reference

### active — 2026-07-27T03:57:58.669Z

Checkpoint recorded; add observed state and one exact next action.
