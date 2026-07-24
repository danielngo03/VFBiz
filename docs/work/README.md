---
id: work-management
title: Quản lý công việc Git-native
status: active
owner_role: engineering-lead
scope: root
when_to_read:
  - create-work-item
  - resume
  - handoff
tags:
  - work
  - plans
  - evidence
revision: 1
review_date: 2026-08-22
supersedes:
  - external-work-management
---

# Work management

Git is the canonical source for approved work, implementation state, decisions
and evidence.

- `items/`: one bounded or controlled outcome per `VFBIZ-NNNN.md`.
- `plans/`: living ExecPlans only for complex or multi-session work.
- `archive/`: completed or superseded historical artifacts.
- `WORK.md`: generated summary; never edit it as the primary state.

Use `npm run work:new`, `work:list`, `work:show`, `work:ready`, `work:start`,
`work:review`, `work:checkpoint`, `work:block`, `work:done` and `work:cancel`.
Chat, spreadsheets and provider memory may link to a work item but cannot
replace it.

Every work item has one owner team and one accountable human role. Department
ownership is derived from `.agents/organization.json`; do not duplicate it in
the item. Parallel delivery uses separate work items for each writer lane and a
shared ExecPlan for dependencies and integration.

The state machine is enforced by the CLI:

```text
proposed -> ready -> active -> review -> done
                       |         |
                       +-> blocked
proposed|ready|active|blocked -> cancelled
```

`ready` requires bounded paths, acceptance, an existing owner team and completed
dependencies. `done` additionally requires observed evidence for every required
check. Workers report evidence; only the orchestrator or integration owner
updates canonical work state.
