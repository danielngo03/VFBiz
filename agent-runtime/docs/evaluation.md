---
id: agent-runtime-evaluation
title: Agent runtime evaluation procedure
status: active
owner_role: quality-lead
scope: agent-runtime
when_to_read:
  - agent-runtime
  - agent-evaluation
  - prompt-injection
tags:
  - agents
  - evaluation
  - security
revision: 2
review_date: 2026-08-30
supersedes: []
---

# Agent runtime evaluation procedure

## Dataset

Evaluation cases are synthetic and contain no customer conversation, secret or
production dataset. They cover each registered department/team, unknown owner,
tool and path policy, approval authority, retry caps, replay, restart, trace
redaction and prompt injection.

## Gates

Unit tests verify domain and encryption. Contract tests verify schemas, role
catalog and Agents SDK/Codex configuration. Integration tests restart SQLite and
exercise idempotency, approvals and reconciliation. Security tests attempt
path/symlink escape, approval spoofing, product access and trace leakage. Eval
fixtures verify deterministic routing and fail-safe decisions.

Application control tests also reproduce mode downgrade, missing claim,
invented authority, absent typed reviewer output, cancellation ignored by a
provider, token/cost overrun and a crash between approval checkpoint and
approval persistence. Worktree tests verify runtime attestation; Codex diff
collection compares committed effects as well as staged, unstaged and untracked
effects.

Legacy-ledger tests upgrade pre-interruption approvals and pre-idempotency usage
tables. Concurrency tests start two local processes against a new state directory
to verify migration locking. Identical usage from distinct execution segments is
counted twice, while a replay of the same segment key is counted once.

## Rollout

The order is shadow read-only, fixture sandbox and local enterprise routing
simulation. Live product work, draft PR, shared host, production identity or
external mutation require a separate work item and fresh evaluation evidence.
