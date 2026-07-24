---
id: plan-vfbiz-0001
title: ExecPlan chuẩn hóa repository đa-agent
status: archived
owner_role: engineering-lead
scope: root
when_to_read:
  - VFBIZ-0001
  - governance-refactor
tags:
  - agents
  - governance
  - context
revision: 3
review_date: 2026-08-22
supersedes: []
---

# Purpose

Replace externally coupled operating state with portable Git-native work items while
preserving the existing claim, lease, fencing and provider-handoff controls.

## Progress

- [x] 2026-07-22: Inspect current instructions, docs, skills, adapters and agent
  control without modifying runtime paths.
- [x] Establish Git-native work and documentation metadata.
- [x] Consolidate instructions, operating docs, roles and skills.
- [x] Make routing, claims and hooks proportional to delivery mode.
- [x] Run context, provider parity, skill and governance checks.

## Discoveries

- Current hooks require a claim for every Claude/Gemini write while Codex has no
  equivalent provider hook.
- The former hand-maintained catalog duplicated and conflicted with document
  metadata; generated `docs/INDEX.md` and Git-local cache now replace it.
- Fast tasks currently over-fetch sprint/product documents and require claims.
- Existing local claim/lease/fencing control is valuable and should be retained.

## Decisions

- Git Markdown/YAML is canonical; external work-management state is not repository authority.
- Root has five core skills; domain skills live in their owning workspace.
- Frontmatter is canonical; indexes/catalogs are generated.
- Fast tasks load no extra docs and need no claim.
- Only concurrent/delegated writers, controlled work and parallel work require
  claims; exclusive resources still require leases.

## Implementation phases

1. Rewrite root and workspace instruction layers.
2. Consolidate operating docs and add canonical metadata.
3. Add work-item/index/context CLI and schemas.
4. Consolidate roles/skills and regenerate provider adapters.
5. Update agent control/hooks and run regression scenarios.

## Validation

- `npm run docs:check`
- `npm run work:check`
- `npm run adapters:check`
- `npm run agent-control:check`
- `npm run work-control:check`
- `npm run governance:check`

## Rollback and recovery

All changes are confined to governance/docs/tooling paths. Preserve the
pre-existing dirty worktree; rollback this work by reverting only VFBIZ-0001
paths, never with a repository-wide reset.

## Outcomes and retrospective

- Git now carries the canonical work item, plan, instructions, role and skill
  definitions. `WORK.md` and `docs/INDEX.*` are generated views.
- Codex, Claude and Gemini adapters are generated from the same six portable
  runtime roles. Generic clients can bootstrap with `npm run agent:context`.
- Context routing is proportional: `fast` loads no extra docs, while controlled
  work loads only the matching active policy headings and requires a claim.
- The retained claim/lease/fencing implementation passed its regression suite,
  including provider handoff and exclusive-resource behavior.
- Remote administration is outside this work item and remains the user's
  responsibility. Repository cleanup does not call remote connectors.
- OpenAPI lint still has 31 non-blocking warnings that pre-date this governance
  refactor. They should be addressed in a runtime-contract work item rather
  than mixed into this change.
