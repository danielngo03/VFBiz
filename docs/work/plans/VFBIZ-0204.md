---
id: plan-VFBIZ-0204
title: ExecPlan VFBiz Enterprise Agent Runtime v1
status: active
owner_role: engineering-lead
scope: cross-system
when_to_read:
  - VFBIZ-0204
  - agent-runtime
  - multi-agent
tags:
  - agents
  - control-plane
  - openai
revision: 2
review_date: 2026-08-30
supersedes: []
---

# Purpose and observable outcome

Add a provider-aware but VFBiz-governed local runtime that can persist and
resume typed agent workflows, route work through the canonical organization,
run sandbox-only fixture execution and attach evidence without changing any
product workspace.

# Scope, boundaries and non-goals

- Allowed paths are exactly those declared by VFBIZ-0204.
- Product code, public contracts, product databases, infrastructure and release
  automation are outside scope.
- Git work items plus the existing agent-control store remain the authority for
  approved work, claims, leases and coordination.
- SQLite is a single-host operational ledger, not a distributed task database.
- The runtime has no public HTTP API and no live external mutation tool.

# Progress

- [x] 2026-07-30: user selected enterprise routing, additive platform boundary,
  local SQLite state, Git/CLI human surface and sandbox-only action.
- [x] 2026-07-30: controlled context classified; writer correctly stopped until
  a valid work item existed.
- [x] 2026-07-30: VFBIZ-0204 allocated with product workspaces excluded.
- [x] Decision packet and controlled assignment are ready.
- [x] Workspace, contracts and SQLite runtime are implemented.
- [x] Agents SDK, Codex/worktree adapters and typed workflows are implemented.
- [x] Security/eval fixtures and documentation are verified locally.
- [x] Two bounded independent correctness/risk review cycles are observed; no
  review granted risk acceptance or release authority.

# Discoveries and surprises

- Current governance already implements local claims, leases, fencing,
  coordination, provider handoffs and retry/review caps. The runtime must reuse
  these controls instead of duplicating them.
- Current repository state is dirty with unrelated AI, mobile and design-token
  work. Root files such as `package.json` and `.agents/organization.json` must
  be patched around those edits without reset or rewrite.
- Existing work IDs VFBIZ-0200 through VFBIZ-0203 are occupied; this program
  uses VFBIZ-0204.
- The current documentation index does not discover every registered workspace;
  the runtime change will make discovery organization-driven without editing
  those workspace documents.
- The first independent reviews found advisory-only mode/claim/reviewer/budget
  controls. These were moved into application/gateway checks, and focused
  reproductions were added before requesting re-review.
- An Agents SDK approval checkpoint and its SQLite approval row cannot be one
  database transaction. Recovery now recreates the same idempotent approval
  from the still-interrupted encrypted SDK state after a crash in that window.
- The second review cycle reproduced real SDK tool-output shape, legacy-ledger
  migration, identical usage segments, cancellation-after-crash and stale
  authority gaps. Each reproduction now has a focused passing test; policy
  stops automated review/fix cycling after this second cycle.

# Decision log

- 2026-07-30 — User: implement an additive runtime and preserve all product
  code/folders.
- 2026-07-30 — Architecture: create a root `agent-runtime` workspace; do not
  place the developer-agent control plane in API, AI or infra. The original
  `platform/agent-runtime` proposal was flattened because `platform` had no
  sibling workspaces. Do not rename it to `agents`, which is ambiguous beside
  the canonical `.agents` organization and provider-specific agent adapters.
- 2026-07-30 — Persistence: SQLite event store in Git common state, with an
  adapter boundary for a future PostgreSQL migration.
- 2026-07-30 — OpenAI: Agents SDK owns the agent loop; Codex is exposed through
  an executor/MCP boundary; VFBiz owns workflow state, approval and evidence.
- 2026-07-30 — Safety: product workspace writes and external mutations are
  disabled; coding execution tests use synthetic fixture repositories.

# Implementation phases and allowed paths

1. Governance: work item, ExecPlan, ADR, architecture and lifecycle documents.
2. Foundation: package/workspace registration, organization routing and runtime
   JSON Schema.
3. Runtime: domain model, SQLite store, CLI/worker and governance adapter.
4. Agent execution: Agents SDK adapter, manager workflows, Codex/worktree ports,
   tracing and encrypted checkpoints.
5. Assurance: unit, contract, integration, security, eval and changed-path gates;
   generate provider/doc/work views only when their generators require it.

The exclusive resources are `agent-organization-registry`,
`dependency-lockfile` and the new runtime contract. No product path may be
added to this plan without a new work item.

# Validation and evidence

Record only observed results in VFBIZ-0204. Required gates are
`verify:agent-runtime`, `agent-control:check`, `adapters:check`,
`governance:check`, `contracts:lint`, `docs:check` and the changed-path check.
Do not infer OpenAI connectivity, production readiness or human risk acceptance
from fixture tests.

# Rollback and recovery

- Runtime state is outside Git and can be disabled without migrating canonical
  work items.
- Removing the new workspace registration and runtime-only files restores the
  prior manual/CLI workflow; product code and databases are unaffected.
- Failed runs stop safely and retain append-only evidence. No automatic cleanup
  may delete a user worktree or unrelated runtime state.

# Outcomes and retrospective

The additive candidate is code-complete locally. Acceptance remains pending the
unrelated `mobile/README.md` governance blocker and the named human ADR
decisions. Released and outcome-validated remain later human-controlled states.
