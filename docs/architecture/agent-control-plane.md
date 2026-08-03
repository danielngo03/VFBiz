---
id: agent-control-plane
title: Enterprise agent control plane
status: proposed
owner_role: engineering-lead
scope: cross-system
when_to_read:
  - agent-runtime
  - multi-agent
  - agent-tool
tags:
  - agents
  - architecture
  - security
revision: 2
review_date: 2026-08-30
supersedes: []
---

# Enterprise agent control plane

## Boundary

`agent-runtime` is an internal execution harness. It owns runtime run
events, checkpoints, local dispatch, approval interruptions and provider trace
correlation. It does not own product work state, business authorization,
customer AI, production infrastructure or release decisions.

```text
Git work item / organization
          |
          v
Agent Runtime ---- SQLite operational ledger
     |                    |
     v                    v
Agents SDK          checkpoint / approval
     |
     +---- typed specialists
     +---- Codex/worktree adapter (fixture only in v1)
     +---- trace/evidence sink
```

## Sources of truth

- Git work item and ExecPlan: approved outcome, scope and evidence.
- `.agents/organization.json`: roles, owners, human authority and budgets.
- Existing agent-control state: claims, leases, coordination and handoffs.
- Runtime SQLite: replayable operational events and encrypted checkpoints.
- Provider traces: diagnostic evidence referenced by ID, never approval.

On every resume or side effect, the runtime re-resolves context and revalidates
the work item, base revision, canonical mode, active claim, fencing token,
allowed paths and approval digest through the existing governance commands.

## Orchestration

The deterministic context resolver runs before a model. A manager-style
orchestrator may call existing roles as bounded tools. Handoffs are reserved for
a specialist that owns the next conversation; workflow phase transitions remain
code-driven. Agents return typed results and cannot name an unknown team, add a
tool, expand a path or approve their own request.

A required reviewer is complete only when the SDK returns a schema-valid output
from that exact specialist tool. The application aggregates independent review
findings and blocks success on P0/P1; an orchestrator summary cannot substitute
for reviewer evidence.

Codex is an executor behind a port, not the workflow authority. Nested Codex
delegation and fresh approval prompts are disabled in v1. Read-only exploration
and fixture worktree mutation use separate sandbox policies.

## Threat boundaries

| Threat | Control | Safe outcome |
| --- | --- | --- |
| Repository or tool prompt injection | content is data; tool/path allowlist is code-owned | refuse or decision packet |
| Approval spoof/replay | actor role, action digest, nonce/idempotency and immutable event | reject |
| Duplicate effect after crash | intent event, idempotency key and reconciliation | observe, do not replay blindly |
| Path/symlink escape | canonical path and worktree-root verification | block before tool call |
| Invented reviewer or authority | registry membership plus observed typed specialist output | fail safely |
| Cost/turn overrun | preflight price policy plus cumulative run budgets | cancel/fail safely |
| Secret or prompt leakage | redacted traces, encrypted checkpoint and fixture-only tests | omit or fail safely |
| State poisoning | event version, schema validation and context/revision recheck | pause/reset candidate run |
| Nested autonomy | one orchestrator, bounded role catalog and disabled Codex subagents | reject delegation |
| Product mutation | changed-path gate and absent product-write tools | fail the run |

## Evolution boundary

PostgreSQL, distributed workers, authenticated approval UI, remote MCP, draft PR
and production actions require new work items and human gates. SQLite schema and
ports must preserve an adapter path without pretending v1 is multi-machine.
