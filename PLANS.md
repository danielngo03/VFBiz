# VFBiz ExecPlans

Use an ExecPlan only for work that is multi-hour, multi-session, cross-system,
migration-heavy or split across independent writer lanes. Small and bounded
changes use only a work item.

An ExecPlan is a living, self-contained document under
`docs/work/plans/VFBIZ-NNNN.md`. It must let a stateless agent resume without
reading the entire repository.

Each plan contains:

1. Purpose and observable outcome.
2. Scope, boundaries and non-goals.
3. Progress checklist with timestamps.
4. Surprises and discoveries.
5. Decision log with owner and source.
6. Implementation phases and allowed paths.
7. Validation and observed evidence.
8. Rollback or recovery.
9. Outcomes and retrospective.

Update the plan at every material stopping point. Never pre-fill successful
evidence, human approval or release state.
