---
id: context-and-handoff
title: Context routing, compaction và handoff
status: active
owner_role: engineering-lead
scope: root
when_to_read:
  - context
  - resume
  - compact
  - handoff
tags:
  - context
  - tokens
  - handoff
revision: 1
review_date: 2026-09-01
supersedes:
  - context-compaction
---

# Context, compaction and handoff

Load context in this order: current work item, root/nearest instructions,
touched files/tests, local workspace docs, exact controlled policy/contract and
at most two skills.

## Budgets

- Fast: no extra docs.
- Bounded/discovery: at most three documents or exact headings.
- Controlled: at most six documents or exact headings.
- Cross-system: at most eight documents/headings per lane.
- Resume: checkpoint, diff and nearest instructions; at most three initial docs.

These are ceilings, not targets. Do not recursively read documentation or load
an entire file when one section is sufficient. `proposed`, `superseded` and
`archived` material is excluded unless explicitly requested.

## Compaction triggers

Checkpoint before compacting at a phase boundary, after noisy research/tests,
before changing provider/session/worktree, or when the native client reports
low remaining context. Do not use one fixed percentage across providers.

Never compact during an incomplete edit, migration or unresolved decision.
Finish the atomic action and inspect Git state first.

## Durable checkpoint

Keep the checkpoint under approximately 1,200–1,500 tokens. Record work ID,
goal, status, base/head revisions, allowed and changed paths, decisions,
assumptions, observed checks, remaining acceptance, blockers, source hashes and
one exact next action. Never include secrets, PII, production data, customer
conversations, raw logs or hidden reasoning.

On resume, validate Git revisions, read the checkpoint and nearest instruction
chain, then reload only sources whose hash changed. Provider identity and model
metadata are telemetry, never authority.
