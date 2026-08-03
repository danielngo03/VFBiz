---
id: VFBIZ-0190
title: Reconcile Customer Assistant repository truth
status: done
mode: controlled
priority: P0
owner_team: agent-platform
accountable_role: engineering-lead
primary_workspace: root
affected_workspaces:
  - root
allowed_paths:
  - README.md
  - WORK.md
  - docs
  - tools
  - package.json
  - package-lock.json
depends_on: []
controlled_signals:
  - customer-chat
  - agent-governance
  - dependency-policy
exclusive_resources:
  - work-registry
  - documentation-index
  - lockfile
required_checks:
  - npm run governance:check
  - npm run docs:check
  - npm run contracts:lint
revision: 6
review_date: "2026-08-29"
updated_at: "2026-07-29T14:39:55.863Z"
---

# Outcome

Make repository documentation, work state and staging claims match the
capabilities that are actually composed and verified for the Customer
Assistant.

## Constraints

- Do not compose the public Chat API.
- Do not invent human approval, production readiness or acceptance evidence.
- Preserve the solo direct-main workflow until the staging CI gate is opened.
- Dependency remediation must use controlled upgrades or time-bounded
  exceptions; never use a forced audit fix.

## Done when

- Missing or stale work-item references and coordination state are reconciled.
- A generated capability maturity view distinguishes Implemented, Candidate,
  Target-only and Human-blocked capabilities using repository evidence.
- README and canonical API/AI architecture documents no longer overstate or
  understate the Customer Assistant runtime.
- Production dependency findings have a reachability decision, remediation
  path or explicit expiring exception.
- Documentation and governance checks regenerate cleanly without dirtying the
  worktree.

## Checkpoint

- Capability maturity is rendered from a curated register with
  status-specific evidence classes; dangling IDs in active work records and
  plans are rejected by governance.
- The dependency snapshot is bound to the lockfile and the live gate compares
  severity, package and advisory identities. No exception is approved; the 14
  high findings remain an explicit staging blocker owned by VFBIZ-0197.
- VFBIZ-0194/0195 now depend on first-party Knowledge, 1,000 human-adjudicated
  Golden cases and supply-chain closure instead of relying on prose gates.
- Exact next action: record the completed independent correctness/risk review
  in the governed ledger and close VFBIZ-0190.

## Evidence

- [x] `npm run governance:check` — maturity, docs, reports, work references,
  authorization and 75 routing scenarios passed.
- [x] `npm run docs:check` — 78 indexed documents are current.
- [x] `npm run contracts:lint` — five OpenAPI documents, 32 registered AI
  contracts, 49 dataset vectors and workforce capabilities passed.
- [x] Independent final review — PASS with no P0/P1 after advisory identity,
  exception evidence and staging dependency remediation.

### done — 2026-07-29T14:39:55.863Z

Repository truth gate completed: maturity and work references are deterministic, dependency risk is lockfile/advisory-bound, staging prerequisites are explicit, and independent correctness/risk review passed with no open P0/P1.
