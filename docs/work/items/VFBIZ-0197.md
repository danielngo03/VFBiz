---
id: VFBIZ-0197
title: Close production supply-chain staging blockers
status: proposed
mode: controlled
priority: P0
owner_team: agent-platform
accountable_role: security-owner
primary_workspace: root
affected_workspaces:
  - root
  - api
  - customer-portal
  - workforce-portal
allowed_paths:
  - package.json
  - package-lock.json
  - apps/customer-portal/package.json
  - apps/workforce-portal/package.json
  - backend/api/package.json
  - docs/governance/dependency-risk-register.md
  - docs/governance/dependency-risk-snapshot.json
  - docs/work/items/VFBIZ-0197.md
  - tools/check-dependency-risk-snapshot.mjs
  - tests/governance/check-dependency-risk-snapshot.mjs
  - WORK.md
depends_on:
  - VFBIZ-0190
controlled_signals:
  - dependency-policy
  - supply-chain
  - staging-release
exclusive_resources:
  - dependency-lockfile
required_checks:
  - npm run dependency-risk:live-check
  - npm run verify:api
  - npm run verify:apps
  - npm run verify:governance
revision: 1
review_date: "2026-08-12"
---

# Outcome

Remove every high or critical production dependency finding, or bind a narrowly
scoped, time-limited Security Owner exception with tested compensating controls,
before staging can be enabled.

## Constraints

- Do not run forced audit remediation or accept incompatible framework
  downgrades.
- A prose risk register is not machine evidence.
- Every exception identifies advisory, reachability, owner, mitigation, expiry
  and removal work item.

## Done when

- The live production audit matches the lockfile-bound evidence snapshot.
- There are zero unexcepted high or critical findings.
- API and both portal regression gates pass after dependency changes.
- CI re-runs the live comparison whenever the lockfile changes.

## Checkpoint

- Fourteen high and zero critical production findings remain open.
- Exact next action: remediate the directly reachable Fastify routing/static
  families first, then the supported Next/Sharp/PostCSS graph.

## Evidence

- [ ] `npm run dependency-risk:live-check` — current observed result is blocked.
- [ ] `npm run verify:api` — add post-remediation evidence.
- [ ] `npm run verify:apps` — add post-remediation evidence.
- [ ] `npm run verify:governance` — add observed evidence.
