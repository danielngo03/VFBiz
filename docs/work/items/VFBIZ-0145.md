---
id: VFBIZ-0145
title: Introduce canonical AI contract registry
status: done
mode: controlled
priority: P0
owner_team: architecture-integration
accountable_role: architect
primary_workspace: root
affected_workspaces:
  - root
  - ai
allowed_paths:
  - contracts/ai
  - docs/work/items/VFBIZ-0145.md
  - WORK.md
depends_on:
  - VFBIZ-0144
controlled_signals:
  - contract
  - dataset-release
  - architecture
exclusive_resources:
  - public-contract
required_checks:
  - npm run contracts:lint
  - npm run verify:ai
  - npm run governance:check
revision: 5
review_date: "2026-08-28"
updated_at: "2026-07-28T10:21:26.366Z"
---

# Outcome

Introduce one stable AI contract registry and capability-based contract layout
without changing contract identity or breaking existing runtime consumers.

## Constraints

- Preserve every existing `$id` and semantic validation rule.
- Move canonical schemas once; compatibility entries may only delegate to the
  canonical schema and must be explicitly time-bounded.
- Contract consumers resolve stable contract IDs through the registry as they
  migrate; no consumer may invent a second authority.
- Do not mix OpenAPI, runtime or Dataset Factory behavior changes into this
  work item.

## Done when

- `contracts/ai/index.json` maps every stable contract ID to one canonical path.
- Assistant, release and dataset contracts are grouped by capability rather
  than kept in a flat directory.
- Dataset source, product, payload, evaluation and export schemas have clear
  ownership boundaries.
- One compatibility revision keeps existing path-based consumers operational
  while identifying the canonical target; contract vectors pass in JS and
  Python.
- No two full schemas claim the same `$id` and no generated check dirties the
  worktree.

## Checkpoint

- Exact next action: independently review contract identity, alias safety and
  registry enforcement, then remove any unresolved finding before closure.

## Evidence

- [x] `npm run contracts:lint` — passed at `consolidated-checkpoint`; 20 registered AI
  contracts, six runtime schemas and 18 dataset vectors validated.
- [x] `npm run verify:ai` — passed after canonical move at `consolidated-checkpoint`;
  433 tests passed and 80 environment-bound tests remained explicitly skipped.
- [x] `npm run governance:check` — `npm run verify:governance` passed at
  `consolidated-checkpoint`, including agent-control, work-control and registry-backed
  contract checks.

### ready — 2026-07-28T10:14:39.099Z

VFBIZ-0144 is complete; contract inventory and compatibility strategy are bounded.

### active — 2026-07-28T10:14:39.230Z

Begin canonical registry and compatibility revision without changing contract semantics.

### review — 2026-07-28T10:20:57.980Z

Canonical layout and registry committed at consolidated-checkpoint; registry-backed enforcement committed at consolidated-checkpoint. Begin independent contract and risk review.

### done — 2026-07-28T10:21:26.366Z

Independent contract and risk reviews found no unresolved finding. Canonical IDs are unchanged, aliases remain repository-contained and CI resolves runtime schemas through the registry.
