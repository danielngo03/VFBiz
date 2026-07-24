# VFBiz agent guide

This is the provider-neutral instruction root. Product scope, technical truth,
work state and evidence live in Git; chat history and provider memory do not.

## Start here

1. Restate one outcome, explicit constraints and "done when".
2. Choose the owning workspace and start the agent with that workspace as its
   working directory so the nearest `AGENTS.md` is active.
3. Classify the change with `npm run agent:context -- --path <target>`.
4. Read only the returned headings, touched files and relevant tests.
5. Use at most two matching skills. Do not recursively read `docs/`.

## Delivery modes

- `fast`: local, reversible and low-risk; one agent, no work item, claim,
  reviewer or extra document.
- `bounded`: one workspace and one writer; use a short work item, at most three
  documents/headings and proportional checks.
- `controlled`: authentication, authorization, PII, payment, migration, public
  contract, AI, dependency policy or production; claim, focused risk review and
  human gate are mandatory; at most six documents/headings.
- `discovery`: gather evidence and produce a decision-ready proposal; do not
  edit runtime code.
- `parallel`: at most three disjoint writer lanes, one worktree per writer and
  one integration owner.

Complexity never lowers risk. A two-line authorization change is controlled.

## Repository boundaries

- `drupal/`: public SSR, CMS, editorial workflow and SEO.
- `backend/api/`: public `/api/v1`, authorization, business state and provider
  orchestration.
- `backend/ai/`: private retrieval, model policy, evaluation and AI tool
  proposals; clients never call it directly.
- `apps/` and `mobile/`: clients of generated contracts, not data authorities.
- `infra/`: environments, delivery, observability and recovery.
- `contracts/`: shared machine-readable interfaces and schemas.

Read the nearest workspace instructions before changing any workspace. Root
docs contain only cross-system product, architecture, governance, decisions and
work state; implementation detail stays with its workspace.

## Multi-agent rules

- Only the orchestrator delegates. Workers set `may_delegate: false`.
- One path has one writer. Reviewers are read-only and never silently fix.
- Parallel writers require claims, disjoint allowed paths and separate
  worktrees. Contracts, migrations, lockfiles, Drupal config and AI dataset
  registries require exclusive leases.
- Retry the same cause at most twice. Review/fix stops after two cycles. Reopen
  a finding only with new evidence.
- Return concise summaries and evidence, never raw logs or hidden reasoning.

## Safety and authority

- Preserve unrelated work in a dirty worktree. Never reset or delete another
  contributor's changes.
- Never commit secrets, production data, customer conversations, proprietary
  datasets or assets without verified rights.
- Never invent prices, specifications, sources, approvals or test results.
- Agents do not accept product scope, architecture, risk or release on behalf
  of a human owner.
- Stop only the affected lane when authority, trustworthy data, rights,
  rollback or safety evidence is missing.

## Plans, checkpoints and completion

- `bounded` and higher work uses `docs/work/items/VFBIZ-NNNN.md`.
- Use `PLANS.md` only for multi-hour, multi-session, cross-system, migration or
  parallel work.
- Before compaction, interruption or provider handoff, finish the atomic action
  and update the durable checkpoint with revisions, changed paths, decisions,
  observed checks, blockers and one exact next action.
- `code-complete`, `acceptance-complete`, `released` and
  `outcome-validated` are distinct states.

Run `npm run governance:check` for governance changes and the nearest workspace
commands for runtime changes. CI and deterministic repository scripts are the
enforcement authority; provider hooks are optional adapters.
