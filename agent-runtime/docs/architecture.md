---
id: agent-runtime-implementation-architecture
title: Agent runtime implementation architecture
status: active
owner_role: engineering-lead
scope: agent-runtime
when_to_read:
  - agent-runtime
  - runtime-state
  - agent-tool
tags:
  - agents
  - architecture
  - sqlite
revision: 2
review_date: 2026-08-30
supersedes: []
---

# Agent runtime implementation architecture

## Layers

The runtime uses ports and adapters. Domain files define runs, events,
checkpoints, approvals, budgets and artifacts. Application use cases own state
transitions. Adapters connect SQLite, deterministic governance, OpenAI Agents
SDK, Codex MCP, fixture worktrees and safe trace metadata.

No adapter deep-imports a product workspace. The dependency direction ends at
ports inside this package.

## Execution authority

The deterministic governance adapter resolves work, owner, context and revision
before an agent runs. Canonical mode cannot be downgraded by a caller; controlled
dispatch requires a live claim, exact fencing token and validated paths. Agents
SDK owns the model loop and agents-as-tools.
VFBiz code owns queue state, retry, checkpoint, approval and completion rules.
Codex is a coding executor and cannot orchestrate nested agents.

## Persistence

SQLite is stored below the Git common directory, uses WAL and foreign keys and
is readable by worktrees on one host. Optimistic versions and idempotency keys
protect replay. Serialized Agents SDK state is AES-256-GCM encrypted with a key
outside Git. Migrations `0001` through `0006` cover the initial ledger,
governance claim identity, content-addressed event provenance and compatible
upgrades for approval, usage and checkpoint idempotency. Work-item state remains
in Git.

## Communication

Cross-agent communication is limited to `AgentResult`, coordination/approval
requests, review findings and content-addressed artifact references. Model text
is descriptive; only schema-valid records can drive application transitions.
Required reviewers count only after a completed typed specialist result was
observed from the SDK tool output. The runtime aggregates their findings itself.
Artifact files are constrained to canonical allowed paths and rehashed from
their bytes before their reference is recorded.
