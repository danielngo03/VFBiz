# VFBiz agent runtime guide

This workspace is the single-host control plane for governed agent work. It is
not the ViVi/customer AI runtime and it has no authority over product state.

## Boundaries

- Keep runtime state in the Git common directory, never in an API or AI
  database.
- Resolve the canonical work item and organization before selecting a model or
  specialist.
- Product workspace writes, external mutation, merge, deploy, migration,
  release and secret tools do not exist in v1.
- Coding tests copy a registered source under `tests/fixtures` into an
  ephemeral, runtime-attested Git worktree outside VFBiz. Arbitrary external
  worktrees are never accepted.
- Every agent response crosses a typed boundary. Agents cannot add a role,
  team, path or authority that is absent from the resolved context.
- Reviewer and risk-reviewer executions are read-only. Agents never approve
  their own work or accept risk.

## Checks

Run `npm run verify:agent-runtime` from the repository root. Live OpenAI and
Codex execution is feature-flagged off by default and is not required by CI.
Before a fresh Codex Desktop session continues a runtime run, generate
`npm run agent-runtime:brief -- --work VFBIZ-NNNN --target <workspace>` and
stop on stale context, pending approval or reconciliation.
