---
id: VFBIZ-0205
title: Harden workspace agent instruction parity and governance gates
status: review
mode: controlled
priority: P1
owner_team: identity-experience
accountable_role: identity-platform-owner
primary_workspace: identity-theme
affected_workspaces:
  - identity-theme
  - design-tokens
allowed_paths:
  - apps/identity-theme/CLAUDE.md
  - packages/design-tokens/CLAUDE.md
  - docs/work/items/VFBIZ-0205.md
  - WORK.md
depends_on: []
controlled_signals:
  - provider-parity
  - agent-control
exclusive_resources: []
required_checks:
  - governance:check
  - adapters:check
  - docs:check
revision: 4
review_date: "2026-07-30"
updated_at: "2026-07-30T15:08:55.625Z"
---

# Outcome

Make provider instruction discovery deterministic for the Identity Theme and
Design Tokens workspaces without changing their product code.

## Constraints

- Documentation and deterministic governance fixtures only. Do not modify
  product source, runtime behavior, public contracts, schemas or migrations.
- Keep workspace guidance thin: `AGENTS.md` remains canonical and `CLAUDE.md`
  only imports it plus one workspace-specific reminder.
- Preserve unrelated dirty changes. This item owns documentation shims only;
  root governance fixtures/checkers are a separate agent-platform item.

## Done when

- Identity theme and design tokens have exact provider shims that resolve their
  nearest `AGENTS.md`.
- Governance, adapter parity and documentation checks pass with no product-code
  diff introduced by this work item.

## Checkpoint

- 2026-07-30: repository-wide instruction audit found complete exact guidance
  for API, AI, Drupal, portals, infra and `mobile/customer`; runtime guidance
  was completed under VFBIZ-0204. Identity theme and design tokens lack only
  thin Claude import shims.
- 2026-07-30: both thin shims were added under a scoped identity-experience
  claim. Codex prompt inspection loaded the correct nearest instruction for
  both workspaces.
- Exact next action: obtain independent read-only acceptance review; do not
  widen this documentation-only item.

## Evidence

- [x] `governance:check` — 2026-07-30: instruction budgets, workspaces,
  provider adapters, skills and 75 context scenarios passed.
- [x] `adapters:check` — 2026-07-30: nine Codex, nine Claude and nine Gemini
  worker adapters match the canonical organization.
- [x] `docs:check` — 2026-07-30: generated index is current at 93 documents.
- [x] Codex discovery — root, API, AI, mobile/customer, runtime, Identity Theme
  and Design Tokens each loaded the expected nearest `AGENTS.md`.

### ready — 2026-07-30T14:59:12.176Z

User authorized documentation-only workspace agent hardening; scope and acceptance are explicit.

### active — 2026-07-30T14:59:12.470Z

Begin one controlled documentation lane; product source remains untouched.

### review — 2026-07-30T15:08:55.625Z

Implementation and deterministic checks are complete; independent read-only acceptance remains required.
