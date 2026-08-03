---
id: agent-runtime-lifecycle
title: Enterprise agent runtime lifecycle
status: proposed
owner_role: engineering-lead
scope: cross-system
when_to_read:
  - agent-runtime
  - agent-approval
  - agent-recovery
tags:
  - agents
  - lifecycle
  - evidence
revision: 2
review_date: 2026-08-30
supersedes: []
---

# Enterprise agent runtime lifecycle

## Run states

```text
queued -> running -> waiting_approval | waiting_dependency | reviewing
                    ^                                      |
                    +--------------------------------------+
running -> succeeded | failed_safely | cancelled
```

Work-item status remains governed by `tools/work.mjs`. Runtime success only
produces evidence; it never marks canonical work done.

## Intake and assignment

1. Accept a canonical work ID, objective and idempotency key.
2. Resolve repository context and owner through the deterministic resolver.
3. Reject missing/invalid work, unknown owners, unsupported mode or forbidden
   paths before any provider call.
4. For claim-required work, validate the claim, current fencing token, context
   key and all allowed paths through agent-control.
5. Create a runtime run and append the assignment snapshot.
6. Dispatch only roles/tools allowed by the resolved organization budget.

## Execution and communication

Specialists communicate through `AgentResult`, coordination requests, approval
requests, review findings, worker reports and artifact references. Free-form
messages can be human-readable summaries but cannot cause a state transition.
Required reviews must appear as completed, schema-valid specialist outputs; the
runtime aggregates their findings independently of the orchestrator.

One local writer may operate in a fixture worktree. Read-only specialists may
run in parallel. All provider calls have turn/tool/time budgets and a stable
work/run/trace correlation.

## Approval and resume

Before a protected tool call, append an approval request containing the exact
action digest and required human role, checkpoint provider state, then stop.
Approval or rejection appends a new event; it never edits the request. Resume
decrypts state, revalidates governance/context and continues the same run.
If a process dies after checkpointing but before recording the approval row,
the still-interrupted SDK state recreates the same request by call ID and payload
digest, so it cannot execute or obtain a second approval identity.

## Failure and recovery

- A crash leaves committed events/checkpoints intact.
- A worker claims one queued/resumable run with a heartbeat and optimistic
  version; an expired heartbeat becomes reconcilable, not automatically safe.
- After provider execution and before accepting results, context plus
  claim/fencing authority are refreshed. Expired authority fails safely while
  retaining measured usage.
- An uncertain side effect enters reconciliation and requires observed state.
- Same-cause retry and review cycles use canonical organization limits.
- Cancellation stops new dispatch and records outstanding artifacts/claims; it
  never deletes a user worktree. If the worker dies first, stale reconciliation
  finalizes the cancellation instead of re-queuing or stranding the run.

## Evidence and retention

Events include actor, timestamp, context/revision, payload hash and idempotency
key. Raw prompt/tool payloads are excluded from normal logs and provider trace
metadata. Active/waiting checkpoints remain until resolution; completed raw
state defaults to 30-day retention subject to data/security owner approval.

## Authority

The local CLI records candidate human decisions but does not provide strong
enterprise identity. It is sufficient only for sandbox v1. Production approval,
external mutation and release require authenticated human authority in a later
program.
