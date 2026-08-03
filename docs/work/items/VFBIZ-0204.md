---
id: VFBIZ-0204
title: Build additive VFBiz enterprise agent runtime v1
status: active
mode: controlled
priority: P1
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
allowed_paths:
  - AGENTS.md
  - agent-runtime
  - .agents/organization.json
  - .agents/skills/handoff-context
  - .agents/skills/operate-agent-runtime
  - .codex
  - .claude
  - .gemini
  - contracts/governance/agent-runtime.schema.json
  - tools/check-runtime-contracts.mjs
  - tools/docs-index.mjs
  - docs/decisions
  - docs/architecture
  - docs/operating-model
  - docs/governance/dependency-risk-snapshot.json
  - docs/work/items/VFBIZ-0204.md
  - docs/work/plans/VFBIZ-0204.md
  - package.json
  - package-lock.json
  - WORK.md
  - docs/INDEX.md
  - docs/INDEX.json
depends_on: []
controlled_signals:
  - ai-tool
  - ai-quality-platform
exclusive_resources:
  - agent-organization-registry
  - dependency-lockfile
required_checks:
  - verify:agent-runtime
  - agent-control:check
  - adapters:check
  - governance:check
  - contracts:lint
  - docs:check
  - changed-paths:check
revision: 7
review_date: "2026-07-30"
updated_at: "2026-07-30T14:11:12.878Z"
---

# Outcome

Deliver a single-host, SQLite-backed enterprise agent runtime at
`agent-runtime` that reuses VFBiz governance, orchestrates typed
OpenAI Agents SDK runs, exposes Codex through an isolated adapter, survives
process restart and never changes product workspace code in this work item.

## Constraints

- Additive control-plane work only. Do not modify `backend/**`, `apps/**`,
  `mobile/**`, `drupal/**`, `infra/**` or `packages/**`.
- No production credentials, customer data, deploy, merge, migration or public
  API capability.
- Existing Git work-item state and agent claims/leases remain canonical;
  SQLite stores runtime operational state only.
- One local writer lane; read-only specialists may run in parallel within the
  organization budget. Do not introduce PostgreSQL, Temporal or a remote MCP
  gateway.
- Preserve all unrelated dirty-worktree changes. Exclusive organization and
  governance-contract edits require this work item and a bounded diff.
- The user's 2026-07-30 implementation request authorizes this local candidate;
  it does not grant production release or risk-acceptance authority.

## Done when

- `agent-runtime` provides enqueue, worker, status, resume, cancel,
  approval, doctor and eval commands with typed domain/application boundaries.
- SQLite events, checkpoints, approvals, artifacts and usage are transactional,
  idempotent and restart-safe; prompt-bearing checkpoints are encrypted by a
  non-repository key.
- Deterministic context routing precedes model routing; Agents SDK specialists
  return typed results and cannot extend tool, path or human authority.
- Codex and worktree adapters are sandboxed and verified only against fixture
  repositories; nested delegation and external mutation remain disabled.
- Runtime contracts, trace metadata, evaluation fixtures, operator guidance and
  cross-system documentation are present and validated.
- A new Codex Desktop session can derive a bounded, redacted resume brief from
  the canonical work item plus the runtime ledger without provider memory or
  checkpoint decryption.
- `git diff --name-only` contains no product workspace path and every required
  repository check has observed evidence.

## Checkpoint

- 2026-07-30: user approved implementation of the additive plan; controlled
  scope was triaged and this work item was allocated before runtime code.
- 2026-07-30: additive runtime is code-complete locally. Two independent review
  cycles found and drove fixes for canonical authority refresh, typed reviewer
  recognition, usage accounting, cancellation recovery and legacy migrations.
- 2026-07-30: the workspace was flattened from `platform/agent-runtime` to
  `agent-runtime`; `platform/` had no sibling workspace. Rename-specific root
  resolution tests were corrected and the full runtime suite passed again.
- 2026-07-30: added a redacted `agent-runtime brief` resume packet. It combines
  the current work item/context with persisted run, approval, artifact, usage,
  checkpoint metadata and event digests. The real legacy run proved that an
  expired context cache is re-resolved and old authority is marked stale.
- Exact next action: settle or isolate the concurrent product lanes, rerun the
  program changed-path gate, then obtain the named human ADR decisions before
  any live-provider pilot.

## Evidence

- [x] `verify:agent-runtime` — 2026-07-30: lint/typecheck/build plus 20 unit,
  4 contract, 8 integration, 7 security and 3 eval tests passed.
- [x] `agent-control:check` — 2026-07-30: claims, leases, fencing, paths,
  handoff and retry/review controls passed.
- [x] `adapters:check` — 2026-07-30: generated provider adapters match the
  canonical organization.
- [x] `governance:check` — 2026-07-30: full governance passes after replacing
  the stale container-mobile scenario with `mobile/customer/README.md`.
- [x] `contracts:lint` — 2026-07-30: public contracts, seven runtime schemas
  and workforce capability validation passed.
- [x] `docs:check` — 2026-07-30: generated index is current at 93 documents.
- [ ] `changed-paths:check` — the current shared-tree rerun correctly reports
  product paths from other active AI/API/mobile/infra/design-token work plus
  two documentation-only shims owned by VFBIZ-0205. Do not recapture the
  baseline or hide this attribution boundary.
- [x] Runtime production dependency audit — 2026-07-30: zero production
  vulnerabilities for `@vfbiz/agent-runtime`; repository-wide live staging
  audit remains blocked by 21 pre-existing high-risk product packages.
- [x] Desktop/runtime resume — 2026-07-30: a fresh Codex prompt contains the
  deterministic brief instruction; real-ledger output omitted decrypted state
  and raw payloads, detected the relocated workspace/cache miss and returned
  `stale-context` with the canonical exact next action.

## Review disposition

- Independent correctness and risk reviewers each completed two read-only
  cycles. The second cycle exposed five concrete runtime gaps; all received
  focused regression tests and local fixes after the final permitted cycle.
- No reviewer accepted risk or approved release. OpenAI, Codex and tracing stay
  disabled by default; ADR-0009 remains proposed for architect, security, data
  and engineering decisions.

### ready — 2026-07-30T12:54:41.383Z

User approved the additive implementation plan; decision packet, scope boundaries and rollback are recorded.

### active — 2026-07-30T12:54:41.670Z

Begin one controlled writer lane for the additive agent runtime; product workspaces remain forbidden.

### active — 2026-07-30T14:11:12.878Z

Code-complete local candidate; runtime gates pass and two review cycles are observed. Acceptance remains pending the unrelated mobile/README.md governance failure and named human ADR decisions. Exact next action: restore or formally replace mobile/README.md, rerun governance:check, then conduct the human boundary decision.
